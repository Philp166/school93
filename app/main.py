"""Сайт школы №93: публичная часть."""
import html
import json
from urllib.parse import quote
import os
import re
from datetime import date

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import db, content, blocks_store
from .content import PAGES, REDIRECTS, SECTIONS, NAV, MENU, SVEDEN, RUBRICS, SERVICE_INFO

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
FOOD_DIR = os.environ.get("S93_FOOD", os.path.join(ROOT, "food"))
UPLOADS = os.path.join(BASE, "static", "uploads")

env = Environment(loader=FileSystemLoader(os.path.join(BASE, "templates")), autoescape=select_autoescape(["html"]))
env.tests["contains"] = lambda seq, x: x in (seq or [])
env.globals.update(NAV=NAV, MENU=MENU, SVEDEN=SVEDEN)


def safe_url(u):
    """Ссылка из админки: только http(s), mailto, tel, адреса сайта и якоря. Всё прочее (javascript: и т.п.) глушим."""
    s = (u or "").strip()
    if re.match(r"^(https?:|mailto:|tel:|/|#|\?)", s, re.I) and not s.startswith("//"):
        return s
    return "#"


env.filters["safeurl"] = safe_url

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def date_h(s):
    try:
        y, m, d = map(int, s.split("-"))
        return f"{d} {MONTHS[m-1]} {y}"
    except Exception:
        return s or ""


def plural(n, forms):
    n = abs(n) % 100
    if 11 <= n <= 19:
        return forms[2]
    n %= 10
    return forms[0] if n == 1 else forms[1] if 2 <= n <= 4 else forms[2]


MONTHS_NOM = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]


def news_date(n):
    """Точная дата — «22 мая 2026», примерная (перенос со старого сайта) — только месяц и год."""
    if n.get("date_exact") == 0:
        try:
            y, mth = int(n["date"][:4]), int(n["date"][5:7])
            return f"{MONTHS_NOM[mth - 1]} {y}"
        except (ValueError, TypeError, IndexError):
            pass
    return date_h(n["date"])


def news(rubric=None, limit=3, offset=0):
    items = db.news_list(rubric, limit, offset)
    for n in items:
        n["date_h"] = news_date(n)
    return items


def people(tag, building=None):
    return db.people_by_tag(tag, building)


def clubs(kvant=False):
    # в Кванториуме только кружки с галочкой «Показывать в Кванториуме»
    if kvant:
        return db.q("SELECT * FROM clubs WHERE kvant=1 ORDER BY pos, title")
    return db.q("SELECT * FROM clubs ORDER BY pos, title")


def vacancies():
    return db.q("SELECT * FROM vacancies WHERE active=1 ORDER BY id")


def food_files():
    rows = db.q("SELECT * FROM food_files ORDER BY uploaded DESC")
    today = date.today().isoformat()
    t = [r for r in rows if r["kind"] == "today" and r["filename"].startswith(today)]
    day = today
    if not t:  # сегодняшнего нет: показываем последнее загруженное, но честно подписываем его дату
        last = [r for r in rows if r["kind"] == "today"]
        if last:
            day = last[0]["filename"][:10]
            t = [r for r in last if r["filename"].startswith(day)]
    return {"today": t, "is_today": day == today, "day_h": date_h(day), "cycle": [r for r in rows if r["kind"] == "cycle"]}


def settings():
    C = db.get_setting("contacts", {})
    for b_ in C.get("buildings", []):
        b_["phone_line"] = f'{b_["phone"]}, {b_["address"]}'
    return C


