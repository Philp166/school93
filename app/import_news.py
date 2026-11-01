"""Загрузка новостей со старого сайта из news_export.zip (результат parse_news.py).
Запуск: python -m app.import_news путь\\к\\news_export.zip

Дат на старом сайте почти нет, но новости на каждой странице стоят от новых к старым.
Поэтому дата берётся из текста («22 мая», «27 января 2026 года», «День знаний») и год подбирается так,
чтобы порядок не нарушался. Где точной даты нет, ставится ближайшая по порядку и пометка «дата примерная»."""
import json
import os
import re
import secrets
import shutil
import sys
import zipfile
from datetime import date

from . import db
from .admin import slugify

BASE = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(BASE, "static", "uploads", "news")
MONTHS = ["январ", "феврал", "март", "апрел", "ма", "июн", "июл", "август", "сентябр", "октябр", "ноябр", "декабр"]
MRE = r"(январ[яь]|феврал[яь]|марта?|апрел[яь]|ма[яй]|июн[яь]|июл[яь]|августа?|сентябр[яь]|октябр[яь]|ноябр[яь]|декабр[яь])"
# праздники, по которым дату можно узнать без числа в тексте
HOLIDAYS = [(r"день знаний|1 сентября", (9, 1)), (r"последн\w+ звон", (5, 24)), (r"вручени\w+ аттестат|выпускн\w+ вечер", (6, 27)),
            (r"день победы|9 мая", (5, 9)), (r"день защитника отечества|23 февраля", (2, 23)), (r"международн\w+ женск|8 марта", (3, 7)),
            (r"нов\w+ год", (12, 27)), (r"снятия блокады|27 января", (1, 27)), (r"день учителя", (10, 4)), (r"день матери", (11, 24)),
            (r"маслениц", (3, 1)), (r"день здоровья", (4, 7)), (r"день космонавтики", (4, 12)), (r"семьи, любви и верности", (7, 8)),
            (r"народного единства", (11, 4)), (r"день россии", (6, 12)), (r"защиты детей", (6, 1)), (r"русского языка|пушкинск\w+ день", (6, 6)),
            (r"начала блокады|жертв фашизма", (9, 8))]
JUNK = re.compile(r"политик\w* обработки персональных|cookies|яндекс метрика|^\d{6},|^фотографии$|^https?://|официальные информационные ресурсы", re.I)
# страницы старого сайта, где была именно лента новостей. На остальных (Кванториум, Орлята, советник, методработа)
# лежали описания разделов: они уже перенесены в тексты страниц нового сайта, в новости их не берём
FEEDS = ("novosti-shkoly", "nashi-meropriyatiya", "meropriyatiya", "smi-o-shkole", "spetsialnaya-voyennaya-operatsiya",
         "meropriyatiya-gol-stremitelniy", "shkolniy-sportivniy-klub", "dopolnitelnaya-informatsiya")
ABBR = {"ГТО", "СВО", "ВСОШ", "ОГЭ", "ЕГЭ", "ГИА", "МВД", "ФСБ", "РФ", "СПБ", "ДДТ", "ОДОД", "ШСК", "НТВ", "ЮИД", "ВК", "БПЛА", "ТЦБС",
        "ДДЮТ", "МЧС", "ГИБДД", "ДПС", "ПДД", "ОБЖ", "ИЗО", "ГОЛ", "ГБОУ", "IT", "СМИ", "ВФСК", "ЦПМСС", "ФИФА", "РДДМ"}
PROPER = re.compile(r"^(санкт|петербург|росси|российск|пушкинск|шушар|кванториум|янтар|орлят|первых|победы|ленинград|москв|минпросвещ|"
                    r"министерств|гофман|щелкунчик|героя|героев|отечеств|рождеств|пасх)", re.I)


def sentence_case(caps):
    """«ДЕНЬ ЗНАНИЙ В КВАНТОРИУМЕ» → «День знаний в Кванториуме». Аббревиатуры (ГТО, СВО, ВСОШ) остаются заглавными."""
    out = []
    for i, w in enumerate(caps.split()):
        core = re.sub(r"[^А-ЯЁA-Z]", "", w)
        if core in ABBR:
            out.append(w)
            continue
        low = w.lower()
        if i == 0 or PROPER.match(re.sub(r"^[«\"(]", "", low)) or (out and out[-1].endswith((".", "!", "?"))):
            m = re.match(r"^([«\"(]*)(.*)$", low)
            low = m.group(1) + m.group(2)[:1].upper() + m.group(2)[1:]
        out.append(low)
    return " ".join(out)


