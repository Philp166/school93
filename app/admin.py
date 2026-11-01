"""Админка сайта школы №93: 8 разделов + журнал и пользователи."""
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import time
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image, ImageOps, UnidentifiedImageError

from . import db, content

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
UPLOADS = os.path.join(BASE, "static", "uploads")
FOOD_DIR = os.environ.get("S93_FOOD", os.path.join(ROOT, "food"))

router = APIRouter(prefix="/admin")
env = Environment(loader=FileSystemLoader(os.path.join(BASE, "templates", "admin")), autoescape=select_autoescape(["html"]))
env.tests["contains"] = lambda seq, x: x in (seq or [])
_M = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def _dh(s):
    try:
        y, m, d = map(int, str(s)[:10].split("-"))
        return f"{d} {_M[m-1]} {y}"
    except Exception:
        return s or ""


env.filters["dh"] = _dh

# ---------- секрет для подписи сессии ----------
_secret_path = os.path.join(ROOT, "data", "secret.key")


def _secret():
    os.makedirs(os.path.dirname(_secret_path), exist_ok=True)
    if not os.path.exists(_secret_path):
        with open(_secret_path, "w") as f:
            f.write(secrets.token_hex(32))
    return open(_secret_path).read().strip().encode()


def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(8)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000).hex()
    return f"{salt}${h}"


def check_pw(pw, stored):
    salt, h = stored.split("$", 1)
    return hmac.compare_digest(hash_pw(pw, salt), stored)


def sign(data: dict):
    raw = json.dumps(data, separators=(",", ":")).encode()
    sig = hmac.new(_secret(), raw, "sha256").hexdigest()
    return raw.hex() + "." + sig


def unsign(token):
    try:
        raw_hex, sig = token.split(".")
        raw = bytes.fromhex(raw_hex)
        if not hmac.compare_digest(hmac.new(_secret(), raw, "sha256").hexdigest(), sig):
            return None
        d = json.loads(raw)
        if d.get("exp", 0) < time.time():
            return None
        return d
    except Exception:
        return None


def current_user(request):
    tok = request.cookies.get("s93")
    d = unsign(tok) if tok else None
    if not d:
        return None
    u = db.q1("SELECT id, login, name, role, pw, COALESCE(active,1) active FROM users WHERE id=?", (d["uid"],))
    if not u or not u["active"] or d.get("pv") != u["pw"][-12:]:
        return None  # пользователя удалили или сменили пароль: старая сессия больше не действует
    del u["pw"]
    u["csrf"] = d["csrf"]
    return u


# ---------- вход в два шага: пароль, потом код из приложения ----------
from . import twofa  # noqa: E402

PENDING_MIN = 10


def _pending(request):
    tok = request.cookies.get("s93p")
    d = unsign(tok) if tok else None
    if not d:
        return None, None
    u = db.q1("SELECT * FROM users WHERE id=?", (d.get("uid"),))
    if not u or not u.get("active", 1) or d.get("pv") != u["pw"][-12:]:
        return None, None
    return u, d


def _start_session(request, u, to="/admin/pages"):
    r = RedirectResponse(to, status_code=303)
    r.set_cookie("s93", sign({"uid": u["id"], "csrf": secrets.token_hex(16), "pv": u["pw"][-12:], "exp": time.time() + 14 * 86400}),
                 httponly=True, samesite="lax", max_age=14 * 86400, secure=request.url.scheme == "https")
    r.delete_cookie("s93p")
    db.run("UPDATE users SET last_login=? WHERE id=?", (db.now(), u["id"]))
    db.log(u["name"], "Вход", "вход", "")
    return r


