"""Админка по страницам: редактор блоков поверх живой страницы."""
import json
import re

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import db, content, blocks_store as bs
from .admin import guard, render, env, current_user

router = APIRouter(prefix="/admin")

TYPE_NAMES = {
    "hero": "Шапка страницы", "card": "Карточка в шапке", "h2": "Заголовок раздела", "text": "Текст", "note": "Примечание",
    "cards": "Карточки", "checkcards": "Списки", "steps": "Шаги", "faq": "Частые вопросы", "links": "Ссылки", "phones": "Телефоны",
    "tabs": "Вкладки", "tiles": "Плитки «Что нужно сделать»", "profiles": "Профили 10 класса", "transport": "Как добраться",
    "trust_top": "Главные телефоны", "kv_promo": "Блок Кванториума", "bullets": "Список", "svc": "Служба",
    "docs": "Документы", "people": "Люди", "feed": "Новости", "newspage": "Лента новостей", "status1": "Статус приёма",
    "dates10": "Сроки подачи документов", "lager_prices": "Цены путёвки", "clubs": "Каталог кружков", "menu": "Меню",
    "director": "Директор", "admin_groups": "Заместители директора", "buildings": "Корпуса", "requisites": "Реквизиты",
    "secretaries": "Секретари", "vacancies": "Вакансии", "struct_units": "Структурные подразделения", "gov_bodies": "Органы управления", "schedule": "Расписание", "sveden_data": "Данные из админки",
}

R = "rows"
SPECS = {
    "hero": [("title", "Название страницы", "input", "Для вкладки браузера и строки «Главная / Раздел / Страница»"),
             ("h1", "Заголовок", "lines", "Каждая строка заголовка с новой строки"),
             ("lead", "Подзаголовок", "textarea", ""),
             ("buttons", "Кнопки", R, {"cols": [("Текст", "input"), ("Ссылка", "input"), ("Вид", "select", [("", "Основная"), ("ghost", "Второстепенная")])]})],
    "card": [("title", "Заголовок карточки", "input", ""), ("text", "Текст", "textarea", ""),
             ("rows", "Строки", R, {"cols": [("Подпись", "input"), ("Значение", "input")]})],
    "h2": [("text", "Заголовок", "input", ""), ("lead", "Пояснение под заголовком", "textarea", "Необязательно")],
    "text": [("ps", "Текст", "paras", "Пустая строка начинает новый абзац")],
    "note": [("text", "Примечание", "textarea", "")],
    "cards": [("rows", "Карточки", R, {"cols": [("Заголовок", "input"), ("Текст", "textarea"), ("Надпись сверху", "input"), ("Ссылка (необязательно)", "input")]})],
    "checkcards": [("cards", "Карточки со списками", R, {"cols": [("Заголовок", "input"), ("Пункты, каждый с новой строки", "lines")]})],
    "steps": [("rows", "Шаги", R, {"cols": [("Шаг", "input"), ("Пояснение", "textarea"), ("Срок", "input")]})],
    "faq": [("rows", "Вопросы", R, {"cols": [("Вопрос", "input"), ("Ответ", "textarea")]})],
    "links": [("rows", "Ссылки", R, {"cols": [("Текст", "input"), ("Адрес", "input")]})],
    "phones": [("rows", "Телефоны", R, {"cols": [("Кто", "input"), ("Телефон", "input"), ("Пояснение", "textarea")]})],
    "tabs": [("tabs", "Названия вкладок", "tablabels", "Содержимое вкладок меняется в их блоках: переключите вкладку на странице и нажмите на блок")],
    "tiles": [("title", "Заголовок", "input", ""), ("rows", "Плитки", R, {"cols": [("Заголовок", "input"), ("Текст", "input"), ("Ссылка", "input")], "fixed": True})],
    "profiles": [("title", "Заголовок", "input", ""), ("lead", "Пояснение", "textarea", ""),
                 ("rows", "Профили", R, {"cols": [("Класс", "input"), ("Профиль", "input"), ("Уточнение", "input"), ("Профильные предметы", "input"), ("Для кого", "textarea")]})],
    "transport": [("title", "Заголовок", "input", ""), ("lead", "Пояснение", "textarea", ""),
                  ("rows", "Транспорт", R, {"cols": [("Вид", "input"), ("Номер или название", "input"), ("Откуда", "textarea")]})],
    "trust_top": [("rows", "Главные телефоны", R, {"cols": [("Надпись", "input"), ("Телефон", "input"), ("Пояснение", "input")]})],
    "kv_promo": [("tag", "Надпись сверху", "input", ""), ("title", "Заголовок", "input", ""), ("lead", "Текст", "textarea", ""), ("button", "Текст кнопки", "input", "")],
    "bullets": [("title", "Заголовок", "input", ""), ("rows", "Пункты", R, {"cols": [("Пункт", "textarea")]})],
    "struct_units": [("title", "Заголовок", "input", ""), ("rows", "Подразделения", R, {"cols": [("Подразделение", "input"), ("Руководитель", "input"), ("Должность", "input"), ("Адрес (пусто = адрес школы)", "input"), ("Почта", "input")]})],
    "gov_bodies": [("title", "Заголовок", "input", ""), ("rows", "Органы управления", R, {"cols": [("Орган", "input"), ("Кто входит и что решает", "textarea")]})],
    "svc": [("lead", "Описание службы", "textarea", ""), ("hours", "Часы приёма", "input", "Подпись над телефоном"),
            ("phones", "Телефоны по корпусам", "dict", {"keys": ["Первомайская, 30", "Школьная, 19"]}),
            ("help", "С чем можно прийти", R, {"cols": [("Тема", "input"), ("Пояснение", "textarea")]})],
}
SPECS["feed"] = [("title", "Заголовок", "input", ""), ("rubric", "Рубрика", "choice", None), ("limit", "Сколько новостей", "number", "")]
# блоки, которые берут данные из разделов-настроек (приём, питание, контакты): правятся там
LOCKED = {"newspage", "status1", "dates10", "lager_prices", "menu", "buildings", "requisites", "secretaries", "vacancies", "sveden_data"}
DATA = {"people", "docs", "clubs"}
TYPE_NAMES.update({"people": "Люди", "docs": "Документы", "clubs": "Кружки", "feed": "Новости рубрики", "card_people": "Карточка «Кто отвечает»"})

