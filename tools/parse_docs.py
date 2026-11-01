"""Собирает со старого shkola93.ru все ссылки на документы вместе с текстом рядом с ними.
На старом сайте кнопки часто называются «Приказ», «Положение», «Заявление», а что это за документ,
написано рядом: в строке таблицы, в пункте списка или в заголовке блока. Этот текст и нужен.
Результат: docs_context.csv рядом со скриптом."""
import csv
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

BASE = "https://shkola93.ru"
PAGES = ["/", "/antinarkoticheskaya-bezopasnost", "/antiterroristicheskaya-zaschischennost", "/bibliotechno-informatsionniy-tsentr-bits",
         "/chasto-zadavayemyye-voprosy", "/dokumenty", "/dokumenty-detskogo-tekhnoparka-kvantorium", "/dopolnitelnaya-informatsiya",
         "/dorozhnaya-bezopasnost", "/dvizheniye-pervykh", "/elektronniy-dnevnik", "/elektronnye-obrazovatelnye-resursy",
         "/federalniy-proyekt-shkola-minprosvescheniya-rossii", "/finansovo-khozyaystvennaya-deyatelnost", "/galereya", "/gia",
         "/gorodskoy-ozdorovitelniy-lager-stremitelniy", "/gotov-k-trudu-i-oborone", "/informatsionnaya-bezopasnost", "/kadetskie-klassy",
         "/kontakty", "/korporativniy-sportivniy-klub", "/kvantorium", "/lgotniy-proezd-v-transporte", "/logopedicheskaya-sluzhba-shkoly",
         "/lokalnyye-normativnyye-dokumenty-shkoly", "/mat-tekh-obespecheniye-dostupnaya-sreda", "/meditsinskaya-sluzhba", "/meropriyatiya",
         "/meropriyatiya-gol-stremitelniy", "/mestonakhozhdenie", "/mezhdunarodnoe-sotrudnichestvo", "/muzey-svo", "/nashi-meropriyatiya",
         "/nastavnichestvo", "/navigatory-detstva", "/novosti-metodicheskoy-raboty", "/novosti-shkoly", "/obrazovanie",
         "/obrazovatelnaya-deyatelnost", "/obrazovatelnye-standarty-i-trebovaniya", "/obucheniye-detey-s-ogranichennymi-vozmozhnostyami-zdorovya",
         "/obucheniye-s-primeneniyem-distantsionnykh-obrazovatelnykh-tekhnologiy", "/odod", "/organizatsiya-pitaniya-v-obrazovatelnoy-organizatsii",
         "/orlyata-rossii", "/osnovnye-svedeniya", "/osnovy-religioznykh-kultur-i-svetskoy-etiki", "/otvetstvennost-roditeley", "/page33194858.html",
         "/pedagogicheskiy-sostav", "/platnye-obrazovatelnye-uslugi", "/polezniy-kontent", "/pozharnaya-bezopasnost",
         "/prava-obyazannosti-i-otvetstvennost-nesovershennoletnikh", "/pravovaya-pomosch-roditelyam-i-detyam",
         "/predpisaniya-kontroliruyuschikh-organov-i-ikh-ispolnenie", "/priyem-v-10-klass", "/priyom-v-1-klass",
         "/profilniy-psikhologo-pedagogicheskiy-klass", "/proforientatsiya", "/programma-razvitiya-shkoly", "/protivodeystvie-korruptsii",
         "/psikhologo-pedagogicheskaya-sluzhba-shkoly", "/pushkinskaya-karta", "/rabota-s-talantlivymi-detmi", "/raspisanie-zanyatiy",
         "/rasshirenie-kulturno-gumanitarnogo-i-nauchno-obrazovatelnogo-sotrudnichestva", "/rukovodstvo",
         "/shkola-93-i-spetsialnaya-voyennaya-operatsiya", "/shkolnaya-forma", "/shkolnaya-sluzhba-mediatsii",
         "/shkolniy-muzeyniy-kompleks-vremya-rossii", "/shkolniy-sportivniy-klub", "/shkolniy-teatr", "/smi-o-shkole",
         "/snizheniye-byurokraticheskoy-nagruzki-na-uchiteley", "/sotsialnaya-sluzhba-shkoly", "/sout", "/stipendii-i-mery-podderzhki-obuchayuschikhsya",
         "/stranitsa-sovetnika", "/struktura-i-organy-upravleniya-obrazovatelnoy-organizatsii", "/telefony-doveriya", "/uspekh-kazhdogo-rebenka",
         "/vakansii", "/vakantnye-mesta-dlya-priema-perevoda-obuchayuschikhsya", "/vospitatelnaya-deyatelnost", "/vserossiyskaya-olimpiada-shkolnikov",
         "/zdorovoye-pitaniye"]