def _code_fail(key):
    db.run("CREATE TABLE IF NOT EXISTS login_fails(key TEXT PRIMARY KEY, fails INTEGER, locked_until TEXT)")
    lf = db.q1("SELECT * FROM login_fails WHERE key=?", (key,))
    fails = (lf["fails"] if lf else 0) + 1
    lock = (datetime.now() + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M") if fails >= 5 else None
    db.run("INSERT INTO login_fails(key,fails,locked_until) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET fails=excluded.fails, locked_until=excluded.locked_until",
           (key, 0 if lock else fails, lock))


def _code_locked(key):
    db.run("CREATE TABLE IF NOT EXISTS login_fails(key TEXT PRIMARY KEY, fails INTEGER, locked_until TEXT)")
    lf = db.q1("SELECT * FROM login_fails WHERE key=?", (key,))
    return bool(lf and lf["locked_until"] and lf["locked_until"] > db.now())


# ---------- маршруты данных: где появится на сайте ----------
ROUTES = {
    "news": [("Лента новостей", "/novosti"), ("Главная", "/"), ("Кванториум", "/kvantorium"), ("Блок «Ещё новости» внизу статей", None)],
    "docs": [("Блоки «Документы» на отмеченных страницах", None)],
    "food": [("Питание", "/roditelyam/pitanie"), ("Сведения: питание", "/sveden/catering"), ("Папка для мониторинга", "/food/")],
    "admission": [("Главная", "/"), ("Приём в 1 класс", "/postuplenie/1-klass"), ("Приём в 10 класс", "/postuplenie/10-klass"), ("Свободные места", "/sveden/vacant"), ("Лагерь", "/zhizn/lager")],
    "people": [("Администрация", "/o-shkole/administratsiya"), ("Помощь и службы", "/roditelyam/sluzhby"), ("Кванториум", "/kvantorium"), ("Сведения: руководство", "/sveden/managers"), ("Сведения: педсостав", "/sveden/employees")],
    "contacts": [("Подвал и меню всех страниц", "/"), ("Контакты", "/o-shkole/kontakty"), ("Администрация", "/o-shkole/administratsiya"), ("Сведения: основные", "/sveden/common")],
    "clubs": [("Кружки и секции", "/zhizn/kruzhki"), ("Кванториум", "/kvantorium")],
    "vacancies": [("Вакансии", "/o-shkole/vakansii")],
}
SECTIONS = [("pages", "Страницы"), ("news", "Новости"), ("docs", "Документы"), ("food", "Питание"), ("admission", "Приём"),
            ("people", "Люди"), ("contacts", "Контакты школы"), ("clubs", "Кружки"), ("vacancies", "Вакансии")]


def render(request, tpl, user, section=None, **kw):
    counts = {"news": db.q1("SELECT COUNT(*) c FROM news")["c"], "docs": db.q1("SELECT COUNT(*) c FROM docs")["c"],
              "people": db.q1("SELECT COUNT(*) c FROM people")["c"], "clubs": db.q1("SELECT COUNT(*) c FROM clubs")["c"],
              "vacancies": db.q1("SELECT COUNT(*) c FROM vacancies WHERE active=1")["c"]}
    ok = request.query_params.get("ok")
    return HTMLResponse(env.get_template(tpl).render(u=user, section=section, SECTIONS=SECTIONS, ROUTES=ROUTES, counts=counts,
                                                      ok=ok, today=date.today().isoformat(), C=content, **kw))


def need_user(request, role=None):
    u = current_user(request)
    if not u or (role and u["role"] != role):
        return None
    return u


async def form_of(request, user):
    f = await request.form()
    if f.get("csrf") != user["csrf"]:
        raise PermissionError("csrf")
    return f


def back(path, ok="saved"):
    return RedirectResponse(f"{path}{'&' if '?' in path else '?'}ok={ok}", status_code=303)


def drop_upload(path):
    """Удалить загруженный файл, если на него больше ничего не ссылается (чтобы не копились сироты)."""
    if not path or not str(path).startswith("/static/uploads/"):
        return
    used = db.q1("SELECT 1 x FROM news WHERE cover=? OR body LIKE ? UNION SELECT 1 FROM people WHERE photo=? LIMIT 1", (path, f"%{path}%", path))
    if not used:
        rel = path[len("/static/uploads/"):]
        if ".." in rel:
            return
        try:
            os.remove(os.path.join(UPLOADS, *rel.split("/")))
        except OSError:
            pass


def slugify(s):
    tr = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя", ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u", "f", "h", "c", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"]))
    s = "".join(tr.get(ch, ch) for ch in s.lower())
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:70] or "novost"


def save_image(up: UploadFile, max_w=1600):
    if not hasattr(up, "file"):
        return None
    data = up.file.read()
    if not data:
        return None
    if len(data) > 25 * 1024 * 1024:
        raise ValueError("Файл больше 25 МБ")
    try:
        im = Image.open(io.BytesIO(data))
        im = ImageOps.exif_transpose(im)  # фото с телефона иначе ложится на бок
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError("Это не картинка или файл повреждён")
    im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB")
    if im.width > max_w:
        im = im.resize((max_w, int(im.height * max_w / im.width)), Image.LANCZOS)
    name = f"{datetime.now():%Y%m%d%H%M%S}-{secrets.token_hex(3)}.webp"
    os.makedirs(UPLOADS, exist_ok=True)
    im.save(os.path.join(UPLOADS, name), "WEBP", quality=82, method=6)
    return f"/static/uploads/{name}"


def safe_url_admin(u):
    import re as _re
    s = (u or "").strip()
    return bool(_re.match(r"^(https?:|/)", s, _re.I)) and not s.startswith("//")


def kind_of(url):
    u = (url or "").lower()
    for ext in ("pdf", "docx", "doc", "xlsx", "xls", "pptx", "zip"):
        if u.split("?")[0].endswith("." + ext):
            return ext.upper().replace("DOCX", "DOC").replace("XLSX", "XLS")
    if "disk.yandex" in u or "yadi.sk" in u:
        return "Яндекс.Диск"
    if "cloud.mail" in u:
        return "Облако Mail"
    return "Ссылка"


# =================== вход ===================
@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return HTMLResponse(env.get_template("login.html").render(err=request.query_params.get("err")))


_DUMMY = hash_pw("dummy")


def _client_ip(request):
    return request.client.host if request.client else "?"