# каталог: что можно добавить на страницу кнопкой «+»
CATALOG = [
    ("h2", "Заголовок раздела", "Крупный заголовок и пояснение под ним", {"text": "Новый раздел", "lead": ""}),
    ("text", "Текст", "Один или несколько абзацев", {"ps": ["Текст абзаца."]}),
    ("note", "Примечание", "Мелкий серый текст", {"text": "Примечание."}),
    ("cards", "Карточки", "Плитки с заголовком и текстом, можно со ссылкой", {"rows": [["Заголовок", "Текст карточки", "", ""]], "cols": 3, "dark": []}),
    ("checkcards", "Списки с отметками", "Что взять, что заполнить и т. п.", {"cards": [["Что взять", ["Пункт"]]]}),
    ("steps", "Шаги", "Порядок действий с номерами", {"rows": [["Первый шаг", "Пояснение", ""]]}),
    ("faq", "Частые вопросы", "Вопрос раскрывается в ответ", {"rows": [["Вопрос?", "Ответ."]]}),
    ("links", "Ссылки", "Список ссылок со стрелкой", {"rows": [["Текст ссылки", "https://"]]}),
    ("phones", "Телефоны", "Крупные номера с пояснением", {"rows": [["Кто", "(812) 000-00-00", ""]], "cols": 2}),
    ("tabs", "Вкладки", "Переключатель разделов внутри страницы", {"tabs": [{"label": "Вкладка 1", "key": ""}, {"label": "Вкладка 2", "key": ""}]}),
    ("people", "Люди", "Сотрудники из базы, в нужном порядке", {"title": "", "view": "grid", "groups": [{"title": "", "ids": []}]}),
    ("docs", "Документы", "Документы из базы, по группам", {"title": "Документы", "view": "list", "groups": [{"title": "", "ids": []}]}),
    ("clubs", "Кружки", "Кружки из базы с фильтром по направленности", {"ids": []}),
    ("feed", "Новости рубрики", "Последние новости выбранной рубрики", {"title": "Новости", "rubric": "Школа", "limit": 3, "more": True}),
]
CATALOG_MAP = {c[0]: c for c in CATALOG}
VIEWS = {"grid": "Карточки людей", "chips": "Группы с фильтром (как «Администрация»)", "service": "По корпусам с телефоном (как службы)",
         "inline": "Одной строкой (руководитель)", "director": "Карточка директора", "table_managers": "Таблица «Руководство» (Сведения)",
         "table_teachers": "Таблица «Педагогический состав» (Сведения)"}