def _first_sentence(src):
    """Первая фраза: конец на . ! ? или после закрывающей кавычки перед заглавной. «ул.», «А.Д.», «2024г.» и кавычки не рвём."""
    for mm in re.finditer(r"(?<=[.!?…])\s+(?=[А-ЯЁA-Z«\"\d])|(?<=[»\"])\s+(?=[А-ЯЁ])", src):
        before = src[:mm.start()]
        opened = before.count("«") - before.count("»") + (before.count('"') % 2)
        if opened > 0:
            continue
        prev_word = (re.findall(r"(\S+)$", before) or [""])[0]
        core = prev_word.rstrip(".!?…").strip("«»\"()")
        if before.endswith(".") and (len(core) <= 3 or re.match(r"\d", core) or re.search(r"[А-ЯЁ]\.[А-ЯЁ]$", core)):
            continue
        if mm.start() >= 15:
            return src[:mm.start()]
    return src


def split_title(title, body):
    """Заголовок и текст новости. Тильда то склеивает заголовок с первой фразой, то отдаёт заголовок отдельно."""
    text = re.sub(r"\s+", " ", " ".join(body)).strip()
    t = re.sub(r"\s+", " ", title or "").strip()
    full = text if (not t or text.startswith(t.rstrip(".!?…")[:max(10, len(t) - 3)])) else (t + " " + text).strip()
    # шапка капсом: «ДЕНЬ ЗНАНИЙ Сегодня в стенах школы…»
    m = re.match(r"^([«\"]?[А-ЯЁA-Z0-9][А-ЯЁA-Z0-9\s«»\"'’.,:!?№\-–—()|]{3,}?)(?=\s+[А-ЯЁA-Z]?[а-яёa-z]|$)", full)
    if m:
        head = m.group(1).strip(" |")
        tail = re.search(r"(\s+(?:В|ВО|С|СО|К|О|ОБ|У|И|НА|ПО|ИЗ|ОТ|ДО|ЗА|\d{1,2}))+$", head)
        if tail:
            head = head[:tail.start()]
        letters = [ch for ch in head if ch.isalpha()]
        if len(letters) >= 4 and sum(ch.isupper() for ch in letters) / len(letters) > 0.85:
            return sentence_case(head).rstrip(".:"), full[len(head):].strip(" .:")
    first = _first_sentence(full)
    if len(first) <= 120:
        return first.rstrip("."), full[len(first):].strip()
    short = first[:117].rsplit(" ", 1)[0].rstrip(",;:—–- ")
    return short + "…", full  # длинная фраза: в заголовок сокращённо, текст целиком


def photo_hash(path):
    """Отпечаток фото 16×16 для поиска дублей и разброс яркости (пустые картинки почти однотонные)."""
    from PIL import Image, ImageStat
    with Image.open(path) as im:
        g = im.convert("L")
        spread = ImageStat.Stat(g).stddev[0]
        small = g.resize((16, 16))
        px = list(small.tobytes())
    avg = sum(px) / len(px)
    return "".join("1" if v > avg else "0" for v in px), spread


def paragraphs(text):
    parts = re.split(r"(?<=[.!?»])\s+(?=[А-ЯЁA-Z«—–-])", text)
    out, cur = [], ""
    for p_ in parts:  # склеиваем короткие фразы в абзацы по 2–4 предложения
        cur = (cur + " " + p_).strip()
        if len(cur) > 280:
            out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return out


def find_daymonth(text):
    t = text.lower()
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(20\d\d|\d\d)(?!\d)", t)
    if m:
        y = int(m.group(3))
        return (y + 2000 if y < 100 else y), int(m.group(2)), int(m.group(1))
    m = re.search(r"\b(\d{1,2})\s+" + MRE + r"(?:\s+(20\d\d))?", t)
    if m:
        mon = next(i + 1 for i, s in enumerate(MONTHS) if m.group(2).startswith(s))
        return (int(m.group(3)) if m.group(3) else None), mon, int(m.group(1))
    for pat, (mon, day) in HOLIDAYS:
        if re.search(pat, t):
            return None, mon, day
    return None