@router.post("/login")
async def login(request: Request):
    """Блокировка по паре «логин + адрес», чтобы чужой человек не мог запереть админку школы пятью неверными паролями."""
    f = await request.form()
    login_ = f.get("login", "").strip().lower()
    key = f"{login_}|{_client_ip(request)}"
    db.run("CREATE TABLE IF NOT EXISTS login_fails(key TEXT PRIMARY KEY, fails INTEGER, locked_until TEXT)")
    lf = db.q1("SELECT * FROM login_fails WHERE key=?", (key,))
    if lf and lf["locked_until"] and lf["locked_until"] > db.now():
        return RedirectResponse("/admin/login?err=locked", status_code=303)
    u = db.q1("SELECT * FROM users WHERE login=?", (login_,))
    ok = check_pw(f.get("password", ""), u["pw"] if u else _DUMMY) and u is not None  # время ответа одинаковое
    if not ok:
        fails = (lf["fails"] if lf else 0) + 1
        lock = (datetime.now() + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M") if fails >= 5 else None
        db.run("INSERT INTO login_fails(key,fails,locked_until) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET fails=excluded.fails, locked_until=excluded.locked_until",
               (key, 0 if lock else fails, lock))
        return RedirectResponse("/admin/login?err=1", status_code=303)
    if not u.get("active", 1):
        return RedirectResponse("/admin/login?err=blocked", status_code=303)
    db.run("DELETE FROM login_fails WHERE key=?", (key,))
    # пароль верный: дальше код из приложения (или настройка приложения при первом входе)
    nxt = "/admin/login/code" if u.get("totp_on") else "/admin/login/setup"
    r = RedirectResponse(nxt, status_code=303)
    r.set_cookie("s93p", sign({"uid": u["id"], "pv": u["pw"][-12:], "exp": time.time() + PENDING_MIN * 60}),
                 httponly=True, samesite="lax", max_age=PENDING_MIN * 60, secure=request.url.scheme == "https")
    return r


@router.get("/login/code", response_class=HTMLResponse)
def login_code_page(request: Request):
    u, _ = _pending(request)
    if not u:
        return RedirectResponse("/admin/login?err=expired", status_code=303)
    if not u.get("totp_on"):
        return RedirectResponse("/admin/login/setup", status_code=303)
    return HTMLResponse(env.get_template("login_code.html").render(err=request.query_params.get("err"), name=u["name"],
                                                                   rec=request.query_params.get("rec")))


@router.post("/login/code")
async def login_code(request: Request):
    u, _ = _pending(request)
    if not u:
        return RedirectResponse("/admin/login?err=expired", status_code=303)
    f = await request.form()
    key = f"code:{u['id']}|{_client_ip(request)}"
    if _code_locked(key):
        return RedirectResponse("/admin/login/code?err=locked", status_code=303)
    code = (f.get("code") or "").strip()
    step = twofa.verify(u.get("totp_secret"), code, u.get("totp_last") or 0)
    if step:
        db.run("UPDATE users SET totp_last=? WHERE id=?", (step, u["id"]))
        db.run("DELETE FROM login_fails WHERE key=?", (key,))
        return _start_session(request, u)
    rec = json.loads(u.get("recovery") or "[]")
    h = twofa.hash_code(code)
    if code and h in rec:  # резервный код: срабатывает один раз
        rec.remove(h)
        db.run("UPDATE users SET recovery=? WHERE id=?", (json.dumps(rec), u["id"]))
        db.run("DELETE FROM login_fails WHERE key=?", (key,))
        db.log(u["name"], "Вход", "вход по резервному коду", f"осталось кодов: {len(rec)}")
        return _start_session(request, u, "/admin/me?ok=reccode")
    _code_fail(key)
    return RedirectResponse("/admin/login/code?err=1" + ("&rec=1" if f.get("rec") else ""), status_code=303)


@router.get("/login/setup", response_class=HTMLResponse)
def login_setup_page(request: Request):
    u, _ = _pending(request)
    if not u:
        return RedirectResponse("/admin/login?err=expired", status_code=303)
    if u.get("totp_on"):
        return RedirectResponse("/admin/login/code", status_code=303)
    secret = u.get("totp_secret")
    if not secret:
        secret = twofa.new_secret()
        db.run("UPDATE users SET totp_secret=? WHERE id=?", (secret, u["id"]))
    return HTMLResponse(env.get_template("login_setup.html").render(err=request.query_params.get("err"), name=u["name"],
                                                                    qr=twofa.qr_svg(twofa.uri(secret, u["login"])),
                                                                    key=" ".join(secret[i:i + 4] for i in range(0, len(secret), 4))))


@router.post("/login/setup")
async def login_setup(request: Request):
    u, _ = _pending(request)
    if not u:
        return RedirectResponse("/admin/login?err=expired", status_code=303)
    f = await request.form()
    key = f"code:{u['id']}|{_client_ip(request)}"
    if _code_locked(key):
        return RedirectResponse("/admin/login/setup?err=locked", status_code=303)
    step = twofa.verify(u.get("totp_secret"), f.get("code"), 0)
    if not step:
        _code_fail(key)
        return RedirectResponse("/admin/login/setup?err=1", status_code=303)
    codes = twofa.new_recovery()
    db.run("UPDATE users SET totp_on=1, totp_last=?, recovery=? WHERE id=?", (step, json.dumps([twofa.hash_code(c) for c in codes]), u["id"]))
    db.log(u["name"], "Вход", "подключил приложение-ключ", "")
    r = _start_session(request, u, "/admin/login/codes")
    r.set_cookie("s93rc", sign({"uid": u["id"], "codes": codes, "exp": time.time() + 600}), httponly=True, samesite="lax", max_age=600,
                 secure=request.url.scheme == "https")
    return r


@router.get("/login/codes", response_class=HTMLResponse)
def login_codes(request: Request):
    u = current_user(request)
    d = unsign(request.cookies.get("s93rc") or "") if request.cookies.get("s93rc") else None
    if not u or not d or d.get("uid") != u["id"]:
        return RedirectResponse("/admin/pages", status_code=303)
    r = HTMLResponse(env.get_template("login_codes.html").render(codes=d["codes"], name=u["name"]))
    r.delete_cookie("s93rc")  # коды показываются один раз
    return r


@router.get("/logout")
def logout():
    r = RedirectResponse("/admin/login", status_code=303)
    r.delete_cookie("s93")
    r.delete_cookie("s93p")
    return r


def guard(request, role=None):
    u = need_user(request, role)
    if not u:
        return None, RedirectResponse("/admin/login", status_code=303)
    return u, None


# =================== главная админки ===================
@router.get("")
@router.get("/")
def dashboard(request: Request):
    u, r = guard(request)
    if r:
        return r
    return RedirectResponse("/admin/pages", status_code=303)


# =================== 1. новости ===================
@router.get("/news", response_class=HTMLResponse)
def news_list(request: Request):
    u, r = guard(request)
    if r:
        return r
    qs, rub = request.query_params.get("q", "").strip(), request.query_params.get("r", "")
    sql, args = "SELECT * FROM news WHERE 1=1", []
    if qs:
        sql += " AND (title LIKE ? OR lead LIKE ?)"
        args += [f"%{qs}%", f"%{qs}%"]
    if rub:
        sql += " AND rubric=?"
        args.append(rub)
    approx = request.query_params.get("approx")
    if approx:
        sql += " AND date_exact=0"
    rows = db.q(sql + " ORDER BY date DESC, id DESC", args)
    return render(request, "news_list.html", u, "news", rows=rows, qs=qs, rub=rub, approx=approx,
                  n_approx=db.q1("SELECT COUNT(*) c FROM news WHERE date_exact=0")["c"])


@router.get("/news/{nid}", response_class=HTMLResponse)
def news_edit(nid: str, request: Request):
    u, r = guard(request)
    if r:
        return r
    n = db.q1("SELECT * FROM news WHERE id=?", (nid,)) if nid != "new" else {"id": None, "date": date.today().isoformat(), "rubric": "Школа", "published": 1}
    return render(request, "news_edit.html", u, "news", n=n)


@router.post("/news/{nid}")
async def news_save(nid: str, request: Request):
    u, r = guard(request)
    if r:
        return r
    f = await form_of(request, u)
    if f.get("delete"):
        old = db.q1("SELECT cover, body FROM news WHERE id=?", (nid,)) or {}
        db.run("DELETE FROM news WHERE id=?", (nid,))
        drop_upload(old.get("cover"))
        for pth in re.findall(r"/static/uploads/\S+", old.get("body") or ""):
            drop_upload(pth)
        db.log(u["name"], "Новости", "удалил", f.get("title", ""))
        return back("/admin/news", "deleted")
    cover = f.get("cover_old") or None
    up = f.get("cover")
    if hasattr(up, "filename") and up.filename:
        try:
            cover = save_image(up)
        except ValueError:
            return back(f"/admin/news/{nid}", "badimg")
    if f.get("cover_remove"):
        cover = None
    title = f.get("title", "").strip()
    vals = (title, f.get("date") or date.today().isoformat(), f.get("rubric"), f.get("lead", "").strip(), cover,
            f.get("body", ""), f.get("vk", "").strip(), 1 if f.get("published") else 0, db.now())
    if nid == "new":
        slug = slugify(title)
        if db.q1("SELECT id FROM news WHERE slug=?", (slug,)):
            slug += "-" + secrets.token_hex(2)
        nid = db.run("INSERT INTO news(title,date,rubric,lead,cover,body,vk,published,updated,slug) VALUES(?,?,?,?,?,?,?,?,?,?)", vals + (slug,))
        db.log(u["name"], "Новости", "добавил", title)
    else:
        db.run("UPDATE news SET title=?,date=?,rubric=?,lead=?,cover=?,body=?,vk=?,published=?,updated=?,date_exact=1 WHERE id=?", vals + (nid,))
        db.log(u["name"], "Новости", "изменил", title)
    if f.get("view"):
        n = db.q1("SELECT slug FROM news WHERE id=?", (nid,))
        return RedirectResponse(f"/novosti/{n['slug']}", status_code=303)
    return back(f"/admin/news/{nid}")


@router.post("/upload-image")
async def upload_image(request: Request):
    """Картинка в текст новости: возвращает путь, JS вставляет его отдельной строкой."""
    u = current_user(request)
    if not u:
        return JSONResponse({"error": "auth"}, status_code=401)
    f = await request.form()
    if f.get("csrf") != u["csrf"]:
        return JSONResponse({"error": "csrf"}, status_code=403)
    try:
        url = save_image(f.get("file"))
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"url": url} if url else {"error": "Файл не выбран"}, status_code=200 if url else 400)