# ---------- оглавление страницы ----------
def preview(blk, t):
    try:
        if t == "hero":
            return " ".join(blk.get("h1", []))
        if t in ("people", "docs"):
            n = sum(len(g.get("ids", [])) for g in blk.get("groups", []))
            return (blk.get("title") or "") + f" ({n})"
        if t == "clubs":
            return f"{len(blk.get('ids', []))} шт."
        for k in ("text", "title", "tag"):
            if blk.get(k):
                return str(blk[k])
        for k in ("rows", "cards", "ps"):
            v = blk.get(k)
            if v:
                first = v[0]
                return str(first[0] if isinstance(first, (list, tuple)) else first)
        if blk.get("lead"):
            return blk["lead"]
    except Exception:  # noqa: BLE001
        pass
    return ""


def outline(page):
    out = [("hero", "hero", preview(page, "hero"), False, 0)]
    card = page.get("card")
    if card:
        dyn = card.get("dyn")
        out.append(("card", "card_people" if dyn == "people_card" else "card", card.get("title", "") if dyn in (None, "people_card") else "Данные из админки",
                    bool(dyn) and dyn != "people_card", 0))

    def walk(blocks, depth):
        for b in blocks:
            t = b.get("t")
            out.append(("b:" + b["_id"], t, preview(b, t), t in LOCKED, depth))
            if t == "tabs":
                for tb in b.get("tabs", []):
                    out.append((None, "tablabel", tb[0], False, depth + 1))
                    walk(tb[1], depth + 2)
    walk(page.get("blocks", []), 0)
    return out


def page_groups():
    used, groups = set(), [("Главная", ["/"])]
    for name, _, items in content.MENU:
        urls = []
        for _, h in items:
            u = h.split("#")[0]
            if u in content.PAGES and u not in used and not u.startswith("/sveden"):
                urls.append(u)
                used.add(u)
        if urls:
            groups.append((name, urls))
    rest = [u for u in content.PAGES if u not in used and u != "/" and not u.startswith("/sveden")]
    if rest:
        groups.append(("Ещё", rest))
    groups.append(("Сведения об образовательной организации", [u for u in content.PAGES if u.startswith("/sveden")]))
    return groups


@router.get("/pages")
def pages_list(request: Request):
    u, r = guard(request)
    if r:
        return r
    return RedirectResponse("/admin/pages/edit?url=/", status_code=303)


@router.get("/pages/edit", response_class=HTMLResponse)
def page_editor(request: Request, url: str = "/"):
    u, r = guard(request)
    if r:
        return r
    page = bs.load_page(url)
    if not page:
        return RedirectResponse("/admin/pages/edit?url=/", status_code=303)
    titles = {x: (bs.get_meta(x) or {}).get("title") or content.PAGES[x]["title"] for x in content.PAGES}
    section = dict((g, n) for g, n in [(k, v[0]) for k, v in content.SECTIONS.items()]).get(page.get("section"), "")
    return render(request, "page_editor.html", u, "pages", page=page, url=url, catalog=CATALOG, groups=page_groups(), titles=titles,
                  sec_name=section, names=TYPE_NAMES)


def _target(url, path):
    """(тип, данные) блока по пути редактора."""
    if path == "hero":
        return "hero", bs.get_meta(url)
    if path == "card":
        card = (bs.get_meta(url) or {}).get("card") or {}
        dyn = card.get("dyn")
        return ("card_people" if dyn == "people_card" else ("locked_card" if dyn else "card")), card
    if path.startswith("b:"):
        b = bs.get_block(path[2:])
        if b and b["url"] == url:
            return b["type"], b["data"]
    raise KeyError(path)