LOCK_BY_TYPE = {
    "feed": ("Новости", "/admin/news"), "newspage": ("Новости", "/admin/news"),
    "status1": ("Приём", "/admin/admission"), "dates10": ("Приём", "/admin/admission"), "lager_prices": ("Приём", "/admin/admission"),
    "menu": ("Питание", "/admin/food"),
    "director": ("Люди", "/admin/people?q=Директор"), "admin_groups": ("Люди", "/admin/people?q=Администрация"),
    "buildings": ("Контакты школы", "/admin/contacts"), "requisites": ("Контакты школы", "/admin/contacts"), "secretaries": ("Контакты школы", "/admin/contacts"),
    "vacancies": ("Вакансии", "/admin/vacancies"),
}
LOCK_DYN = {"admission_home": ("Приём", "/admin/admission"), "admission_10": ("Приём", "/admin/admission"), "lager_card": ("Приём", "/admin/admission"),
            "people_card": ("Люди", "/admin/people"), "odod_card": ("Контакты школы", "/admin/contacts"), "contacts_card": ("Контакты школы", "/admin/contacts"),
            "food_prices": ("Питание", "/admin/food")}
LOCK_SVEDEN = {"common": ("Контакты школы", "/admin/contacts"), "struct": ("Люди", "/admin/people?q=Руководитель подразделения"), "managers": ("Люди", "/admin/people?q=Администрация"),
               "employees": ("Люди", "/admin/people?q=Педагогический состав"), "vacant": ("Приём", "/admin/admission"), "catering": ("Питание", "/admin/food")}


def lock_of(p):
    def f(blk):
        t = blk.get("t") if isinstance(blk, dict) else blk
        if t in ("people", "docs", "clubs"):
            return None  # блоки с данными правятся прямо на странице
        if t == "sveden_data":
            lab, href = LOCK_SVEDEN.get(p.get("sveden"), ("Контакты школы", "/admin/contacts"))
            return {"label": lab, "href": href}
        if t in LOCK_BY_TYPE:
            lab, href = LOCK_BY_TYPE[t]
            return {"label": lab, "href": href.format(url=p["url"], title=quote(p.get("title", "")))}
        return None
    return f


def claimed_groups(blocks):
    out = set()
    for b_ in blocks or []:
        if b_.get("t") == "docs" and b_.get("groups"):
            out.update(b_["groups"])
        if b_.get("t") == "tabs":
            for _, inner in b_.get("tabs", []):
                out |= claimed_groups(inner)
    return out


def docs_view(p):
    claimed = claimed_groups(p.get("blocks"))

    def f(blk):
        g = db.docs_for(p["url"])
        if blk.get("groups"):
            return {k: g[k] for k in blk["groups"] if k in g}
        if blk.get("rest"):
            return {k: v for k, v in g.items() if k not in claimed}
        return g
    return f


def schedule_groups(url):
    """Расписание по корпусам. Группу узнаём по названию улицы, а не по точному написанию, остальное — отдельно."""
    blds = [b_.get("address", "") for b_ in (settings().get("buildings") or [])]
    out = {b_: [] for b_ in blds}
    other = []
    for grp, items in db.docs_for(url).items():
        key = re.sub(r"[^а-яё]", "", (grp or "").lower())
        hit = next((b_ for b_ in blds if re.sub(r"[^а-яё]", "", b_.lower().split(",")[0]) and re.sub(r"[^а-яё]", "", b_.lower().split(",")[0]) in key), None)
        (out[hit] if hit else other).extend(items)
    return [(b_, out[b_]) for b_ in blds], other


def section_updated(p):
    """Дата обновления подраздела «Сведений»: самое позднее из правок страницы, её документов и её источника данных."""
    url, slug = p.get("url", ""), p.get("sveden")
    dates = [blocks_store.page_updated(url)]
    r = db.q1("SELECT MAX(d.updated) u FROM docs d JOIN doc_places pl ON pl.doc_id=d.id WHERE pl.page=?", (url,))
    dates.append((r or {}).get("u") or "")
    src = {"common": "contacts", "struct": "contacts", "vacant": "admission", "catering": "food_prices"}.get(slug)
    if src:
        dates.append(db.setting_updated(src) or "")
    if slug in ("managers", "employees"):
        r = db.q1("SELECT MAX(updated) u FROM people")
        dates.append((r or {}).get("u") or "")
    if slug == "catering":
        r = db.q1("SELECT MAX(uploaded) u FROM food_files")
        dates.append((r or {}).get("u") or "")
    best = max(dates)
    return best or date.today().isoformat()