# =================== 2. документы ===================
@router.get("/docs", response_class=HTMLResponse)
def docs_list(request: Request):
    from . import blocks_store as bs
    u, r = guard(request)
    if r:
        return r
    qs = request.query_params.get("q", "").strip()
    rows = db.q("SELECT * FROM docs ORDER BY id DESC")
    if qs:  # ищем и по названию документа, и по странице, где он стоит
        ql = qs.lower()
        page_ids = set()
        for url_, t_ in content.DOC_PAGES:
            if ql in t_.lower():
                for b in db.q("SELECT data FROM blocks WHERE url=? AND type='docs'", (url_,)):
                    for g in json.loads(b["data"]).get("groups", []):
                        page_ids.update(g.get("ids", []))
        rows = [x for x in rows if ql in (x["title"] or "").lower() or x["id"] in page_ids]
    cnt = bs.usage_counts("docs")
    for x in rows:
        x["used"] = cnt.get(x["id"], 0)
    unused = sum(1 for x in db.q("SELECT id FROM docs") if not cnt.get(x["id"]))
    if request.query_params.get("unused"):
        rows = [x for x in rows if not x["used"]]
    return render(request, "docs_list.html", u, "docs", rows=rows, qs=qs, total=db.q1("SELECT COUNT(*) c FROM docs")["c"], unused=unused,
                  only_unused=request.query_params.get("unused"))


