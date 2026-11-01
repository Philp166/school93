"""Первичное наполнение базы: контакты, приём, люди и документы со старого сайта, пользователь-администратор.
Запуск: python -m app.seed [путь к files.csv со старого сайта]"""
import csv
import json
import os
import sys

from . import db
from .admin import hash_pw, kind_of
from .content import REDIRECTS, PAGES

B1, B2 = "Школьная, 19", "Первомайская, 30"

CONTACTS = {
    "full_name": "Государственное бюджетное общеобразовательное учреждение школа №93 Пушкинского района Санкт-Петербурга",
    "short_name": "ГБОУ школа №93 Пушкинского района Санкт-Петербурга",
    "created": "11 июня 2014 года",
    "legal_address": "196624, Санкт-Петербург, пос. Шушары, Школьная ул., д. 19, лит. А",
    "email": "sh93@obr.gov.spb.ru", "hours": "Пн–пт, 8:00–20:00", "reception": "четверг, 16:00–18:00",
    "hotline": "(812) 611-13-31", "director_day": "Второй четверг месяца", "director_time": "16:00–18:00",
    "director_place": "Первомайская, 30, каб. 4021", "pos_widget": "",
    "buildings": [
        {"address": B1, "address_full": "Школьная ул., 19", "phone": "(812) 611-13-31", "room": "", "extra": ["Факс", "(812) 611-13-10"], "safe_route": ""},
        {"address": B2, "address_full": "Первомайская ул., 30", "phone": "(812) 611-13-16", "room": "4022", "extra": ["Кабинет директора", "4021"], "safe_route": ""},
    ],
    "founders": [
        ["Учредитель", "Санкт-Петербург в лице уполномоченных исполнительных органов государственной власти"],
        ["Комитет по образованию Санкт-Петербурга", "Председатель: Путиловская Наталия Геннадьевна<br>Санкт-Петербург, пер. Антоненко, 8, лит. А"],
        ["Администрация Пушкинского района", "Глава администрации: Чапуров Андрей Владимирович<br>Пушкин, Октябрьский бульвар, 24"],
        ["Комитет имущественных отношений", "Врио председателя: Макаров Сергей Владимирович<br>Санкт-Петербург, Новгородская ул., 20, лит. А"],
    ],
    "requisites": [
        ["ИНН / КПП", "7820337251 / 782001001"], ["ОГРН", "1147847205681"],
        ["Получатель", "Комитет финансов Санкт-Петербурга (ГБОУ школа №93 Пушкинского района Санкт-Петербурга, л/с 0731119)"],
        ["Банк", "Северо-Западное ГУ Банка России / УФК по г. Санкт-Петербургу"], ["БИК", "014030106"],
        ["Казначейский счёт", "03224643400000007200"], ["Единый казначейский счёт", "40102810945370000005"], ["ОКТМО", "40901000000"],
    ],
}

ADMISSION = {
    "status1": "soon", "year1": "2027/28", "open_date": "1 апреля",
    "soon_text": "Заявления на Госуслугах принимаются с 1 апреля. Первыми подают семьи с регистрацией на закреплённой территории и льготными категориями.",
    "open_text": "Заявления принимаются только через Госуслуги. Сроки и порядок ниже.",
    "closed_text": "Подайте заявление в соседнюю школу посёлка Шушары, где места есть: школа №459 или школа №686, микрорайон «Центральная усадьба». Заявление подаётся так же, через Госуслуги.",
    "year10": "2026/27", "classes10": "6", "seats10": "25",
    "dates10": [["Ученики школы 93", "25–30 июня 2026"], ["Ученики школы 93, второй срок", "25 августа 2026"], ["Ученики других школ, при наличии мест", "27 августа 2026"]],
    "vacant": [["1 класс", "0", "0", "0", "0"], ["10 класс", "0", "26", "0", "0"]],
}
LAGER = {"shift": "Весенняя смена", "dates": "30 марта – 3 апреля 2026", "seats": "25",
         "price_full": "3 355 ₽", "price_part": "1 342 ₽", "price_free": "Бесплатно"}
