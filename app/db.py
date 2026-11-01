"""База сайта: SQLite, простые помощники без ORM."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("S93_DB", os.path.join(BASE, "data", "site.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS news(
  id INTEGER PRIMARY KEY, slug TEXT UNIQUE, title TEXT, date TEXT, rubric TEXT,
  lead TEXT, cover TEXT, body TEXT, vk TEXT, published INTEGER DEFAULT 1, updated TEXT);
CREATE TABLE IF NOT EXISTS docs(
  id INTEGER PRIMARY KEY, title TEXT, url TEXT, kind TEXT, year INTEGER, updated TEXT, main_doc INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS doc_places(
  doc_id INTEGER, page TEXT, grp TEXT, pos INTEGER DEFAULT 0,
  PRIMARY KEY(doc_id, page));
CREATE TABLE IF NOT EXISTS people(
  id INTEGER PRIMARY KEY, name TEXT, position TEXT, duty TEXT, phone TEXT, email TEXT,
  building TEXT, photo TEXT, pos INTEGER DEFAULT 100, tags TEXT DEFAULT '[]',
  edu TEXT, qual TEXT, experience TEXT, subjects TEXT, grp TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS pages(url TEXT PRIMARY KEY, data TEXT, updated TEXT, user TEXT);
CREATE TABLE IF NOT EXISTS page_edits(url TEXT, path TEXT, data TEXT, updated TEXT, user TEXT, PRIMARY KEY(url, path));
CREATE TABLE IF NOT EXISTS page_history(id INTEGER PRIMARY KEY, url TEXT, path TEXT, data TEXT, updated TEXT, user TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS clubs(
  id INTEGER PRIMARY KEY, title TEXT, direction TEXT, age TEXT, building TEXT,
  teacher TEXT, schedule TEXT, pos INTEGER DEFAULT 100);
CREATE TABLE IF NOT EXISTS vacancies(
  id INTEGER PRIMARY KEY, title TEXT, building TEXT, contact TEXT, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS food_files(
  id INTEGER PRIMARY KEY, kind TEXT, label TEXT, filename TEXT, uploaded TEXT);
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, login TEXT UNIQUE, name TEXT, role TEXT, pw TEXT,
  fails INTEGER DEFAULT 0, locked_until TEXT);
CREATE TABLE IF NOT EXISTS journal(
  id INTEGER PRIMARY KEY, at TEXT, user TEXT, section TEXT, action TEXT, what TEXT);
"""


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


_ready = set()