@router.get("/docs/{did}", response_class=HTMLResponse)
def docs_edit(did: str, request: Request):
    from . import blocks_store as bs
    u, r = guard(request)
    if r:
        return r
    d = db.q1("SELECT * FROM docs WHERE id=?", (did,)) if did != "new" else {"id": None}
    if d is None:
        return RedirectResponse("/admin/docs", status_code=303)
    return render(request, "docs_edit.html", u, "docs", d=d, usage=bs.usage("docs", did) if d.get("id") else [])


@router.post("/docs/{did}")
async def docs_save(did: str, request: Request):
    from . import blocks_store as bs
    u, r = guard(request)
    if r:
        return r
    f = await form_of(request, u)
    if f.get("delete") and did != "new":
        bs.remove_everywhere("docs", did, u["name"])  # со страниц убираем, чтобы не осталось пустых мест
        db.run("DELETE FROM doc_places WHERE doc_id=?", (did,))
        db.run("DELETE FROM docs WHERE id=?", (did,))
        db.log(u["name"], "Документы", "удалил", f.get("title", ""))
        return back("/admin/docs", "deleted")
    title, url = f.get("title", "").strip(), f.get("url", "").strip()
    if not safe_url_admin(url):
        return back(f"/admin/docs/{did}", "badurl")
    main_doc = 1 if f.get("main_doc") else 0
    if did == "new":
        did = db.run("INSERT INTO docs(title,url,kind,updated,main_doc) VALUES(?,?,?,?,?)", (title, url, kind_of(url), db.now(), main_doc))
        db.log(u["name"], "Документы", "добавил", title)
    else:
        db.run("UPDATE docs SET title=?,url=?,kind=?,updated=?,main_doc=? WHERE id=?", (title, url, kind_of(url), db.now(), main_doc, did))
        db.log(u["name"], "Документы", "изменил", title)
    return back(f"/admin/docs/{did}")


@router.get("/food", response_class=HTMLResponse)
def food(request: Request):
    u, r = guard(request)
    if r:
        return r
    rows = db.q("SELECT * FROM food_files ORDER BY uploaded DESC LIMIT 40")
    return render(request, "food.html", u, "food", rows=rows, prices=db.get_setting("food_prices", []),
                  pattern=db.get_setting("food_pattern", {"g1": "{date}-sm.xlsx", "g2": "{date}-sm-2.xlsx"}))


@router.post("/food/upload")
async def food_upload(request: Request):
    u, r = guard(request)
    if r:
        return r
    f = await form_of(request, u)
    os.makedirs(FOOD_DIR, exist_ok=True)
    pattern = db.get_setting("food_pattern", {"g1": "{date}-sm.xlsx", "g2": "{date}-sm-2.xlsx"})
    d = f.get("date") or date.today().isoformat()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
        return back("/admin/food", "baddate")
    saved = 0
    for key, label in (("g1", "Меню на сегодня, 7–11 лет"), ("g2", "Меню на сегодня, 12–18 лет")):
        up = f.get(key)
        if hasattr(up, "filename") and up.filename:
            name = pattern[key].format(date=d)
            with open(os.path.join(FOOD_DIR, name), "wb") as out:
                out.write(up.file.read())
            db.run("DELETE FROM food_files WHERE filename=?", (name,))
            db.run("INSERT INTO food_files(kind,label,filename,uploaded) VALUES('today',?,?,?)", (label, name, db.now()))
            saved += 1
    for i, label in enumerate(["Горячее питание, 7–11 лет", "Горячее питание, 12–18 лет", "Кадеты, 5–8 классы", "Кадеты, 9–11 классы"], 1):
        up = f.get(f"c{i}")
        if hasattr(up, "filename") and up.filename:
            name = f"cycle-{i}.xlsx"
            with open(os.path.join(FOOD_DIR, name), "wb") as out:
                out.write(up.file.read())
            db.run("DELETE FROM food_files WHERE filename=?", (name,))
            db.run("INSERT INTO food_files(kind,label,filename,uploaded) VALUES('cycle',?,?,?)", (label, name, db.now()))
            saved += 1
    db.log(u["name"], "Питание", f"загрузил файлы ({saved})", d)
    return back("/admin/food", f"up{saved}")


@router.post("/food/prices")
async def food_prices(request: Request):
    u, r = guard(request)
    if r:
        return r
    f = await form_of(request, u)
    rows = [(a.strip(), b.strip()) for a, b in zip(f.getlist("pa"), f.getlist("pb")) if a.strip()]
    db.set_setting("food_prices", rows)
    db.log(u["name"], "Питание", "изменил цены", "")
    return back("/admin/food")


# =================== 4. приём ===================
@router.get("/admission", response_class=HTMLResponse)
def admission(request: Request):
    u, r = guard(request)
    if r:
        return r
    return render(request, "admission.html", u, "admission", A=db.get_setting("admission", {}), L=db.get_setting("lager", {}))


@router.post("/admission/status")
async def admission_status(request: Request):
    """Статус приёма в 1 класс прямо со страницы в редакторе."""
    from fastapi.responses import JSONResponse
    u = current_user(request)
    if not u:
        return JSONResponse({"error": "auth"}, status_code=401)
    f = await request.form()
    if f.get("csrf") != u["csrf"] or f.get("status") not in ("soon", "open", "closed"):
        return JSONResponse({"error": "bad"}, status_code=400)
    A = db.get_setting("admission", {})
    A["status1"] = f.get("status")
    db.set_setting("admission", A)
    db.log(u["name"], "Приём", "изменил статус", {"soon": "скоро", "open": "идёт", "closed": "закрыт"}[f.get("status")])
    return JSONResponse({"ok": True})