@router.get("/pages/form", response_class=HTMLResponse)
def block_form(request: Request, url: str, path: str):
    u = current_user(request)
    if not u:
        return HTMLResponse("", status_code=401)
    try:
        t, blk = _target(url, path)
    except KeyError:
        return HTMLResponse('<div class="bf"><p class="mut">Блок не найден. Обновите страницу.</p></div>', status_code=404)
    hist = []
    if path.startswith("b:"):
        hist = db.q("SELECT id, action, updated, user FROM block_history WHERE block_id=? AND action='изменил' ORDER BY id DESC LIMIT 5", (path[2:],))
    elif path in ("hero", "card"):
        hist = db.q("SELECT id, action, updated, user FROM block_history WHERE block_id=? ORDER BY id DESC LIMIT 5", ("meta:" + url,))
    fixed = t in bs.FIXED_TYPES
    tpl = "block_data.html" if t in DATA or t == "card_people" else "block_form.html"
    return HTMLResponse(env.get_template(tpl).render(
        u=u, url=url, path=path, t=t, blk=blk, spec=SPECS.get(t), history=hist, edited=False, name=TYPE_NAMES.get(t, "Блок"),
        locked=t in LOCKED or t == "locked_card", movable=path.startswith("b:"), fixed=fixed, views=VIEWS, rubrics=content.RUBRICS,
        data_json=json.dumps(blk, ensure_ascii=False)))


def fields_from_form(t, f, blk):
    fields = {}
    for key, label, kind, extra in [(s + ("",))[:4] for s in SPECS.get(t, [])]:
        if kind in ("input", "textarea", "choice"):
            fields[key] = f.get(f"f_{key}", "").strip()
        elif kind == "number":
            try:
                fields[key] = max(1, min(24, int(f.get(f"f_{key}", "3"))))
            except ValueError:
                fields[key] = 3
        elif kind == "lines":
            fields[key] = [x.strip() for x in f.get(f"f_{key}", "").splitlines() if x.strip()]
        elif kind == "paras":
            fields[key] = [x.strip() for x in f.get(f"f_{key}", "").replace("\r", "").split("\n\n") if x.strip()]
        elif kind == "tablabels":
            labels = f.getlist("tl")
            keys = f.getlist("tk")
            fields["tabs"] = [{"label": (l_.strip() or f"Вкладка {i + 1}"), "key": (keys[i] if i < len(keys) else "")} for i, l_ in enumerate(labels)]
        elif kind == "dict":
            fields[key] = {k: f.get(f"d_{key}_{i}", "").strip() for i, k in enumerate(extra["keys"]) if f.get(f"d_{key}_{i}", "").strip()}
        elif kind == R:
            cols = extra["cols"]
            colvals = [f.getlist(f"r_{key}_{ci}") for ci in range(len(cols))]
            rows = []
            for vals in zip(*colvals):
                row = []
                for (clabel, ckind, *_), v in zip(cols, vals):
                    row.append([x.strip() for x in v.splitlines() if x.strip()] if ckind == "lines" else v.strip())
                if any(x for x in row):
                    rows.append(row)
            fields[key] = rows
    if "f_cols" in f:
        try:
            fields["cols"] = max(1, min(3, int(f.get("f_cols"))))
        except ValueError:
            pass
    return fields


async def _auth_form(request):
    u = current_user(request)
    if not u:
        return None, None, JSONResponse({"error": "auth"}, status_code=401)
    f = await request.form()
    if f.get("csrf") != u["csrf"]:
        return None, None, JSONResponse({"error": "csrf"}, status_code=403)
    return u, f, None


