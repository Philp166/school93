"""Конструктор страниц. Каждая страница — шапка и набор блоков в базе.
content.py нужен только для первого наполнения и для кнопки «Вернуть исходный вид страницы».

Блоки с данными (люди, документы, кружки) хранят не текст, а ссылки на записи базы в нужном порядке:
что лежит в блоке, то и показано на сайте. Никаких скрытых меток."""
import json
import uuid

from . import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS blocks(id TEXT PRIMARY KEY, url TEXT, parent TEXT, tab INTEGER, pos REAL, type TEXT, data TEXT, updated TEXT, user TEXT);
CREATE INDEX IF NOT EXISTS blocks_url ON blocks(url);
CREATE TABLE IF NOT EXISTS page_meta(url TEXT PRIMARY KEY, data TEXT, updated TEXT, user TEXT);
CREATE TABLE IF NOT EXISTS block_history(id INTEGER PRIMARY KEY, block_id TEXT, url TEXT, action TEXT, data TEXT, updated TEXT, user TEXT);
"""

META_KEYS = ("title", "h1", "lead", "buttons", "card", "obj", "k", "main", "ktabs", "section", "sveden")
DATA_TYPES = {"people", "docs", "clubs"}            # блоки со ссылками на базу
FIXED_TYPES = {"sveden_data", "newspage", "status1", "menu", "buildings", "requisites"}  # нельзя удалить: без них страница теряет смысл


def init():
    with db.conn() as c:
        c.executescript(SCHEMA)
        try:
            c.execute("ALTER TABLE blocks ADD COLUMN deleted INTEGER DEFAULT 0")  # удалённый блок можно вернуть
        except Exception:  # noqa: BLE001
            pass


def new_id():
    return uuid.uuid4().hex[:10]


# ---------- перевод исходных страниц из content.py в блоки ----------
def _people_ids(tag):
    return [p["id"] for p in db.people_by_tag(tag)]


def _docs_groups(url, only=None, exclude=()):
    groups = db.docs_for(url)  # из первичного импорта: страница → группа → документы по порядку
    out = []
    for g, items in groups.items():
        if only is not None and g not in only:
            continue
        if g in exclude:
            continue
        out.append({"title": g, "ids": [d["id"] for d in items]})
    if only:
        out.sort(key=lambda x: only.index(x["title"]) if x["title"] in only else 99)
    return out


def _claimed(blocks):
    s = set()
    for b in blocks:
        if b.get("t") == "docs" and b.get("groups"):
            s.update(b["groups"])
        if b.get("t") == "tabs":
            for _, inner in b["tabs"]:
                s |= _claimed(inner)
    return s


def convert_block(b, page, claimed):
    """Блок из content.py → (тип, данные, дети). Дети нужны вкладкам."""
    t = b.get("t")
    d = {k: v for k, v in b.items() if k != "t"}
    url = page["url"]
    if t == "people":
        return "people", {"title": b.get("title", ""), "view": "grid", "groups": [{"title": "", "ids": _people_ids(b.get("tag", ""))}]}, None
    if t == "docs":
        if b.get("groups"):
            groups = _docs_groups(url, only=list(b["groups"]))
        elif b.get("rest"):
            groups = _docs_groups(url, exclude=claimed)
        else:
            groups = _docs_groups(url)
        return "docs", {"title": b.get("title", "Документы"), "view": "list", "groups": groups, "id": b.get("id", "")}, None
    if t == "schedule":
        from .main import schedule_groups
        bl, other = schedule_groups(url)
        groups = [{"title": name, "ids": [d["id"] for d in items]} for name, items in bl]
        if other:
            groups.append({"title": "Другие документы", "ids": [d["id"] for d in other]})
        return "docs", {"title": "", "view": "tabs", "groups": groups, "empty": "Расписание появится здесь, как только школа загрузит его в админке."}, None
    if t == "clubs":
        # каталог «Кружки и секции» показывает все кружки базы сам; в Кванториуме — только выбранные
        return "clubs", ({"auto": False, "ids": []} if b.get("kvant") else {"auto": True, "ids": []}), None
    if t == "director":
        return "people", {"title": "", "view": "director", "limit": 1, "groups": [{"title": "", "ids": _people_ids("director")[:1]}]}, None
    if t == "admin_groups":
        dirs = set(_people_ids("director")[:1])
        groups = {}
        for p in db.people_by_tag("admin"):
            if p["id"] in dirs:
                continue
            groups.setdefault(p.get("grp") or "Другие", []).append(p["id"])
        return "people", {"title": "", "view": "chips", "id": "adm", "groups": [{"title": g, "ids": ids} for g, ids in groups.items()],
                          "note": "Филиалов и представительств у школы нет."}, None
    if t == "services":
        # каждая служба — вкладка из обычных блоков: заголовок, руководитель, специалисты по корпусам, «с чем прийти»
        from .content import SERVICES, BUILDINGS
        tabs, children = [], []
        for i, (key, label, title) in enumerate(SERVICES):
            S = b["info"][key]
            tabs.append({"label": label, "key": key})
            leads = [p["id"] for p in db.people_by_tag("lead") if key in p["tags"]]
            groups = []
            for bld in ["Первомайская, 30", "Школьная, 19"]:
                ids = [p["id"] for p in db.people_by_tag(key, bld) if "lead" not in p["tags"]]
                if ids:
                    groups.append({"title": bld, "ids": ids, "phone": S["phones"].get(bld, ""), "note": S.get("hours", "")})
            children += [
                (i, "h2", {"text": title, "lead": S["lead"]}),
                (i, "people", {"title": "Руководитель службы", "view": "inline", "limit": 1, "groups": [{"title": "", "ids": leads[:1]}]}),
                (i, "people", {"title": "", "view": "service", "word": list(S["word"]), "groups": groups}),
                (i, "h2", {"text": "С чем можно прийти", "lead": ""}),
                (i, "cards", {"rows": [list(x) for x in S["help"]], "cols": 3, "dark": []}),
            ]
        return "tabs", {"tabs": tabs, "query": "s"}, children
    if t == "sveden_data" and page.get("sveden") == "managers":
        return "people", {"title": "Руководство", "view": "table_managers", "groups": [{"title": "", "ids": _people_ids("admin")}]}, None
    if t == "sveden_data" and page.get("sveden") == "employees":
        return "people", {"title": "Педагогический состав", "view": "table_teachers", "groups": [{"title": "", "ids": _people_ids("teacher")}],
                          "empty": "Список педагогов добавляется в этот блок: нажмите на него в редакторе страницы."}, None
    if t == "tabs":
        tabs, children = [], []
        for i, (label, inner) in enumerate(b["tabs"]):
            tabs.append({"label": label, "key": ""})
            for x in inner:
                children.append((i, x))
        return "tabs", {"tabs": tabs}, children
    return t, d, None


def materialize(url, user="система"):
    """Собрать страницу в базе из content.py (первый запуск или «вернуть исходный вид»)."""
    from .content import PAGES
    page = json.loads(json.dumps(PAGES[url], ensure_ascii=False))
    with db.conn() as c:
        c.execute("DELETE FROM blocks WHERE url=?", (url,))
        c.execute("DELETE FROM page_meta WHERE url=?", (url,))
    meta = {k: page.get(k) for k in META_KEYS if k in page}
    card = meta.get("card")
    if card and card.get("dyn") == "people_card":
        card["ids"] = _people_ids(card.pop("tag", ""))
    db.run("INSERT INTO page_meta(url,data,updated,user) VALUES(?,?,?,?)", (url, json.dumps(meta, ensure_ascii=False), db.now(), user))
    claimed = _claimed(page["blocks"])

    def put(blocks, parent=None, tab=None):
        for i, b in enumerate(blocks):
            if isinstance(b, tuple) and len(b) == 3:  # (вкладка, тип, данные) из служб
                continue
            t, data, children = convert_block(b, page, claimed)
            bid = new_id()
            db.run("INSERT INTO blocks(id,url,parent,tab,pos,type,data,updated,user) VALUES(?,?,?,?,?,?,?,?,?)",
                   (bid, url, parent, tab, float(i), t, json.dumps(data, ensure_ascii=False), db.now(), user))
            if children:
                pos = {}
                for ch in children:
                    if len(ch) == 3:
                        ti, ct, cd = ch
                        cid = new_id()
                        pos[ti] = pos.get(ti, 0) + 1
                        db.run("INSERT INTO blocks(id,url,parent,tab,pos,type,data,updated,user) VALUES(?,?,?,?,?,?,?,?,?)",
                               (cid, url, bid, ti, float(pos[ti]), ct, json.dumps(cd, ensure_ascii=False), db.now(), user))
                    else:
                        ti, x = ch
                        pos[ti] = pos.get(ti, 0) + 1
                        put_one(x, bid, ti, pos[ti])

    def put_one(b, parent, tab, p):
        t, data, children = convert_block(b, page, claimed)
        bid = new_id()
        db.run("INSERT INTO blocks(id,url,parent,tab,pos,type,data,updated,user) VALUES(?,?,?,?,?,?,?,?,?)",
               (bid, url, parent, tab, float(p), t, json.dumps(data, ensure_ascii=False), db.now(), user))

    put(page["blocks"])


def ensure_all():
    from .content import PAGES
    init()
    have = {r["url"] for r in db.q("SELECT DISTINCT url FROM page_meta")}
    for url in PAGES:
        if url not in have:
            materialize(url)


# ---------- чтение страницы для отрисовки ----------
def load_page(url):
    """Страница в том же виде, что раньше давал content.py: шаблоны сайта не меняются."""
    from .content import PAGES
    if url not in PAGES:
        return None
    m = db.q1("SELECT data FROM page_meta WHERE url=?", (url,))
    if not m:
        ensure_all()
        m = db.q1("SELECT data FROM page_meta WHERE url=?", (url,))
    page = json.loads(m["data"])
    page["url"] = url
    page.setdefault("h1", [page.get("title", "")])
    page.setdefault("buttons", [])
    rows = db.q("SELECT * FROM blocks WHERE url=? AND COALESCE(deleted,0)=0 ORDER BY pos", (url,))
    by_parent = {}
    for r in rows:
        by_parent.setdefault(r["parent"], []).append(r)

    def build(r):
        d = json.loads(r["data"])
        d["t"] = r["type"]
        d["_id"] = r["id"]
        if r["type"] == "tabs":
            kids = by_parent.get(r["id"], [])
            d["tabs"] = [[t.get("label", ""), [build(k) for k in kids if k["tab"] == i], t.get("key", "")] for i, t in enumerate(d.get("tabs", []))]
        return d
    page["blocks"] = [build(r) for r in by_parent.get(None, [])]
    return page


def get_block(bid):
    r = db.q1("SELECT * FROM blocks WHERE id=?", (bid,))
    if not r:
        return None
    r["data"] = json.loads(r["data"])
    return r


def save_block(bid, data, user, action="изменил"):
    old = db.q1("SELECT * FROM blocks WHERE id=?", (bid,))
    if not old:
        return False
    db.run("INSERT INTO block_history(block_id,url,action,data,updated,user) VALUES(?,?,?,?,?,?)",
           (bid, old["url"], action, old["data"], old["updated"], old["user"]))
    db.run("UPDATE blocks SET data=?, updated=?, user=? WHERE id=?", (json.dumps(data, ensure_ascii=False), db.now(), user, bid))
    return True


def get_meta(url):
    m = db.q1("SELECT data FROM page_meta WHERE url=?", (url,))
    return json.loads(m["data"]) if m else {}


def save_meta(url, meta, user):
    old = db.q1("SELECT data, updated, user FROM page_meta WHERE url=?", (url,))
    if old:
        db.run("INSERT INTO block_history(block_id,url,action,data,updated,user) VALUES(?,?,?,?,?,?)",
               ("meta:" + url, url, "изменил", old["data"], old["updated"], old["user"]))
    db.run("INSERT INTO page_meta(url,data,updated,user) VALUES(?,?,?,?) ON CONFLICT(url) DO UPDATE SET data=excluded.data, updated=excluded.updated, user=excluded.user",
           (url, json.dumps(meta, ensure_ascii=False), db.now(), user))


def siblings(bid):
    b = db.q1("SELECT * FROM blocks WHERE id=?", (bid,))
    if b["parent"] is None:
        return db.q("SELECT * FROM blocks WHERE url=? AND parent IS NULL AND COALESCE(deleted,0)=0 ORDER BY pos", (b["url"],))
    return db.q("SELECT * FROM blocks WHERE parent=? AND tab=? AND COALESCE(deleted,0)=0 ORDER BY pos", (b["parent"], b["tab"]))


def renumber(rows):
    for i, r in enumerate(rows):
        db.run("UPDATE blocks SET pos=? WHERE id=?", (float(i), r["id"]))


def add_block(url, btype, data, user, after=None, parent=None, tab=None):
    """Новый блок после указанного (или первым в странице/вкладке)."""
    if after:
        a = db.q1("SELECT * FROM blocks WHERE id=?", (after,))
        parent, tab = a["parent"], a["tab"]
        sib = siblings(after)
        idx = [s["id"] for s in sib].index(after) + 1
    else:
        sib = (db.q("SELECT * FROM blocks WHERE url=? AND parent IS NULL AND COALESCE(deleted,0)=0 ORDER BY pos", (url,)) if parent is None
               else db.q("SELECT * FROM blocks WHERE parent=? AND tab=? AND COALESCE(deleted,0)=0 ORDER BY pos", (parent, tab)))
        idx = 0
    bid = new_id()
    db.run("INSERT INTO blocks(id,url,parent,tab,pos,type,data,updated,user) VALUES(?,?,?,?,?,?,?,?,?)",
           (bid, url, parent, tab, 0.0, btype, json.dumps(data, ensure_ascii=False), db.now(), user))
    rows = [s for s in sib]
    rows.insert(idx, {"id": bid})
    renumber(rows)
    return bid


def move_block(bid, direction):
    sib = siblings(bid)
    ids = [s["id"] for s in sib]
    i = ids.index(bid)
    j = i - 1 if direction == "up" else i + 1
    if 0 <= j < len(sib):
        sib[i], sib[j] = sib[j], sib[i]
        renumber(sib)
        return True
    return False


def delete_block(bid, user):
    """Блок прячется, а не стирается: его можно вернуть кнопкой «Вернуть»."""
    b = db.q1("SELECT * FROM blocks WHERE id=?", (bid,))
    if not b:
        return False
    db.run("INSERT INTO block_history(block_id,url,action,data,updated,user) VALUES(?,?,?,?,?,?)",
           (bid, b["url"], "удалил блок " + b["type"], b["data"], db.now(), user))
    db.run("UPDATE blocks SET deleted=1, updated=?, user=? WHERE id=?", (db.now(), user, bid))
    return True


def restore_block(bid, user):
    b = db.q1("SELECT * FROM blocks WHERE id=?", (bid,))
    if not b:
        return False
    db.run("UPDATE blocks SET deleted=0, updated=?, user=? WHERE id=?", (db.now(), user, bid))
    return True


# ---------- где используется запись базы ----------
def usage(kind, rid):
    """kind: people / docs / clubs. → [(url, заголовок страницы, id блока, подпись блока)]"""
    from .content import PAGES
    rid = int(rid)
    out = []
    for r in db.q("SELECT id, url, type, data FROM blocks WHERE type=? AND COALESCE(deleted,0)=0", (kind,)):
        d = json.loads(r["data"])
        ids = d.get("ids", []) if kind == "clubs" else [i for g in d.get("groups", []) for i in g.get("ids", [])]
        if kind == "clubs" and d.get("auto"):
            ids = [rid]  # блок с автоматическим списком показывает все кружки
        if rid in ids:
            out.append((r["url"], PAGES.get(r["url"], {}).get("title", r["url"]), r["id"], d.get("title") or ""))
    if kind == "people":
        for m in db.q("SELECT url, data FROM page_meta"):
            card = (json.loads(m["data"]).get("card") or {})
            if rid in (card.get("ids") or []):
                out.append((m["url"], PAGES.get(m["url"], {}).get("title", m["url"]), "card", card.get("title", "")))
    return out


def usage_counts(kind):
    cnt = {}
    for r in db.q("SELECT data FROM blocks WHERE type=? AND COALESCE(deleted,0)=0", (kind,)):
        d = json.loads(r["data"])
        ids = d.get("ids", []) if kind == "clubs" else [i for g in d.get("groups", []) for i in g.get("ids", [])]
        if kind == "clubs" and d.get("auto"):
            ids = [c["id"] for c in db.q("SELECT id FROM clubs")]
        for i in ids:
            cnt[i] = cnt.get(i, 0) + 1
    if kind == "people":
        for m in db.q("SELECT data FROM page_meta"):
            for i in (json.loads(m["data"]).get("card") or {}).get("ids") or []:
                cnt[i] = cnt.get(i, 0) + 1
    return cnt


def remove_everywhere(kind, rid, user):
    """Запись удалили из базы: убираем её из всех блоков, чтобы на страницах не осталось дыр."""
    rid = int(rid)
    for r in db.q("SELECT id, data FROM blocks WHERE type=?", (kind,)):
        d = json.loads(r["data"])
        changed = False
        if kind == "clubs":
            if rid in d.get("ids", []):
                d["ids"].remove(rid); changed = True
        else:
            for g in d.get("groups", []):
                if rid in g.get("ids", []):
                    g["ids"].remove(rid); changed = True
        if changed:
            save_block(r["id"], d, user, "убрал удалённую запись")
    if kind == "people":
        for m in db.q("SELECT url, data FROM page_meta"):
            meta = json.loads(m["data"])
            card = meta.get("card") or {}
            if rid in (card.get("ids") or []):
                card["ids"].remove(rid)
                save_meta(m["url"], meta, user)


def page_updated(url):
    r = db.q1("SELECT MAX(updated) u FROM (SELECT updated FROM blocks WHERE url=? UNION ALL SELECT updated FROM page_meta WHERE url=?)", (url, url))
    return (r or {}).get("u") or ""