@router.post("/admission")
async def admission_save(request: Request):
    u, r = guard(request)
    if r:
        return r
    f = await form_of(request, u)
    A = db.get_setting("admission", {})
    for k in ("status1", "year1", "open_date", "open_text", "closed_text", "soon_text", "year10", "classes10", "seats10"):
        if k in f:
            A[k] = f.get(k, "").strip()
    for k in ("classes10", "seats10"):  # только числа: буквы здесь уронили бы карточку на странице
        A[k] = re.sub(r"\D", "", A.get(k, ""))
    A["dates10"] = [(a.strip(), b.strip()) for a, b in zip(f.getlist("dw"), f.getlist("dd")) if a.strip()]
    A["vacant"] = [[c.strip(), f1.strip(), f2.strip(), f3.strip(), f4.strip()] for c, f1, f2, f3, f4 in
                   zip(f.getlist("vc"), f.getlist("v1"), f.getlist("v2"), f.getlist("v3"), f.getlist("v4")) if c.strip()]
    db.set_setting("admission", A)
    L = {k: f.get("l_" + k, "").strip() for k in ("shift", "dates", "seats", "price_full", "price_part", "price_free")}
    db.set_setting("lager", L)
    db.log(u["name"], "Приём", "изменил", {"open": "приём идёт", "closed": "приём закрыт"}.get(A.get("status1"), "скоро"))
    return back("/admin/admission")


# =================== 5. люди ===================
@router.get("/people", response_class=HTMLResponse)
def people_list(request: Request):
    from . import blocks_store as bs
    u, r = guard(request)
    if r:
        return r
    qs = request.query_params.get("q", "").strip()
    rows = db.q("SELECT * FROM people ORDER BY name")
    if qs:
        ql = qs.lower()
        rows = [x for x in rows if ql in (x["name"] + " " + (x["position"] or "") + " " + (x["building"] or "")).lower()]
    cnt = bs.usage_counts("people")
    for x in rows:
        x["used"] = cnt.get(x["id"], 0)
    if request.query_params.get("unused"):
        rows = [x for x in rows if not x["used"]]
    unused = sum(1 for x in db.q("SELECT id FROM people") if not cnt.get(x["id"]))
    return render(request, "people_list.html", u, "people", rows=rows, qs=qs, unused=unused, only_unused=request.query_params.get("unused"))


@router.get("/people/{pid}", response_class=HTMLResponse)
def people_edit(pid: str, request: Request):
    from . import blocks_store as bs
    u, r = guard(request)
    if r:
        return r
    x = db.q1("SELECT * FROM people WHERE id=?", (pid,)) if pid != "new" else {"id": None, "pos": 100}
    if x is None:
        return RedirectResponse("/admin/people", status_code=303)
    return render(request, "people_edit.html", u, "people", x=x, usage=bs.usage("people", pid) if x.get("id") else [])


@router.post("/people/{pid}")
async def people_save(pid: str, request: Request):
    from . import blocks_store as bs
    u, r = guard(request)
    if r:
        return r
    f = await form_of(request, u)
    if f.get("delete") and pid != "new":
        old = db.q1("SELECT photo FROM people WHERE id=?", (pid,)) or {}
        bs.remove_everywhere("people", pid, u["name"])  # со всех страниц, чтобы не осталось пустых карточек
        db.run("DELETE FROM people WHERE id=?", (pid,))
        drop_upload(old.get("photo"))
        db.log(u["name"], "Люди", "удалил", f.get("name", ""))
        return back("/admin/people", "deleted")
    photo = f.get("photo_old") or None
    up = f.get("photo")
    if hasattr(up, "filename") and up.filename:
        try:
            photo = save_image(up, 600)
        except ValueError:
            return back(f"/admin/people/{pid}", "badimg")
    if f.get("photo_remove"):
        photo = None
    vals = [f.get(k, "").strip() for k in ("name", "position", "duty", "phone", "email", "building", "edu", "qual", "experience", "subjects")]
    if pid == "new":
        pid = db.run("INSERT INTO people(name,position,duty,phone,email,building,edu,qual,experience,subjects,tags,pos,photo,updated) VALUES(?,?,?,?,?,?,?,?,?,?,'[]',100,?,?)",
                     (*vals, photo, db.now()))
        db.log(u["name"], "Люди", "добавил", vals[0])
    else:
        db.run("UPDATE people SET name=?,position=?,duty=?,phone=?,email=?,building=?,edu=?,qual=?,experience=?,subjects=?,photo=?,updated=? WHERE id=?",
               (*vals, photo, db.now(), pid))
        db.log(u["name"], "Люди", "изменил", vals[0])
    return back(f"/admin/people/{pid}")


# =================== 6. контакты школы ===================
@router.get("/contacts", response_class=HTMLResponse)
def contacts(request: Request):
    u, r = guard(request)
    if r:
        return r
    return render(request, "contacts.html", u, "contacts", Cs=db.get_setting("contacts", {}), O=db.get_setting("odod", {}))