@router.post("/pages/save")
async def block_save(request: Request):
    u, f, err = await _auth_form(request)
    if err:
        return err
    url, path = f.get("url"), f.get("path")
    try:
        t, blk = _target(url, path)
    except KeyError:
        return JSONResponse({"error": "notfound"}, status_code=404)
    if t in LOCKED or t == "locked_card":
        return JSONResponse({"error": "locked"}, status_code=400)
    page_title = (bs.get_meta(url) or {}).get("title", url)
    if t in DATA or t == "card_people":
        try:
            data = json.loads(f.get("data", "{}"))
        except ValueError:
            return JSONResponse({"error": "bad"}, status_code=400)
        new = dict(blk)
        for k in ("title", "view", "note", "empty", "word"):
            if k in data:
                new[k] = data[k]
        if t == "clubs":
            new["ids"] = [int(i) for i in data.get("ids", []) if str(i).isdigit()]
            new["auto"] = bool(data.get("auto"))
        elif t == "card_people":
            new["ids"] = [int(i) for i in data.get("ids", []) if str(i).isdigit()]
        else:
            groups = []
            for g in data.get("groups", []):
                gg = {k: str(g.get(k, "")).strip() for k in ("title", "phone", "note") if k in g}
                gg["ids"] = [int(i) for i in g.get("ids", []) if str(i).isdigit()]
                groups.append(gg)
            lim = blk.get("limit")
            if lim:  # единственное место: директор, руководитель
                allids = [i for g in groups for i in g["ids"]][:lim]
                groups = [{**(groups[0] if groups else {}), "ids": allids}]
            new["groups"] = groups
    else:
        new = dict(blk)
        new.update(fields_from_form(t, f, blk))
        if t == "tabs" and path.startswith("b:"):
            # вкладки переставили или удалили: блоки внутри переезжают вслед за своей вкладкой
            olds = f.getlist("ti")
            mapping = {}
            for new_i, old_i in enumerate(olds):
                if str(old_i).isdigit():
                    mapping[int(old_i)] = new_i
            for ch in db.q("SELECT id, tab FROM blocks WHERE parent=?", (path[2:],)):
                if ch["tab"] in mapping:
                    db.run("UPDATE blocks SET tab=? WHERE id=?", (mapping[ch["tab"]], ch["id"]))
                else:
                    bs.delete_block(ch["id"], u["name"])
    if path == "hero" or path == "card":
        meta = bs.get_meta(url)
        if path == "hero":
            meta.update({k: new[k] for k in ("title", "h1", "lead", "buttons") if k in new})
        else:
            meta["card"] = new
        bs.save_meta(url, meta, u["name"])
    else:
        bs.save_block(path[2:], new, u["name"])
    db.log(u["name"], "Страницы", "изменил", f'{page_title}: {TYPE_NAMES.get(t, t)}')
    return JSONResponse({"ok": True})


@router.post("/pages/revert")
async def block_revert(request: Request):
    """Вернуть прежнюю версию блока или шапки."""
    u, f, err = await _auth_form(request)
    if err:
        return err
    url, path, hid = f.get("url"), f.get("path"), f.get("history")
    h = db.q1("SELECT * FROM block_history WHERE id=?", (hid,)) if hid else None
    if not h:
        return JSONResponse({"error": "notfound"}, status_code=404)
    if path.startswith("b:") and h["block_id"] == path[2:]:
        bs.save_block(path[2:], json.loads(h["data"]), u["name"])
    elif path in ("hero", "card") and h["block_id"] == "meta:" + url:
        bs.save_meta(url, json.loads(h["data"]), u["name"])
    else:
        return JSONResponse({"error": "notfound"}, status_code=404)
    db.log(u["name"], "Страницы", "вернул прежнюю версию", f"{url} ({h['updated']})")
    return JSONResponse({"ok": True})


# ---------- конструктор: добавить, переставить, удалить ----------
@router.post("/blocks/add")
async def block_add(request: Request):
    u, f, err = await _auth_form(request)
    if err:
        return err
    url, btype = f.get("url"), f.get("type")
    if url not in content.PAGES or btype not in CATALOG_MAP:
        return JSONResponse({"error": "bad"}, status_code=400)
    after, parent, tab = f.get("after") or None, f.get("parent") or None, f.get("tab")
    if after and not (bs.get_block(after) or {}).get("url") == url:
        return JSONResponse({"error": "bad"}, status_code=400)
    data = json.loads(json.dumps(CATALOG_MAP[btype][3], ensure_ascii=False))
    bid = bs.add_block(url, btype, data, u["name"], after=after, parent=parent, tab=int(tab) if tab not in (None, "") else None)
    db.log(u["name"], "Страницы", "добавил блок", f'{url}: {CATALOG_MAP[btype][1]}')
    return JSONResponse({"ok": True, "id": bid})


@router.post("/blocks/move")
async def block_move(request: Request):
    u, f, err = await _auth_form(request)
    if err:
        return err
    b = bs.get_block(f.get("id", ""))
    if not b:
        return JSONResponse({"error": "notfound"}, status_code=404)
    moved = bs.move_block(b["id"], "up" if f.get("dir") == "up" else "down")
    if moved:
        db.log(u["name"], "Страницы", "переставил блок", f'{b["url"]}: {TYPE_NAMES.get(b["type"], b["type"])}')
    return JSONResponse({"ok": True, "moved": moved})