FOOD_PRICES = [["Завтрак, 5–11 классы", "145 ₽"], ["Обед, 1–4 классы", "185 ₽"], ["Обед, 5–11 классы", "217 ₽"]]
ODOD = {"hours": "пн–пт, 14:40–19:35", "reception": "чт, 16:00–18:00", "phone": "(812) 611-13-32"}


def P(name, position, tags, phone="", email="", building="", grp="", duty="", pos=100):
    return dict(name=name, position=position, tags=tags, phone=phone, email=email, building=building, grp=grp, duty=duty, pos=pos)


PEOPLE = [
    P("Яшина Татьяна Владимировна", "Директор", ["admin", "director"], duty="Почётный работник воспитания и просвещения Российской Федерации, победитель всероссийского конкурса «Лучший директор образовательного учреждения»", pos=1),
    P("Шевцова Виктория Владимировна", "Заместитель директора по УВР", ["admin", "priem1"], "(812) 611-13-09", grp="Учёба", duty="1–4 классы", pos=10),
    P("Жидова Татьяна Алексеевна", "Заместитель директора по УВР", ["admin"], "(812) 611-13-54", "zhidova_tatyana@mail.ru", grp="Учёба", duty="5–11 классы, кафедра русского языка и литературы", pos=11),
    P("Скрипко Марина Иосифовна", "Заместитель директора по УВР", ["admin", "perevod"], "(812) 611-13-70", "miskripko1964@mail.ru", grp="Учёба", duty="домашнее обучение, экстернат, семейное образование", pos=12),
    P("Пылинина Ольга Сергеевна", "Заведующая учебной частью", ["admin", "raspisanie", "perevod"], "(812) 611-13-81", "olpyl2016@gmail.com", grp="Учёба", duty="расписание, зачисление и перевод", pos=13),
    P("Беляков Андрей Леонидович", "Заместитель директора по ИКТ", ["admin"], "(812) 611-13-19", "belyakov-sh93@mail.ru", grp="Учёба", duty="электронный дневник", pos=14),
    P("Касаткина Ирина Владимировна", "Заместитель директора по УВР", ["admin", "minpros"], grp="Учёба", duty="проект «Школа Минпросвещения России»", pos=15),
    P("Чибитько Алексей Сергеевич", "Заместитель директора по УВР", ["admin"], "(812) 611-13-31", "al7855@yandex.ru", grp="Кафедры", duty="кафедра истории и обществознания", pos=20),
    P("Прелова Лариса Викторовна", "Заместитель директора по УВР", ["admin"], "", "prelova-sh93@mail.ru", grp="Кафедры", duty="кафедра математики", pos=21),
    P("Саморока Евгения Анатольевна", "Заместитель директора по УВР", ["admin", "lager"], "", "e.a.samoroka-sh93@mail.ru", grp="Кафедры", duty="английский язык, ИЗО, технология, музыка", pos=22),
    P("Платова Марианна Витальевна", "Заместитель директора по УВР", ["admin"], "", "Platova78@mail.ru", grp="Кафедры", pos=23),
    P("Бабурина Людмила Анатольевна", "Заместитель директора по воспитательной работе", ["admin"], "", "Ljubaburina@rambler.ru", grp="Воспитание и досуг", duty="1–4 классы", pos=30),
    P("Родионов Антон Александрович", "Заместитель директора по воспитательной работе", ["admin"], "", "antonrodionov1@ya.ru", grp="Воспитание и досуг", duty="5–11 классы", pos=31),
    P("Гребенщиков Дмитрий Николаевич", "Руководитель ОДОД", ["admin"], "(812) 611-13-32", "ododshkola93@mail.ru", grp="Воспитание и досуг", duty="бесплатные кружки и секции", pos=32),
    P("Замбори Наталья Юрьевна", "Заведующая бассейном", ["admin", "bassein"], "(812) 611-13-60, доб. 2189", grp="Воспитание и досуг", pos=33),
    P("Аристов Александр Владимирович", "Заместитель директора по АХР", ["admin"], "(812) 611-13-30", "ssm.797@mail.ru", grp="Хозяйство и безопасность", pos=40),
    P("Дю Александр Александрович", "Заместитель директора по безопасности", ["admin"], "", "du.aa.93@yandex.ru", grp="Хозяйство и безопасность", pos=41),
    P("Клевцова Елена Петровна", "Заместитель директора по развитию", ["admin"], "(812) 611-13-08", "yrist@bk.ru", grp="Хозяйство и безопасность", duty="платные услуги", pos=42),
    P("Окаша Светлана Михайловна", "Заведующая библиотекой", ["admin", "biblioteka"], "", "C-27@mail.ru", grp="Хозяйство и безопасность", pos=43),
    P("Гуляева Татьяна Геннадьевна", "По вопросам обучения детей с ОВЗ", ["ovz"], duty="кабинет 4001"),
    P("Осипова Марина Борисовна", "Заведующая музейным комплексом", ["muzey"]),
    P("Воронин Павел Александрович", "Советник директора по воспитанию", ["sovetnik", "pervye"], duty="куратор отделения «Движения Первых»"),
    P("Цветкова Карина Анатольевна", "Советник директора по воспитанию", ["sovetnik"], duty="педагог-организатор высшей категории"),
    P("Спасибухов Даниил Николаевич", "Начальник лагеря", ["lager"]),
    P("Мезенцева Светлана Александровна", "Методист Кванториума", ["kvant"], pos=1),
    P("Есева Анна Олеговна", "Руководитель психологической службы", ["psiholog", "lead"]),
    P("Звягинцева Ольга Владимировна", "Руководитель логопедической службы", ["logoped", "lead"]),
    P("Маркова Наталья Геннадьевна", "Руководитель социальной службы", ["social", "lead"]),
    P("Евгеньева Александра Дмитриевна", "Социальный педагог", ["social"]),
    P("Гураль Мирослава Васильевна", "Социальный педагог", ["social"]),
    P("Буга Станислав Сергеевич", "Социальный педагог", ["social"]),
    P("Халус Ликсиния Валерьевна", "Медицинская сестра", ["med"], "(812) 611-13-15", building=B1, duty="кабинет 138"),
    P("Пименова Елена Фёдоровна", "Фельдшер", ["med"], "(812) 611-13-25", building=B2, duty="кабинет 1045"),
    P("Степанова Анастасия Владимировна", "Фельдшер", ["med"], "(812) 611-13-25", building=B2, duty="кабинет 1045"),
]
for n in ["Бондаренко Елена Евгеньевна", "Грецкая Ксения Витальевна", "Шпикова Наталья Петровна", "Мурашкина Екатерина Викторовна", "Сахарова Вера Игоревна", "Павлова Елена Павловна", "Зейналова Вусала Шаммед кызы"]:
    PEOPLE.append(P(n, "Педагог-психолог", ["psiholog"], building=B2))