def assign_dates(items, start):
    """Новости одной страницы от новых к старым. Даты из текста — опорные точки, если идут по порядку;
    между ними даты распределяются равномерно. Такие даты помечаются как примерные."""
    prev = start
    anchors = {}
    for k, it in enumerate(items):
        head = it["title"] + " " + it["text"][:400]
        found = find_daymonth(head)
        if not found:
            continue
        y, mon, day = found
        day = min(day, 28) if mon == 2 else min(day, 30)
        try:
            if y:
                d = date(y, mon, day)
                full = True
            else:
                d = date(prev.year if (mon, day) <= (prev.month, prev.day) else prev.year - 1, mon, day)
                full = False
        except ValueError:
            continue
        if d <= prev and (prev - d).days < (1100 if full else 370):
            anchors[k] = (d, full)
            prev = d
    keys = sorted(anchors)
    for k, it in enumerate(items):
        if k in anchors:
            it["date"], it["exact"] = anchors[k][0], anchors[k][1]
            continue
        newer = max((a for a in keys if a < k), default=None)
        older = min((a for a in keys if a > k), default=None)
        if newer is not None and older is not None:
            d1, d2 = anchors[newer][0], anchors[older][0]
            frac = (k - newer) / (older - newer)
            it["date"] = d1 - (d1 - d2) * frac
        elif newer is not None:
            it["date"] = anchors[newer][0]
        elif older is not None:
            it["date"] = anchors[older][0]
        else:
            it["date"] = start
        it["exact"] = False
    return items


def run(zip_path, user="перенос"):
    tmp = os.path.join(BASE, "..", "data", "_news_import")
    shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(tmp)
    root = next(os.path.join(dp) for dp, dn, fn in os.walk(tmp) if "news.json" in fn)
    raw = json.load(open(os.path.join(root, "news.json"), encoding="utf-8"))
    os.makedirs(UPLOADS, exist_ok=True)
    by_page = {}
    for it in raw:
        if not any(f in (it.get("source") or "") for f in FEEDS):
            continue
        body = [re.sub(r"(?:\s*#[\wа-яё]+)+\s*$", "", x, flags=re.I) for x in it.get("body", [])]  # хештеги в конце
        title, text = split_title(it.get("title", ""), [x for x in body if x.strip()])
        if JUNK.search(title + " " + text) or (len(text) < 60 and not it.get("images")):
            continue
        by_page.setdefault(it.get("source", ""), []).append({**it, "title": title, "text": text})
    seen, n = set(), 0
    for src, items in by_page.items():
        assign_dates(items, date.today())
        for it in items:
            key = re.sub(r"\W", "", (it["title"] + it["text"][:80]).lower())[:120]
            if key in seen:
                continue
            seen.add(key)
            imgs, hashes = [], []
            for nm in it.get("images", []):
                f = os.path.join(root, "img", nm)
                if not os.path.exists(f):
                    continue
                h, spread = photo_hash(f)
                if spread < 8:
                    continue  # почти однотонная картинка: декоративный фон Тильды, не фото
                if any(sum(a != b for a, b in zip(h, x)) < 30 for x in hashes):
                    continue  # то же фото ещё раз (Тильда хранила его в нескольких размерах)
                hashes.append(h)
                shutil.copy(f, os.path.join(UPLOADS, nm))
                imgs.append(f"/static/uploads/news/{nm}")
            paras = paragraphs(it["text"])
            body = "\n\n".join(paras + imgs[1:])  # первое фото — обложка, остальные галереей после текста
            lead = paras[0] if paras else ""
            if len(lead) > 160:
                lead = lead[:157].rsplit(" ", 1)[0] + "…"
            slug = slugify(it["title"])
            if db.q1("SELECT id FROM news WHERE slug=?", (slug,)):
                slug += "-" + secrets.token_hex(2)
            old = db.q1("SELECT id FROM news WHERE import_key=?", (key,))
            vals = (it["title"][:200], it["date"].isoformat(), it.get("rubric") or "Школа", lead, imgs[0] if imgs else None, body, 1, db.now(), 1 if it["exact"] else 0, key)
            if old:  # повторная загрузка обновляет, а не дублирует
                db.run("UPDATE news SET title=?,date=?,rubric=?,lead=?,cover=?,body=?,published=?,updated=?,date_exact=?,import_key=? WHERE id=?", vals + (old["id"],))
            else:
                db.run("INSERT INTO news(title,date,rubric,lead,cover,body,published,updated,date_exact,import_key,slug) VALUES(?,?,?,?,?,?,?,?,?,?,?)", vals + (slug,))
            n += 1
    shutil.rmtree(tmp, ignore_errors=True)
    db.log(user, "Новости", f"загрузил со старого сайта ({n})", os.path.basename(zip_path))
    return n


if __name__ == "__main__":
    print("новостей загружено:", run(sys.argv[1]))