@router.post("/blocks/delete")
async def block_delete(request: Request):
    u, f, err = await _auth_form(request)
    if err:
        return err
    b = bs.get_block(f.get("id", ""))
    if not b:
        return JSONResponse({"error": "notfound"}, status_code=404)
    if b["type"] in bs.FIXED_TYPES:
        return JSONResponse({"error": "fixed"}, status_code=400)
    bs.delete_block(b["id"], u["name"])
    db.log(u["name"], "Страницы", "удалил блок", f'{b["url"]}: {TYPE_NAMES.get(b["type"], b["type"])}')
    return JSONResponse({"ok": True})


@router.post("/blocks/restore")
async def block_restore(request: Request):
    u, f, err = await _auth_form(request)
    if err:
        return err
    ok = bs.restore_block(f.get("id", ""), u["name"])
    if ok:
        db.log(u["name"], "Страницы", "вернул удалённый блок", f.get("id", ""))
    return JSONResponse({"ok": ok})


def _set_path(obj, parts, value):
    """Записать значение по пути «rows.2.1» внутрь данных блока."""
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        key = int(part) if part.isdigit() else part
        if isinstance(obj, list):
            while len(obj) <= key:
                obj.append("")
            if last:
                obj[key] = value
            else:
                if not isinstance(obj[key], (list, dict)):
                    obj[key] = []
                obj = obj[key]
        else:
            if last:
                obj[key] = value
            else:
                if not isinstance(obj.get(key), (list, dict)):
                    obj[key] = []
                obj = obj[key]


EDITABLE = {"h2", "text", "note", "cards", "checkcards", "steps", "faq", "links", "phones", "hero"}


@router.post("/pages/field")
async def field_save(request: Request):
    """Правка текста прямо на странице: одно поле одного блока."""
    u, f, err = await _auth_form(request)
    if err:
        return err
    url, path, field = f.get("url"), f.get("path", ""), f.get("field", "")
    value = (f.get("value") or "").replace("\r", "").strip()
    if not re.fullmatch(r"[a-z0-9]+(\.[a-z0-9]+){0,3}", field or ""):
        return JSONResponse({"error": "bad"}, status_code=400)
    try:
        t, blk = _target(url, path)
    except KeyError:
        return JSONResponse({"error": "notfound"}, status_code=404)
    if t not in EDITABLE:
        return JSONResponse({"error": "locked"}, status_code=400)
    if path == "hero" and field not in ("h1", "lead"):
        return JSONResponse({"error": "bad"}, status_code=400)
    data = json.loads(json.dumps(blk, ensure_ascii=False))
    if field == "h1":
        lines = [x.strip() for x in value.split("\n") if x.strip()]
        if not lines:
            return JSONResponse({"error": "empty"}, status_code=400)
        data["h1"] = lines
    else:
        _set_path(data, field.split("."), value)
    if path == "hero":
        meta = bs.get_meta(url)
        meta.update({"h1": data.get("h1", meta.get("h1")), "lead": data.get("lead", meta.get("lead"))})
        bs.save_meta(url, meta, u["name"])
    else:
        bs.save_block(path[2:], data, u["name"])
    db.log(u["name"], "Страницы", "изменил текст", f'{(bs.get_meta(url) or {}).get("title", url)}: {TYPE_NAMES.get(t, t)}')
    return JSONResponse({"ok": True})


@router.post("/pages/reset")
async def page_reset(request: Request):
    u, r = guard(request)
    if r:
        return r
    f = await request.form()
    if f.get("csrf") != u["csrf"] or f.get("url") not in content.PAGES:
        return RedirectResponse("/admin/login", status_code=303)
    bs.materialize(f.get("url"), u["name"])
    db.log(u["name"], "Страницы", "вернул исходный вид страницы", f.get("url"))
    return RedirectResponse(f"/admin/pages/edit?url={f.get('url')}&ok=reset", status_code=303)