def resolve_people(blk):
    ids = [i for g in blk.get("groups", []) for i in g.get("ids", [])]
    rows = {r["id"]: r for r in db.q("SELECT * FROM people WHERE id IN (%s)" % ",".join("?" * len(ids)), ids)} if ids else {}
    out = []
    for g in blk.get("groups", []):
        gg = {k: v for k, v in g.items() if k != "ids"}
        gg["members"] = [rows[i] for i in g.get("ids", []) if i in rows]
        out.append(gg)
    return out


def resolve_docs(blk):
    ids = [i for g in blk.get("groups", []) for i in g.get("ids", [])]
    rows = {r["id"]: r for r in db.q("SELECT * FROM docs WHERE id IN (%s)" % ",".join("?" * len(ids)), ids)} if ids else {}
    out = []
    for g in blk.get("groups", []):
        gg = {k: v for k, v in g.items() if k != "ids"}
        gg["members"] = [rows[i] for i in g.get("ids", []) if i in rows]
        out.append(gg)
    return out


def resolve_clubs(blk):
    if blk.get("auto"):
        return db.q("SELECT * FROM clubs ORDER BY pos, title")
    ids = blk.get("ids", [])
    rows = {r["id"]: r for r in db.q("SELECT * FROM clubs WHERE id IN (%s)" % ",".join("?" * len(ids)), ids)} if ids else {}
    return [rows[i] for i in ids if i in rows]


def active_tab_fn(qp):
    def f(blk):
        key = qp.get(blk.get("query") or "", "") if blk.get("query") else ""
        if key:
            for i, tb in enumerate(blk.get("tabs", []), 1):
                if len(tb) > 2 and tb[2] == key:
                    return i
        try:
            n = int(qp.get("tab", "1"))
        except ValueError:
            n = 1
        return n if 1 <= n <= len(blk.get("tabs", [])) else 1
    return f


def ctx_for(p, request, edit=False):
    qp = request.query_params
    tab = int(qp.get("tab", "1")) if qp.get("tab", "1").isdigit() else 1
    svc = qp.get("s", "psiholog")
    S = {k: v for k, v in SERVICE_INFO.items()}
    try:
        offset = max(0, int(qp.get("o", "0")))
    except ValueError:
        offset = 0
    return dict(p=p, C=settings(), A=db.get_setting("admission", {}), L=db.get_setting("lager", {}),
                F=food_files(), P=db.get_setting("food_prices", []),
                docs=db.docs_for, people=people, news=news, clubs=clubs, vacancies=vacancies,
                tab=tab, svc=svc if svc in S else "psiholog", S=S, SERVICES=content.SERVICES, plural=plural,
                RUBRICS=RUBRICS, rubric=qp.get("r") if qp.get("r") in RUBRICS else None, offset=offset, edit=edit, lock=lock_of(p), resolve_people=resolve_people, resolve_docs=resolve_docs, resolve_clubs=resolve_clubs, active_tab=active_tab_fn(qp), schedule_groups=lambda: schedule_groups(p['url']),
                service_buildings=lambda: [b_.get('address') for b_ in (settings().get('buildings') or [])][::-1] + ['—'],
                updated=date_h(section_updated(p)[:10]))