for n in ["Головина Оксана Владимировна", "Кашина Ксения Алексеевна", "Пшенникова Юлия Константиновна", "Согомонян Карина Мартиковна"]:
    PEOPLE.append(P(n, "Педагог-психолог", ["psiholog"] + (["logoped"] if n.startswith("Головина") else []), building=B1))
for n in ["Губарева Ирина Владимировна", "Салькова Лилия Александровна", "Андреева Светлана Руслановна", "Соколова Елизавета Александровна", "Шаповалова Елена Валентиновна", "Гаврилова Татьяна Сергеевна", "Штанова Юлия Олеговна", "Хоменя Наталья Борисовна", "Баранова Илона Дмитриевна", "Архипова Ольга Геннадьевна"]:
    PEOPLE.append(P(n, "Учитель-логопед", ["logoped"], building=B2))
for n in ["Яковлева Елена Геннадьевна", "Виданова Ирина Николаевна", "Доржиева Анжелика Александровна"]:
    PEOPLE.append(P(n, "Учитель-логопед", ["logoped"], building=B1))
for n in ["Макаров Алексей Дмитриевич", "Романов Алексей Владимирович", "Борхсениус Андрей Сергеевич", "Рязанцева Мария Владимировна", "Головнина Виктория Георгиевна", "Немчинович Людмила Витальевна", "Ефимова Альфия Рафаилевна", "Иванова Екатерина Олеговна", "Юрченко Екатерина Михайловна", "Максимова Наталья Евгеньевна", "Канева Татьяна Владимировна"]:
    PEOPLE.append(P(n, "Педагог Кванториума", ["kvant"]))