@router.post("/contacts")
async def contacts_save(request: Request):
    u, r = guard(request)
    if r:
        return r
    f = await form_of(request, u)
    C = db.get_setting("contacts", {})
    for k in ("full_name", "short_name", "created", "legal_address", "email", "hours", "reception", "hotline",
              "director_day", "director_time", "director_place", "pos_widget"):
        if k == "pos_widget" and u["role"] != "admin":
            continue  # код виджета попадает на все страницы как есть
        C[k] = f.get(k, "").strip()
    C["buildings"] = []
    for i in (0, 1):
        C["buildings"].append({"address": f.get(f"b{i}_address", "").strip(), "address_full": f.get(f"b{i}_full", "").strip(),
                               "phone": f.get(f"b{i}_phone", "").strip(), "room": f.get(f"b{i}_room", "").strip(),
                               "extra": [f.get(f"b{i}_xa", "").strip(), f.get(f"b{i}_xb", "").strip()] if f.get(f"b{i}_xa", "").strip() else None,
                               "safe_route": f.get(f"b{i}_route", "").strip()})
    C["founders"] = [(a.strip(), b.strip()) for a, b in zip(f.getlist("fa"), f.getlist("fb")) if a.strip()]
    C["requisites"] = [(a.strip(), b.strip()) for a, b in zip(f.getlist("ra"), f.getlist("rb")) if a.strip()]
    db.set_setting("contacts", C)
    db.set_setting("odod", {"hours": f.get("o_hours", "").strip(), "reception": f.get("o_reception", "").strip(), "phone": f.get("o_phone", "").strip()})
    db.log(u["name"], "Контакты школы", "изменил", "")
    return back("/admin/contacts")


# =================== 7. кружки ===================
@router.get("/clubs", response_class=HTMLResponse)
def clubs(request: Request):
    u, r = guard(request)
    if r:
        return r
    teachers = [x["name"] for x in db.q("SELECT name FROM people ORDER BY name")]
    return render(request, "clubs.html", u, "clubs", rows=db.q("SELECT * FROM clubs ORDER BY pos, title"), teachers=teachers,
                  edit=request.query_params.get("edit"))


@router.post("/clubs")
async def clubs_save(request: Request):
    u, r = guard(request)
    if r:
        return r
    f = await form_of(request, u)
    cid = f.get("id")
    if f.get("delete") and cid:
        from . import blocks_store as bs
        bs.remove_everywhere("clubs", cid, u["name"])
        db.run("DELETE FROM clubs WHERE id=?", (cid,))
        db.log(u["name"], "Кружки", "удалил", f.get("title", ""))
        return back("/admin/clubs", "deleted")
    vals = [f.get(k, "").strip() for k in ("title", "direction", "age", "building", "teacher", "schedule")] + [1 if f.get("kvant") else 0]
    if cid:
        db.run("UPDATE clubs SET title=?,direction=?,age=?,building=?,teacher=?,schedule=?,kvant=? WHERE id=?", (*vals, cid))
        db.log(u["name"], "Кружки", "изменил", vals[0])
    else:
        db.run("INSERT INTO clubs(title,direction,age,building,teacher,schedule,kvant) VALUES(?,?,?,?,?,?,?)", vals)
        db.log(u["name"], "Кружки", "добавил", vals[0])
    return back("/admin/clubs")


# =================== 8. вакансии ===================
@router.get("/vacancies", response_class=HTMLResponse)
def vacancies(request: Request):
    u, r = guard(request)
    if r:
        return r
    return render(request, "vacancies.html", u, "vacancies", rows=db.q("SELECT * FROM vacancies ORDER BY active DESC, id DESC"))


@router.post("/vacancies")
async def vacancies_save(request: Request):
    u, r = guard(request)
    if r:
        return r
    f = await form_of(request, u)
    act = f.get("act")
    if act == "add" and f.get("title", "").strip():
        db.run("INSERT INTO vacancies(title,building,contact,active) VALUES(?,?,?,1)", (f.get("title").strip(), f.get("building", ""), f.get("contact", "").strip()))
        db.log(u["name"], "Вакансии", "добавил", f.get("title"))
    elif act == "toggle":
        db.run("UPDATE vacancies SET active=1-active WHERE id=?", (f.get("id"),))
        db.log(u["name"], "Вакансии", "переключил", f.get("title", ""))
    elif act == "delete":
        db.run("DELETE FROM vacancies WHERE id=?", (f.get("id"),))
        db.log(u["name"], "Вакансии", "удалил", f.get("title", ""))
    return back("/admin/vacancies")


# =================== журнал и пользователи ===================
@router.get("/journal", response_class=HTMLResponse)
def journal(request: Request):
    u, r = guard(request)
    if r:
        return r
    return render(request, "journal.html", u, "journal", rows=db.q("SELECT * FROM journal ORDER BY id DESC LIMIT 300"))


@router.get("/users", response_class=HTMLResponse)
def users(request: Request):
    u, r = guard(request, "admin")
    if r:
        return r
    rows = db.q("SELECT id, login, name, role, COALESCE(active,1) active, COALESCE(totp_on,0) totp_on, last_login, recovery FROM users ORDER BY active DESC, name")
    for x in rows:
        x["rec_left"] = len(json.loads(x.pop("recovery") or "[]"))
    return render(request, "users.html", u, "users", rows=rows, newpw=request.query_params.get("pw"), newlogin=request.query_params.get("login"))


def _admins_left(exclude_id):
    return db.q1("SELECT COUNT(*) c FROM users WHERE role='admin' AND COALESCE(active,1)=1 AND id<>?", (exclude_id,))["c"]