# ---------- стеклянные карточки в шапке ----------
def card_html(p, ctx):
    c = p.get("card")
    if not c:
        return ""
    obj = f'<img class="o3d o-card" src="/static/img/obj/{p["obj"]}.webp" alt="">' if p.get("obj") else ""
    if p["url"] == "/":
        obj = '<img class="o3d o-h1" src="/static/img/obj/ringsphere.webp" alt=""><img class="o3d o-h2" src="/static/img/obj/pyramid.webp" alt="">'
    e = html.escape
    rows, title, text, btn = [], "", "", ""
    dyn = c.get("dyn")
    A, C, L = ctx["A"], ctx["C"], ctx["L"]
    if dyn == "admission_home":
        # объявление собирается из статуса, года и даты: год вводится один раз и не расходится
        yr, st = A.get("year1", ""), A.get("status1")
        title = {"open": f"Идёт приём в 1 класс на {yr} учебный год",
                 "closed": f"Приём в 1 класс на {yr} учебный год завершён"}.get(st, f"Приём в 1 класс на {yr} учебный год откроется {A.get('open_date', '')}")
        btn = '<div class="btns" style="margin-top:4px"><a class="btn btn--ghost btn--sm" href="/postuplenie/1-klass">Как проходит приём</a></div>'
    elif dyn == "people_card":
        title = c["title"]
        ids = c.get("ids") or []
        found = {r["id"]: r for r in db.q("SELECT * FROM people WHERE id IN (%s)" % ",".join("?" * len(ids)), ids)} if ids else {}
        for x in [found[i] for i in ids if i in found]:
            rows.append((f'{x["name"]}, {(x["position"] or "").lower()}', (x["phone"] or "").replace("(812) ", "")))
        if c.get("secretary") is not None:  # телефон секретаря берём из «Контактов школы», а не пишем второй раз
            blds = C.get("buildings") or []
            i = c["secretary"]
            if i < len(blds):
                b_ = blds[i]
                rows.append((f'Секретарь, {b_.get("address", "")}{", каб. " + b_["room"] if b_.get("room") else ""}', (b_.get("phone") or "").replace("(812) ", "")))
    elif dyn == "admission_10":
        title = f'На {A.get("year10", "")} учебный год'
        def num(v):
            try:
                return int(str(v).strip())
            except (TypeError, ValueError):
                return 0
        rows = [("10 классов", A.get("classes10", "")), ("Мест в классе", A.get("seats10", "")),
                ("Всего мест", (num(A.get("classes10")) * num(A.get("seats10"))) or "")]
    elif dyn == "odod_card":
        o = db.get_setting("odod", {})
        title, text = "Отделение дополнительного образования", "Все объединения бесплатные."
        rows = [("Занятия", o.get("hours", "")), ("Приём родителей", o.get("reception", "")), ("Руководитель", o.get("phone", ""))]
    elif dyn == "lager_card":
        title = L.get("shift", "Ближайшая смена")
        rows = [("Даты", L.get("dates", "")), ("Мест", L.get("seats", ""))]
    elif dyn == "food_prices":
        title = "Цены на питание"
        rows = [(a, v) for a, v in ctx["P"]]
    elif dyn == "contacts_card":
        title, text = "Общая почта", C.get("email", "")
        rows = [("Приёмный день", C.get("reception", ""))]
    else:
        title, text, rows = c.get("title", ""), c.get("text", ""), c.get("rows", [])
    r = "".join(f'<div class="row"><span>{e(str(a))}</span><b>{e(str(b_))}</b></div>' for a, b_ in rows if b_ not in ("", None))
    attrs = ""
    if ctx.get("edit"):
        if dyn:
            lab, href = LOCK_DYN.get(dyn, ("Контакты школы", "/admin/contacts"))
            if dyn == "people_card":
                lab, href = None, None
            attrs = (f' data-eb="1" data-path="card" data-t="card" data-lock="{lab}" data-href="{href}"' if lab
                     else ' data-eb="1" data-path="card" data-t="card_people"')
        else:
            attrs = ' data-eb="1" data-path="card" data-t="card"'
    return f'<aside class="hcard glass"{attrs}>{obj}<h2>{e(title)}</h2>{f"<p>{e(text)}</p>" if text else ""}{r}{btn}</aside>'


def groups_of(blocks):
    """Секции страницы; у каждого блока запоминаем его номер, чтобы админка знала, что правит."""
    out, cur = [], []
    for i, b_ in enumerate(blocks):
        if b_["t"] == "kv_promo":
            if cur:
                out.append(("light", cur))
                cur = []
            out.append(("kv", [(i, b_)]))
        else:
            cur.append((i, b_))
    if cur:
        out.append(("light", cur))
    return out