DOC_HOSTS = ("cloud.mail.ru", "disk.yandex", "yadi.sk", "drive.google", "docs.google", "tildacdn", "static.tildacdn")
DOC_EXT = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip", ".rar")


def is_doc(href):
    h = (href or "").lower()
    return any(x in h for x in DOC_HOSTS) or h.split("?")[0].endswith(DOC_EXT)


def clean(s):
    s = re.sub(r"\s+", " ", s or "").strip(" -–—:;,.\u00a0")
    return s


def own_text(tag, a):
    """Текст элемента без текста самой ссылки и без других ссылок-документов."""
    parts = []
    for s in tag.find_all(string=True):
        par = s.find_parent("a")
        if par is not None and (par is a or is_doc(par.get("href"))):
            continue
        if s.parent.name in ("script", "style"):
            continue
        parts.append(s)
    return clean(" ".join(parts))


def context_for(a):
    rec = a.find_parent(class_="t-rec") or a.find_parent("body")
    # 1. та же строка таблицы, пункт списка или абзац
    for tag in a.parents:
        if tag is rec or tag is None:
            break
        if tag.name in ("tr", "li", "p") or (tag.get("class") and any(c in ("t-card__col", "t-item", "t-col") for c in tag.get("class"))):
            t = own_text(tag, a)
            if 6 < len(t) < 400:
                return t, "рядом"
            break
    # 2. ближайший текст перед ссылкой в том же блоке
    prev = []
    for s in rec.find_all(string=True):
        par = s.find_parent("a")
        if par is a:
            break
        if par is not None or s.parent.name in ("script", "style"):
            continue
        t = clean(s)
        if len(t) > 6:
            prev.append(t)
    if prev:
        return prev[-1][:400], "перед"
    return "", ""


def around(a):
    """Текст между предыдущей ссылкой-документом и этой (до) и между этой и следующей (после), в пределах блока."""
    rec = a.find_parent(class_="t-rec") or a.find_parent("body")
    seq = []  # элементы по порядку: ("a", tag) или ("t", текст)
    for s in rec.find_all(string=True):
        par = s.find_parent("a")
        if par is not None and is_doc(par.get("href")):
            if not seq or seq[-1][0] != "a" or seq[-1][1] is not par:
                seq.append(("a", par))
            continue
        if s.parent.name in ("script", "style"):
            continue
        t = clean(s)
        if t:
            seq.append(("t", t))
    idx = next((i for i, (k, v) in enumerate(seq) if k == "a" and v is a), None)
    if idx is None:
        return "", ""
    before, after = [], []
    for k, v in reversed(seq[:idx]):
        if k == "a":
            break
        before.insert(0, v)
    for k, v in seq[idx + 1:]:
        if k == "a":
            break
        after.append(v)
    return clean(" ".join(before))[:400], clean(" ".join(after))[:400]


def main():
    out = []
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (school93 migration)"
    for i, p in enumerate(PAGES, 1):
        url = BASE + p
        try:
            r = s.get(url, timeout=30)
            r.encoding = "utf-8"
        except Exception as e:
            print(f"[{i}/{len(PAGES)}] {p} ошибка: {e}")
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup.select("header, footer, .t-menu, .t228, .t450, .t-store"):
            tag.decompose()
        n = 0
        for a in soup.find_all("a", href=True):
            if not is_doc(a["href"]):
                continue
            ctx, where = context_for(a)
            before, after = around(a)
            rec = a.find_parent(class_="t-rec")
            head = ""
            if rec is not None:
                h = rec.find(class_=re.compile(r"t-title|t-name|t-section__title|t-heading"))
                head = clean(h.get_text(" ")) if h else ""
            out.append({"page": url, "url": a["href"].strip(), "link_text": clean(a.get_text(" ")),
                        "context": ctx, "where": where, "before": before, "after": after, "block_title": head[:200]})
            n += 1
        print(f"[{i}/{len(PAGES)}] {p}: ссылок на документы {n}")
        time.sleep(0.3)
    with open("docs_context2.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["page", "url", "link_text", "context", "where", "before", "after", "block_title"], delimiter=";")
        w.writeheader()
        w.writerows(out)
    print(f"\nГотово: {len(out)} ссылок, файл docs_context2.csv")


if __name__ == "__main__":
    sys.exit(main())