CLUBS = [("Театральная студия «Открытая маска»", "Художественная", "Дорожко Т. М."), ("Театральная студия «Новый взгляд»", "Художественная", "Цветкова К. А."),
         ("Литературная студия «Живое слово»", "Художественная", "Тимохов Л. Н."), ("Футбольный клуб «Янтарь 93»", "Физкультурно-спортивная", "Школьный спортивный клуб"),
         ("Школьный спортивный клуб «Феникс»", "Физкультурно-спортивная", "")]
VACANCIES = ["Учитель русского языка и литературы", "Учитель математики", "Учитель физики", "Учитель информатики", "Учитель-дефектолог",
             "Помощник воспитателя ОДОД", "Тренер по настольному теннису", "Врач бассейна", "Контрактный управляющий", "Уборщик территории", "Уборщик служебных помещений"]

NEWS = [
    ("2026-09-15", "Спорт", "«Янтарь 93» выиграл отборочный этап и едет на финал в Нижний Новгород", "Сборная школы первой из Петербурга прошла в финал: три победы в плей-офф.", "Футбольная команда школы выиграла отборочный этап проекта «Футбол в школе». В плей-офф ребята провели три игры и не пропустили почти ни одного мяча.\n\nФинал пройдёт в Нижнем Новгороде. Поздравляем команду и тренеров!"),
    ("2026-09-10", "Кванториум", "Космическая викторина для «Орлят России»", "Методист Кванториума рассказала, как «Луна-16» доставила на Землю лунный грунт.", "Ученики начальной школы, участники программы «Орлята России», побывали на космической викторине в Кванториуме.\n\nМетодист технопарка Светлана Александровна Мезенцева рассказала о станции «Луна-16», которая впервые в автоматическом режиме доставила на Землю лунный грунт."),
    ("2026-08-28", "Школа", "Корпус на Первомайской, 30 готов к учебному году", "Классы, столовая и спортзал проверены и приняты к 1 сентября.", "Корпус на Первомайской, 30 прошёл приёмку к новому учебному году."),
    ("2026-05-20", "СМИ о нас", "Наш учитель в репортаже НТВ", "Как проходят уроки с искусственным интеллектом в начальной школе.", "Съёмочная группа НТВ побывала на уроке в начальной школе, где ученики работают с помощником на основе искусственного интеллекта."),
    ("2026-04-18", "Кванториум", "Малыши из детского сада в Агролаборатории", "Воспитанники группы «Бегемотик» побывали на мастер-классах Кванториума.", "Воспитанники детского сада побывали на мастер-классах в Агролаборатории Кванториума."),
    ("2026-03-12", "Профориентация", "Мастер-классы медицинского колледжа и клиник", "Скорая помощь, роддом и клиники показали старшеклассникам свою работу.", "Многопрофильный медицинский колледж провёл для старшеклассников мастер-классы вместе с клиниками, скорой помощью и роддомом."),
    ("2026-02-08", "Кванториум", "День науки в Кванториуме", "Опыты, лаборатории и научные бои для учеников 5–9 классов.", "В Кванториуме прошёл ежегодный День науки."),
    ("2025-10-21", "Профориентация", "День университета гражданской авиации", "Проректор и деканы рассказали старшеклассникам о профессиях в авиации.", "К нам приехал Санкт-Петербургский государственный университет гражданской авиации имени А. А. Новикова. Проректор и деканы факультетов рассказали ученикам школы 93 и школы 604, как устроено обучение и работа в авиации.\n\n## Кто выступил\n\nПроректор по учебной работе Ильгизар Миннисламович Хаертдинов, деканы факультетов транспортных систем и безопасности, аэропортов и инженерно-технического обеспечения полётов, экономики, управления и права.\n\nБольше всего вопросов было о практической работе в авиации."),
]