def crumbs_of(p):
    """Крошки без петель: раздел меню — просто подпись (у разделов нет своих страниц),
    ссылка только туда, куда человек ожидает вернуться. У новости — назад в «Новости»."""
    if p.get("article"):
        return [("Новости", "/novosti")]
    sec = p.get("section")
    if not sec or p["url"] == "/":
        return []
    if p["url"] == "/novosti":
        return [("Новости", None)]
    name, href = SECTIONS[sec]
    if name == p["title"]:
        return [(p["title"], None)]
    return [(name, None), (p["title"], None)]


def is_edit(request):
    if request.query_params.get("edit") != "1":
        return False
    from .admin import current_user
    return current_user(request) is not None


import logging
from markupsafe import Markup
log = logging.getLogger("school93")


def block_renderer(ctx):
    """Каждый блок рисуется отдельно: если данные в админке сломали один блок, страница всё равно открывается."""
    mod = env.get_template("blocks.html").module

    def draw(blk, path, macro="render"):
        if blk.get("_id"):
            path = "b:" + blk["_id"]
        try:
            fn = getattr(mod, macro)
            return Markup(fn(blk, ctx, path) if macro == "render" else fn(blk, ctx, path))
        except Exception as e:  # noqa: BLE001
            log.exception("блок %s на %s не отрисован", path, ctx["p"].get("url"))
            if ctx.get("edit"):
                return Markup(f'<div class="eb-broken" data-eb="1" data-path="{html.escape(path)}" data-t="{html.escape(str(blk.get("t")))}">'
                              f'Блок не показан посетителям: в его данных ошибка ({html.escape(type(e).__name__)}). Нажмите, чтобы исправить.</div>')
            return Markup("")
    return draw


def render_page(p, request, article_html=None):
    ctx = ctx_for(p, request, edit=is_edit(request))
    ctx["block"] = block_renderer(ctx)
    nav_cur = {"novosti": "zhizn", "pedagogam": "o-shkole", "sveden": "o-shkole"}.get(p.get("section"), p.get("section"))
    t = env.get_template("base.html")
    try:
        hcard = card_html(p, ctx)
    except Exception:  # noqa: BLE001
        log.exception("карточка в шапке %s не отрисована", p.get("url"))
        hcard = ""
    return t.render(p=p, ctx=ctx, C=ctx["C"], card_html=hcard, groups=groups_of(p["blocks"]), edit=ctx["edit"],
                    crumbs=crumbs_of(p), nav_cur=nav_cur, article_html=article_html)


IMG_LINE = re.compile(r"/static/uploads/(?:news/)?[A-Za-z0-9._-]+\.(webp|jpg|jpeg|png)")


def body_to_html(text):
    """Текст новости: пустая строка = новый абзац, «## » = подзаголовок, строка-картинка /static/uploads/...
    Одна картинка — на всю ширину, несколько подряд — галерея."""
    out, gallery = [], []

    def flush():
        if len(gallery) == 1:
            out.append(f"<div class='photo' style='min-height:360px;background-image:url({gallery[0]})'></div>")
        elif gallery:
            out.append("<div class='gallery'>" + "".join(f"<a href='{g}' target='_blank'><img src='{g}' alt='' loading='lazy'></a>" for g in gallery) + "</div>")
        gallery.clear()
    for block in re.split(r"\n\s*\n", (text or "").strip()):
        s = block.strip()
        if not s:
            continue
        if IMG_LINE.fullmatch(s):
            gallery.append(s)
            continue
        flush()
        if s.startswith("## "):
            out.append(f"<h3 class='h3'>{html.escape(s[3:])}</h3>")
        else:
            out.append("<p>" + html.escape(s).replace("\n", "<br>") + "</p>")
    flush()
    return "\n".join(out)