@router.post("/users")
async def users_save(request: Request):
    u, r = guard(request, "admin")
    if r:
        return r
    f = await form_of(request, u)
    act, uid = f.get("act"), f.get("id")
    target = db.q1("SELECT * FROM users WHERE id=?", (uid,)) if uid else None
    if act == "add":
        login_ = re.sub(r"[^a-z0-9._-]", "", (f.get("login") or "").strip().lower())
        name = (f.get("name") or "").strip()
        if not login_ or not name:
            return back("/admin/users", "badlogin")
        if f.get("role") not in ("editor", "admin"):
            return back("/admin/users", "badrole")
        pw = secrets.token_urlsafe(9)  # временный пароль: показываем один раз, человек сменит его в профиле
        try:
            db.run("INSERT INTO users(login,name,role,pw,active) VALUES(?,?,?,?,1)", (login_, name, f.get("role"), hash_pw(pw)))
        except Exception:
            return back("/admin/users", "exists")
        db.log(u["name"], "Пользователи", "добавил", f"{name} ({login_})")
        return RedirectResponse(f"/admin/users?ok=added&login={login_}&pw={pw}", status_code=303)
    if not target:
        return back("/admin/users")
    me = str(target["id"]) == str(u["id"])
    if act == "newpw":
        pw = secrets.token_urlsafe(9)
        db.run("UPDATE users SET pw=? WHERE id=?", (hash_pw(pw), target["id"]))  # старые входы этого человека перестают действовать
        db.log(u["name"], "Пользователи", "выдал новый пароль", target["login"])
        return RedirectResponse(f"/admin/users?ok=newpw&login={target['login']}&pw={pw}", status_code=303)
    if act == "reset2fa":
        db.run("UPDATE users SET totp_on=0, totp_secret=NULL, totp_last=0, recovery=NULL WHERE id=?", (target["id"],))
        db.log(u["name"], "Пользователи", "сбросил приложение-ключ", target["login"])
        return back("/admin/users", "reset2fa")
    if act == "role" and f.get("role") in ("editor", "admin") and not me:
        if target["role"] == "admin" and f.get("role") != "admin" and not _admins_left(target["id"]):
            return back("/admin/users", "lastadmin")
        db.run("UPDATE users SET role=? WHERE id=?", (f.get("role"), target["id"]))
        db.log(u["name"], "Пользователи", "сменил роль", f'{target["login"]}: {f.get("role")}')
        return back("/admin/users")
    if act in ("block", "unblock") and not me:
        if act == "block" and target["role"] == "admin" and not _admins_left(target["id"]):
            return back("/admin/users", "lastadmin")
        db.run("UPDATE users SET active=? WHERE id=?", (0 if act == "block" else 1, target["id"]))
        db.log(u["name"], "Пользователи", "заблокировал" if act == "block" else "разблокировал", target["login"])
        return back("/admin/users")
    if act == "delete" and not me:
        if target["role"] == "admin" and not _admins_left(target["id"]):
            return back("/admin/users", "lastadmin")
        db.run("DELETE FROM users WHERE id=?", (target["id"],))
        db.log(u["name"], "Пользователи", "удалил", target["login"])
        return back("/admin/users", "deleted")
    return back("/admin/users")


# ---------- мой профиль: пароль и резервные коды ----------
@router.get("/me", response_class=HTMLResponse)
def me(request: Request):
    u, r = guard(request)
    if r:
        return r
    x = db.q1("SELECT login, name, role, last_login, recovery FROM users WHERE id=?", (u["id"],))
    d = unsign(request.cookies.get("s93rc") or "") if request.cookies.get("s93rc") else None
    codes = d["codes"] if d and d.get("uid") == u["id"] else None
    resp = render(request, "me.html", u, "me", x=x, rec_left=len(json.loads(x["recovery"] or "[]")), codes=codes)
    if codes:
        resp.delete_cookie("s93rc")
    return resp


@router.post("/me")
async def me_save(request: Request):
    u, r = guard(request)
    if r:
        return r
    f = await form_of(request, u)
    x = db.q1("SELECT * FROM users WHERE id=?", (u["id"],))
    if f.get("act") == "pw":
        if not check_pw(f.get("old", ""), x["pw"]):
            return back("/admin/me", "badold")
        if len(f.get("new", "")) < 8:
            return back("/admin/me", "shortpw")
        if f.get("new") != f.get("new2"):
            return back("/admin/me", "mismatch")
        db.run("UPDATE users SET pw=? WHERE id=?", (hash_pw(f.get("new")), u["id"]))
        db.log(u["name"], "Пользователи", "сменил свой пароль", "")
        nx = db.q1("SELECT * FROM users WHERE id=?", (u["id"],))
        return _start_session(request, nx, "/admin/me?ok=pw")  # остальные входы с другого устройства закрываются
    if f.get("act") == "codes":
        if not twofa.verify(x.get("totp_secret"), f.get("code"), x.get("totp_last") or 0):
            return back("/admin/me", "badcode")
        codes = twofa.new_recovery()
        db.run("UPDATE users SET recovery=? WHERE id=?", (json.dumps([twofa.hash_code(c) for c in codes]), u["id"]))
        db.log(u["name"], "Пользователи", "выпустил новые резервные коды", "")
        resp = RedirectResponse("/admin/me", status_code=303)
        resp.set_cookie("s93rc", sign({"uid": u["id"], "codes": codes, "exp": time.time() + 600}), httponly=True, samesite="lax", max_age=600,
                        secure=request.url.scheme == "https")
        return resp
    return back("/admin/me")