# ---------- библиотека: поиск по базе и создание записи прямо из окна ----------
@router.get("/lib/{kind}")
def lib_search(kind: str, request: Request, q: str = ""):
    u = current_user(request)
    if not u or kind not in DATA:
        return JSONResponse({"error": "auth"}, status_code=401)
    ql = f"%{q.strip()}%"
    if kind == "people":
        rows = db.q("SELECT id, name, position, building, photo FROM people WHERE name LIKE ? OR position LIKE ? ORDER BY name LIMIT 60", (ql, ql))
        items = [{"id": r["id"], "title": r["name"], "sub": ", ".join(x for x in (r["position"], r["building"]) if x)} for r in rows]
    elif kind == "docs":
        rows = db.q("SELECT id, title, kind, main_doc FROM docs WHERE title LIKE ? ORDER BY title LIMIT 80", (ql,))
        items = [{"id": r["id"], "title": r["title"], "sub": r["kind"] + (", главный документ" if r["main_doc"] else "")} for r in rows]
    else:
        rows = db.q("SELECT id, title, direction, age FROM clubs WHERE title LIKE ? OR direction LIKE ? ORDER BY title LIMIT 60", (ql, ql))
        items = [{"id": r["id"], "title": r["title"], "sub": ", ".join(x for x in (r["direction"], r["age"]) if x)} for r in rows]
    cnt = bs.usage_counts(kind)
    for it in items:
        it["used"] = cnt.get(it["id"], 0)
    return JSONResponse({"items": items})


@router.get("/lib/{kind}/get")
def lib_get(kind: str, request: Request, ids: str = ""):
    u = current_user(request)
    if not u or kind not in DATA:
        return JSONResponse({"error": "auth"}, status_code=401)
    idl = [int(i) for i in ids.split(",") if i.strip().isdigit()]
    if not idl:
        return JSONResponse({"items": []})
    ph = ",".join("?" * len(idl))
    if kind == "people":
        rows = {r["id"]: {"id": r["id"], "title": r["name"], "sub": ", ".join(x for x in (r["position"], r["building"]) if x)} for r in db.q(f"SELECT * FROM people WHERE id IN ({ph})", idl)}
    elif kind == "docs":
        rows = {r["id"]: {"id": r["id"], "title": r["title"], "sub": r["kind"] + (", главный документ" if r["main_doc"] else "")} for r in db.q(f"SELECT * FROM docs WHERE id IN ({ph})", idl)}
    else:
        rows = {r["id"]: {"id": r["id"], "title": r["title"], "sub": r["direction"] or ""} for r in db.q(f"SELECT * FROM clubs WHERE id IN ({ph})", idl)}
    return JSONResponse({"items": [rows[i] for i in idl if i in rows]})


@router.post("/lib/{kind}/new")
async def lib_new(kind: str, request: Request):
    from .admin import kind_of, safe_url_admin
    u, f, err = await _auth_form(request)
    if err:
        return err
    if kind == "people":
        name = f.get("name", "").strip()
        if not name:
            return JSONResponse({"error": "Укажите ФИО"}, status_code=400)
        rid = db.run("INSERT INTO people(name,position,phone,email,building,duty,tags,pos,updated) VALUES(?,?,?,?,?,?,'[]',100,?)",
                     (name, f.get("position", "").strip(), f.get("phone", "").strip(), f.get("email", "").strip(), f.get("building", "").strip(), f.get("duty", "").strip(), db.now()))
        item = {"id": rid, "title": name, "sub": f.get("position", "").strip()}
        db.log(u["name"], "Люди", "добавил", name)
    elif kind == "docs":
        title, url = f.get("title", "").strip(), f.get("url", "").strip()
        if not title or not url:
            return JSONResponse({"error": "Укажите название и ссылку"}, status_code=400)
        if not safe_url_admin(url):
            return JSONResponse({"error": "Ссылка должна начинаться с https://"}, status_code=400)
        rid = db.run("INSERT INTO docs(title,url,kind,updated,main_doc) VALUES(?,?,?,?,?)", (title, url, kind_of(url), db.now(), 1 if f.get("main_doc") else 0))
        item = {"id": rid, "title": title, "sub": kind_of(url)}
        db.log(u["name"], "Документы", "добавил", title)
    elif kind == "clubs":
        title = f.get("title", "").strip()
        if not title:
            return JSONResponse({"error": "Укажите название"}, status_code=400)
        rid = db.run("INSERT INTO clubs(title,direction,age,building,teacher,schedule) VALUES(?,?,?,?,?,?)",
                     (title, f.get("direction", ""), f.get("age", "").strip(), f.get("building", ""), f.get("teacher", "").strip(), f.get("schedule", "").strip()))
        item = {"id": rid, "title": title, "sub": f.get("direction", "")}
        db.log(u["name"], "Кружки", "добавил", title)
    else:
        return JSONResponse({"error": "bad"}, status_code=400)
    item["used"] = 0
    return JSONResponse({"ok": True, "item": item})