# =================== приложение ===================
app = FastAPI(title="Школа №93", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")


@app.on_event("startup")
def _startup():
    db.init()
    os.makedirs(FOOD_DIR, exist_ok=True)
    if not db.get_setting("contacts"):  # пустая база: заполняем сами, чтобы сайт не был пустым
        from . import seed
        seed.seed(os.path.join(ROOT, "data", "files.csv"))
    blocks_store.ensure_all()  # страницы, которых ещё нет в конструкторе, собираются из исходных текстов


from . import admin  # noqa: E402  админка в отдельном модуле
app.include_router(admin.router)
from . import pages_admin  # noqa: E402
app.include_router(pages_admin.router)


@app.middleware("http")
async def _security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    # админку можно встраивать только в саму себя (редактор страниц работает через iframe)
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return resp


@app.exception_handler(PermissionError)
def _perm(request, exc):
    return RedirectResponse("/admin/login", status_code=303)


@app.get("/food/")
def food_index():
    files = sorted(os.listdir(FOOD_DIR)) if os.path.isdir(FOOD_DIR) else []
    items = "".join(f'<li><a href="/food/{quote(f)}">{html.escape(f)}</a></li>' for f in files if not f.startswith("."))
    return HTMLResponse(f"<!doctype html><meta charset=utf-8><title>/food/</title><h1>/food/</h1><ul>{items}</ul>")


@app.get("/food/{name}")
def food_file(name: str):
    path = os.path.join(FOOD_DIR, os.path.basename(name))
    if not os.path.isfile(path):
        return Response(status_code=404)
    return FileResponse(path)


@app.get("/sitemap.xml")
def sitemap(request: Request):
    host = str(request.base_url).rstrip("/")
    urls = list(PAGES) + [f"/novosti/{n['slug']}" for n in db.news_list(None, 500)]
    xml = "".join(f"<url><loc>{host}{u}</loc></url>" for u in urls)
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{xml}</urlset>', media_type="application/xml")


@app.get("/robots.txt")
def robots(request: Request):
    return PlainTextResponse(f"User-agent: *\nDisallow: /admin\nSitemap: {str(request.base_url).rstrip('/')}/sitemap.xml\n")


@app.get("/novosti/{slug}", response_class=HTMLResponse)
def article(slug: str, request: Request):
    n = db.q1("SELECT * FROM news WHERE slug=? AND published=1 AND date<=?", (slug, date.today().isoformat()))
    if not n:
        return not_found(request)
    n["date_h"] = news_date(n)
    size = "s" if len(n["title"]) <= 60 else ("m" if len(n["title"]) <= 110 else "l")
    p = dict(url=f"/novosti/{slug}", section="novosti", title=n["title"], h1=[n["title"]], lead=f'{n["rubric"]}, {n["date_h"]}',
             blocks=[], buttons=[], card=None, obj=None, k=n["rubric"] == "Кванториум", article=size)
    ctx = ctx_for(p, request)
    # фото в конце текста — это галерея, их показываем сеткой под текстом
    parts = [x.strip() for x in re.split(r"\n\s*\n", (n["body"] or "").strip()) if x.strip()]
    gallery = []
    while parts and IMG_LINE.fullmatch(parts[-1]):
        gallery.insert(0, parts.pop())
    photos = ([n["cover"]] if n.get("cover") else []) + gallery
    art = env.get_template("article.html").render(n=n, size=size, body_html=body_to_html("\n\n".join(parts)), gallery=gallery, photos=photos, ctx=ctx)
    return HTMLResponse(render_page(p, request, article_html=art))


def not_found(request):
    p = dict(url="/404", section=None, title="Страница не найдена", h1=["Страница", "не найдена"],
             lead="Возможно, адрес изменился. Начните с главной или откройте меню.",
             buttons=[("На главную", "/", "")], blocks=[], card=None, obj=None, k=False)
    return HTMLResponse(render_page(p, request), status_code=404)


@app.get("/{path:path}", response_class=HTMLResponse)
def any_page(path: str, request: Request):
    url = "/" + path.strip("/") if path.strip("/") else "/"
    if url in REDIRECTS:
        return RedirectResponse(REDIRECTS[url], status_code=301)
    if url.endswith(".html") and url in REDIRECTS:
        return RedirectResponse(REDIRECTS[url], status_code=301)
    p = blocks_store.load_page(url)
    if not p:
        return not_found(request)
    return HTMLResponse(render_page(p, request))