@contextmanager
def conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    if DB_PATH not in _ready:  # схема создаётся при первом обращении
        c.executescript(SCHEMA)
        for mig in ("ALTER TABLE docs ADD COLUMN main_doc INTEGER DEFAULT 0", "ALTER TABLE clubs ADD COLUMN kvant INTEGER DEFAULT 0",
                    "ALTER TABLE news ADD COLUMN date_exact INTEGER DEFAULT 1", "ALTER TABLE news ADD COLUMN import_key TEXT",
                    "ALTER TABLE users ADD COLUMN totp_secret TEXT", "ALTER TABLE users ADD COLUMN totp_on INTEGER DEFAULT 0",
                    "ALTER TABLE users ADD COLUMN totp_last INTEGER DEFAULT 0", "ALTER TABLE users ADD COLUMN recovery TEXT",
                    "ALTER TABLE users ADD COLUMN active INTEGER DEFAULT 1", "ALTER TABLE users ADD COLUMN last_login TEXT"):
            try:
                c.execute(mig)
            except sqlite3.OperationalError:
                pass  # колонка уже есть
        _ready.add(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript(SCHEMA)


def q(sql, args=()):
    with conn() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def q1(sql, args=()):
    r = q(sql, args)
    return r[0] if r else None


def run(sql, args=()):
    with conn() as c:
        cur = c.execute(sql, args)
        return cur.lastrowid


# ---------- настройки (контакты школы, приём, питание) ----------
def get_setting(key, default=None):
    r = q1("SELECT value FROM settings WHERE key=?", (key,))
    return json.loads(r["value"]) if r else default


def set_setting(key, value):
    run("INSERT INTO settings(key,value,updated) VALUES(?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated=excluded.updated",
        (key, json.dumps(value, ensure_ascii=False), now()))


def setting_updated(key):
    r = q1("SELECT updated FROM settings WHERE key=?", (key,))
    return r["updated"] if r else None


def log(user, section, action, what):
    run("INSERT INTO journal(at,user,section,action,what) VALUES(?,?,?,?,?)",
        (now(), user, section, action, what))


# ---------- выборки для страниц ----------
def people_by_tag(tag, building=None):
    rows = q("SELECT * FROM people ORDER BY pos, name")
    out = []
    for r in rows:
        tags = json.loads(r["tags"] or "[]")
        if tag in tags and (building is None or r["building"] == building):
            r["tags"] = tags
            out.append(r)
    return out


def docs_for(page):
    rows = q("SELECT d.*, p.grp, p.pos FROM docs d JOIN doc_places p ON p.doc_id=d.id "
             "WHERE p.page=? ORDER BY p.pos, d.year DESC, d.title", (page,))
    groups = {}
    for r in rows:
        groups.setdefault(r["grp"] or "", []).append(r)
    return groups


SERVICE_RUBRICS = ("Педагогам",)  # служебные рубрики не уходят в общие ленты для родителей


def news_list(rubric=None, limit=None, offset=0):
    # новость с датой в будущем — отложенная публикация: появится на сайте в свой день
    sql = "SELECT * FROM news WHERE published=1 AND date<=?"
    args = [datetime.now().strftime("%Y-%m-%d")]
    if rubric:
        sql += " AND rubric=?"
        args.append(rubric)
    else:
        sql += " AND rubric NOT IN (%s)" % ",".join("?" * len(SERVICE_RUBRICS))
        args += list(SERVICE_RUBRICS)
    sql += " ORDER BY date DESC, id DESC"
    if limit:
        sql += " LIMIT ? OFFSET ?"
        args += [limit, offset]
    return q(sql, args)


# ---------- страницы: правки из админки поверх исходных текстов ----------
# В базе хранятся только изменённые поля отдельных блоков. Всё остальное каждый раз берётся из content.py,
# поэтому правки в коде (новый блок, исправленная опечатка) доходят и до страниц, которые редактировали в админке.
def _walk(page, path):
    if path == "hero":
        return page
    if path == "card":
        return page.get("card")
    obj = page
    for part in path.split("."):
        obj = obj[int(part)] if isinstance(obj, list) else obj[part]
    return obj


def apply_edit(page, path, data):
    try:
        target = _walk(page, path)
    except (KeyError, IndexError, ValueError, TypeError):
        return False  # блока больше нет в коде: правку не применяем
    if not isinstance(target, dict):
        return False
    t = data.get("t")
    if t and path not in ("hero", "card") and ".info." not in path and target.get("t") != t:
        return False  # на этом месте теперь другой блок
    for k, v in data.get("fields", {}).items():
        if k == "tabs":
            for i, label in enumerate(v):
                if i < len(target.get("tabs", [])) and label:
                    target["tabs"][i][0] = label
        else:
            target[k] = v
    return True


def get_page(url):
    from .content import PAGES
    base = PAGES.get(url)
    if base is None:
        return None
    legacy = q1("SELECT data FROM pages WHERE url=?", (url,))
    page = json.loads(legacy["data"]) if legacy else json.loads(json.dumps(base, ensure_ascii=False))
    for e in q("SELECT path, data FROM page_edits WHERE url=?", (url,)):
        apply_edit(page, e["path"], json.loads(e["data"]))
    return page


def get_edit(url, path):
    r = q1("SELECT data FROM page_edits WHERE url=? AND path=?", (url, path))
    return json.loads(r["data"]) if r else None


def save_edit(url, path, data, user):
    old = q1("SELECT data, updated, user FROM page_edits WHERE url=? AND path=?", (url, path))
    if old:  # прежнюю версию в историю
        run("INSERT INTO page_history(url,path,data,updated,user) VALUES(?,?,?,?,?)", (url, path, old["data"], old["updated"], old["user"]))
    run("INSERT INTO page_edits(url,path,data,updated,user) VALUES(?,?,?,?,?) ON CONFLICT(url,path) DO UPDATE SET data=excluded.data, updated=excluded.updated, user=excluded.user",
        (url, path, json.dumps(data, ensure_ascii=False), now(), user))


def revert_edit(url, path):
    old = q1("SELECT data, updated, user FROM page_edits WHERE url=? AND path=?", (url, path))
    if old:
        run("INSERT INTO page_history(url,path,data,updated,user) VALUES(?,?,?,?,?)", (url, path, old["data"], old["updated"], old["user"]))
    run("DELETE FROM page_edits WHERE url=? AND path=?", (url, path))


def page_changed(url):
    r = q1("SELECT MAX(updated) updated, user FROM page_edits WHERE url=?", (url,))
    if r and r["updated"]:
        return r
    return q1("SELECT updated, user FROM pages WHERE url=?", (url,))


def reset_page(url):
    for e in q("SELECT path FROM page_edits WHERE url=?", (url,)):
        revert_edit(url, e["path"])
    run("DELETE FROM pages WHERE url=?", (url,))