def seed(files_csv=None):
    n = _seed(files_csv)
    from . import blocks_store
    blocks_store.ensure_all()
    return n


def _seed(files_csv=None):
    db.init()
    db.set_setting("contacts", CONTACTS)
    db.set_setting("admission", ADMISSION)
    db.set_setting("lager", LAGER)
    db.set_setting("food_prices", FOOD_PRICES)
    db.set_setting("odod", ODOD)
    db.set_setting("food_pattern", {"g1": "{date}-sm.xlsx", "g2": "{date}-sm-2.xlsx"})
    if not db.q1("SELECT id FROM people LIMIT 1"):
        for x in PEOPLE:
            db.run("INSERT INTO people(name,position,duty,phone,email,building,grp,tags,pos,updated) VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (x["name"], x["position"], x["duty"], x["phone"], x["email"], x["building"], x["grp"], json.dumps(x["tags"], ensure_ascii=False), x["pos"], db.now()))
    if not db.q1("SELECT id FROM clubs LIMIT 1"):
        for t, d, teacher in CLUBS:
            db.run("INSERT INTO clubs(title,direction,teacher) VALUES(?,?,?)", (t, d, teacher))
    if not db.q1("SELECT id FROM vacancies LIMIT 1"):
        for v in VACANCIES:
            db.run("INSERT INTO vacancies(title,active) VALUES(?,1)", (v,))
    # фото директора
    db.run("UPDATE people SET photo=? WHERE name LIKE 'Яшина Татьяна%' AND (photo IS NULL OR photo='')", ("/static/img/people/yashina-tatyana.webp",))
    # новости: настоящие со старого сайта, если рядом лежит архив парсера (news_export.zip)
    if not db.q1("SELECT id FROM news LIMIT 1"):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for zp in (os.environ.get("S93_NEWS_ZIP", ""), os.path.join(root, "data", "news_export.zip"), os.path.join(root, "news_export.zip")):
            if zp and os.path.exists(zp):
                from . import import_news
                import_news.run(zp)
                break
    if not db.q1("SELECT id FROM users LIMIT 1"):
        pw = os.environ.get("S93_ADMIN_PASSWORD", "school93-admin")
        db.run("INSERT INTO users(login,name,role,pw) VALUES('admin','Администратор','admin',?)", (hash_pw(pw),))
    n = 0
    if files_csv and os.path.exists(files_csv) and not db.q1("SELECT id FROM docs LIMIT 1"):
        n = import_docs(files_csv)
    # главные документы: то, что родитель заполняет сам
    for pat in MAIN_DOCS:
        db.run("UPDATE docs SET main_doc=1 WHERE title LIKE ?", (pat,))
    # документы, которые нужны ещё и на другой странице
    for pat, page, grp in EXTRA_PLACES:
        for d in db.q("SELECT id FROM docs WHERE title LIKE ?", (pat,)):
            db.run("INSERT OR IGNORE INTO doc_places(doc_id,page,grp,pos) VALUES(?,?,?,0)", (d["id"], page, grp))
    return n


GENERIC = {"положение", "приказ", "памятка", "буклет", "письмо", "распоряжение", "презентация", "документ", "алгоритм", "план работы",
           "приложение", "расписание занятий", "расписание отделения", "заявление", "согласие", "инструкция", "протокол", "отчет", "отчёт",
           "программа", "план", "справка", "регламент", "порядок", "правила", "уведомление", "договор", "перечень", "график",
           "постановление", "указ", "методические рекомендации"}


def restored_titles(md_path):
    """На старом сайте кнопки назывались «Приказ», «Расписание занятий», а полное название стояло текстом рядом.
    Ищем в тексте страницы строку, которая начинается с того же слова, по порядку ссылок."""
    import re
    if not os.path.exists(md_path):
        return {}
    text = open(md_path, encoding="utf-8").read().replace("\r", "")
    out = {}

    def clean(l):
        return re.sub(r"\s+", " ", re.sub(r"^[-•*\d.)\s]+", "", l)).strip()
    for page in text.split("\n---\n")[1:]:
        if "**Документы на странице:**" not in page:
            continue
        body, docs = page.split("**Документы на странице:**", 1)
        links = re.findall(r"- \[([^\]]*)\]\(([^)]+)\)", docs)
        raw = [l.strip() for l in body.splitlines() if l.strip() and not l.startswith(("#", "URL:", "Title:"))]
        lines = []
        for i, l in enumerate(raw):
            c = clean(l)
            if i + 1 < len(raw) and c.lower().rstrip(".") in GENERIC and clean(raw[i + 1])[:1] in "\"«":
                c = c + " " + clean(raw[i + 1])
            lines.append(c)
        used, pos = set(), 0
        for txt, url in links:
            key = txt.strip().lower().rstrip(".:")
            if key not in GENERIC:
                continue
            for j in range(pos, len(lines)):
                L = lines[j]
                if j not in used and L.lower().startswith(key) and len(L) > len(key) + 4 and len(L) < 300 and "http" not in L:
                    out[url.strip()] = L.rstrip(" .;,")
                    used.add(j)
                    pos = j + 1
                    break
    return out


GROUP_BY_OLD = {"/psikhologo-pedagogicheskaya-sluzhba-shkoly": "Психологическая служба", "/logopedicheskaya-sluzhba-shkoly": "Логопедическая служба",
                "/sotsialnaya-sluzhba-shkoly": "Социальная служба", "/meditsinskaya-sluzhba": "Медицинский кабинет",
                "/shkolnaya-sluzhba-mediatsii": "Служба медиации", "/dokumenty-detskogo-tekhnoparka-kvantorium": "Документы технопарка",
                "/polezniy-kontent": "Как уберечь ребёнка от вербовки и мошенников"}


MAIN_DOCS = ["Заявление о приеме в ОДОД%", "Заявление на прием в школу%", "Заявление на питание%", "Заявление от родителей (законных представителей) обучающихся, заявивших%",
             "Форма записки от родителей%", "Заявление на компенсационную выплату%"]
EXTRA_PLACES = [("Правила внутреннего распорядка обучающихся%", "/roditelyam/pravila", "Для учеников"),
                ("Порядок организации индивидуального отбора%", "/postuplenie/10-klass", "Приём в 10 класс")]


def import_docs(path):
    """Документы со старого сайта. Основной источник: data/doc_titles.csv — названия, восстановленные
    по тексту рядом с кнопками на старом сайте, и группы по заголовкам блоков. Запасной: files.csv."""
    import re as _re
    base = os.path.dirname(path)
    titles_csv = os.path.join(base, "doc_titles.csv")
    if not os.path.exists(titles_csv):
        return import_docs_raw(path)
    old_titles = {}
    pages_csv = os.path.join(base, "pages.csv")
    if os.path.exists(pages_csv):
        with open(pages_csv, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f, delimiter=";"):
                old_titles[r["URL"].replace("https://shkola93.ru", "").rstrip("/") or "/"] = r["Title"]
    rows = list(csv.DictReader(open(titles_csv, encoding="utf-8-sig"), delimiter=";"))
    # сколько старых страниц сливается в каждую новую: если больше одной, пустую группу заменяем названием старой страницы
    sources = {}
    for r in rows:
        old = r["page"].replace("https://shkola93.ru", "").rstrip("/") or "/"
        new = REDIRECTS.get(old, old).split("?")[0]
        sources.setdefault(new, set()).add(old)
    best = {}  # у одного файла на разных страницах бывают разные подписи: берём самую полную
    for r in rows:
        if r["how"] != "выкинуто" and r["title"].strip():
            u = r["url"].strip()
            if len(r["title"]) > len(best.get(u, "")):
                best[u] = r["title"].strip()
    n, placed, doc_ids = 0, set(), {}
    for pos, r in enumerate(rows):
        if r["how"] == "выкинуто" or not r["title"].strip():
            continue
        old = r["page"].replace("https://shkola93.ru", "").rstrip("/") or "/"
        new = REDIRECTS.get(old, old).split("?")[0]
        url = r["url"].strip()
        title = best.get(url, r["title"].strip())
        if r["place"] != "1" and url not in doc_ids:
            continue  # файлы без подписи (например «р. р») в админку не тащим
        did = doc_ids.get(url)
        if did is None:
            ex = db.q1("SELECT id FROM docs WHERE url=?", (url,))
            did = ex["id"] if ex else db.run("INSERT INTO docs(title,url,kind,updated) VALUES(?,?,?,?)", (title[:300], url, kind_of(url), db.now()))
            doc_ids[url] = did
        if r["place"] != "1" or new not in PAGES or new == "/" or new == "/novosti":
            continue
        targets = [new] + (["/roditelyam/pitanie"] if old == "/organizatsiya-pitaniya-v-obrazovatelnoy-organizatsii" else [])
        for tgt in targets:
            grp = r.get("grp", "").strip()
            if tgt == "/ucheba/raspisanie":
                grp = B2 if "первомай" in title.lower() else B1
                title = _re.sub(r"\s*\(?(Школьная,? 19|Первомайская,? 30)\)?\s*$", "", title)
                db.run("UPDATE docs SET title=? WHERE id=?", (title, did))
            elif old in GROUP_BY_OLD:
                grp = GROUP_BY_OLD[old]
            elif not grp and len(sources.get(tgt, ())) > 1:
                grp = old_titles.get(old, "")
            if (did, tgt) in placed:
                continue
            db.run("INSERT OR IGNORE INTO doc_places(doc_id,page,grp,pos) VALUES(?,?,?,?)", (did, tgt, grp, pos))
            placed.add((did, tgt))
            n += 1
    return n


def import_docs_raw(path):
    """Документы со старого сайта: ссылки на облака и файлы, без сквозных ссылок шапки и подвала."""
    seen, n = {}, 0
    better = restored_titles(os.path.join(os.path.dirname(path), "all_pages.md"))
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter=";"):
            if row.get("Сквозная") == "да" or row.get("Тип") not in ("документ", "облако"):
                continue
            old = row["Страница"].replace("https://shkola93.ru", "").rstrip("/") or "/"
            new = REDIRECTS.get(old, old).split("?")[0]
            if new not in PAGES or new == "/":
                continue
            url, title = row["URL"].strip(), (row["Текст ссылки"] or "").strip() or "Документ"
            if title.lower().rstrip(".:") in GENERIC and url in better:
                title = better[url]
            grp = ""
            if new == "/ucheba/raspisanie":
                grp = B2 if "первомай" in title.lower() else B1
                import re as _re
                title = _re.sub(r"\s*(Школьная,? 19|Первомайская,? 30)\s*$", "", title)
            key = (url, new)
            if key in seen:
                continue
            did = db.q1("SELECT id FROM docs WHERE url=?", (url,))
            did = did["id"] if did else db.run("INSERT INTO docs(title,url,kind,updated) VALUES(?,?,?,?)", (title[:300], url, kind_of(url), db.now()))
            db.run("INSERT OR IGNORE INTO doc_places(doc_id,page,grp,pos) VALUES(?,?,?,?)", (did, new, grp, len(seen)))
            seen[key] = did
            n += 1
    return n


if __name__ == "__main__":
    print("документов:", seed(sys.argv[1] if len(sys.argv) > 1 else None))
