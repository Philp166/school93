import csv,re,collections
rows=list(csv.DictReader(open('/mnt/user-data/uploads/docs_context2.csv',encoding='utf-8-sig'),delimiter=';'))
GEN={"положение","приказ","памятка","буклет","письмо","распоряжение","презентация","документ","алгоритм","план работы","приложение","расписание занятий","расписание отделения","заявление","согласие","инструкция","протокол","отчет","отчёт","отчеты","программа","план","справка","регламент","порядок","правила","уведомление","договор","перечень","график","постановление","указ","методические рекомендации","перечень учебников","правила пользования","список литературы","устав","приказы","положения","памятки","буклеты","рекомендации","информация","анкета","форма","образец","бланк","шаблон","лицензия","выписка"}
POINTER={"узнать больше","подробнее","ссылка","тут","здесь","скачать","смотреть","открыть"}
JUNK=re.compile(r'>>>|\b[tT]\d{2,4}\b|@classes:?[^А-ЯЁа-яё]*|noindex|/noindex|data-zoomable="yes"')
STOP=re.compile(r'\s(?=(Приказ|Распоряжение|Положение|Постановление|Письмо|Федеральный закон|Указ|Школьный этап|Муниципальный этап|Родительский контроль|Мониторинг питания|Категории обучающихся|Стоимость питания|График работы|Перечни|Уважаемые|Ссылка)\b)')
MANUAL={"адреса закреплены":"Распоряжение администрации Пушкинского района о закреплении территорий за школами",
        "годовым календарным":"Годовой календарный учебный график на 2026–2027 учебный год", "протоколы":"Протоколы районного этапа игр ШСК",
        "ссылка на видеоролики":"Видеоролики о Великой Отечественной войне","наглядные материалы":"Наглядные материалы о схемах злоумышленников в интернете",
        "списку литературы на лето":"Список литературы на лето","уставом":"Устав ГБОУ школы № 93 Пушкинского района Санкт-Петербурга"}
UNPLACE={"р. р","спорт","презентацией урока",""}
def cl(s): return re.sub(r'\s+',' ',JUNK.sub(' ',s or '')).strip(' -–—:;,.')
NAMES=re.compile(r'^(Всероссийск|Всемирн|ГТО|ВФСК|Пушкинск|Санкт|Петербург|Российск|Росси|Федерац|Министерств|Минпросвещ|Минобр|Правительств|Комитет|Администрац|Рособрнадзор|Кванториум|Интернет|Школьн|Первомайск|Параграф|Совет|Штаб|Макс|Сферум|Героя|Героев|Великой|Отечественной|ООО|НОО|СОО|ГИА|ВСОШ|ХАССП|Библиотечно|Бассейн|Логопункт|Отделение|Детский|Пришкольная|Стремительный|Битва|Я)')
def cut(s):
    s=re.sub(r'#\S+','',cl(s)).strip()
    m=STOP.search(s)
    if m and m.start()>8: s=s[:m.start()]
    # новая фраза с заглавной после строчного слова = начался следующий текст
    for m in re.finditer(r'(?<=[а-яёa-z0-9)»"])\s([А-ЯЁ][а-яё]*)(?=[\s,.]|$)',s):
        before=s[:m.start()]
        inside=(before.count('"')%2==1) or (before.count('«')>before.count('»')) or (before.count('“')>before.count('”'))
        if inside: continue
        if m.start()>=3 and not NAMES.match(m.group(1)):
            s=s[:m.start()]; break
    for m in re.finditer(r'(\S+)\.\s+[А-ЯЁ]',s):
        w=m.group(1).lower().strip('(«"')
        if w in ('ул','д','г','пр','им','стр','п','пос','ст','каб','т','корп','лит','н','а','с','о','м','в','и') or len(w)<=2: continue
        if m.start()>10: s=s[:m.start()+len(m.group(1))]; break
    return s[:420].strip(' -–—:;,.')
def quotes(s):
    """Кавычки-ёлочки, внутри ёлочек — лапки; лишний хвост после закрытой цитаты отрезаем."""
    out=[];depth=0;prev=' '
    for ch in s:
        if ch in '"“”„«»':
            opening = ch in '«„' or (ch in '"“' and prev in ' («„—-')
            if ch=='»' or ch=='”': opening=False
            if opening:
                out.append('«' if depth==0 else '„'); depth+=1
            else:
                if depth==0: continue
                depth-=1; out.append('»' if depth==0 else '“')
                if depth==0:
                    out.append('\x00')  # конец цитаты верхнего уровня
        else: out.append(ch)
        prev=ch if ch not in '\x00' else prev
    s=''.join(out)
    while depth>0:
        depth-=1; s+='»' if depth==0 else '“'
    if '\x00' in s:
        head,tail=s.split('\x00',1); tail=tail.replace('\x00','')
        # хвост после цитаты оставляем, только если это продолжение со строчной буквы или «от …/№ …»
        t=tail.strip()
        if t and (t[:1].islower() and not t.startswith(('совет ','общее ')) or t.startswith(('от ','№',')'))):
            s=head+tail
        else:
            s=head
    return s.replace('\x00','')
FIX={("dokumenty","режим занятий"):("Режим занятий обучающихся: годовой календарный учебный график на 2026–2027 учебный год",True),
     ("lokalnyye","режим занятий"):("Режим занятий обучающихся: годовой календарный учебный график на 2026–2027 учебный год",True),
     ("nastavnichestvo","дорожная карта"):("Дорожная карта реализации целевой модели наставничества",True),
     ("osnovy-religioznykh","(презентация)"):("Презентация курса ОРКСЭ",True),
     ("programma-razvitiya","легенда"):("Легенда к результатам самодиагностики (ноябрь 2025)",True),
     ("protivodeystvie","2022 год"):("Протоколы комиссии по противодействию коррупции, 2022 год",True),
     ("protivodeystvie","2023 год"):("Протоколы комиссии по противодействию коррупции, 2023 год",True),
     ("protivodeystvie","2024 год"):("Протоколы комиссии по противодействию коррупции, 2024 год",True),
     ("protivodeystvie","2025 год"):("Протоколы комиссии по противодействию коррупции, 2025 год",True),
     ("proforientatsiya","скачать файл"):("Скачать файл",False),
     ("page33194858","бассейн$"):("Платные услуги: бассейн",True),("platnye-obrazovatelnye","бассейн$"):("Платные услуги: бассейн",True),
     ("page33194858","спорт$"):("Платные услуги: спортивные секции",True),("platnye-obrazovatelnye","спорт$"):("Платные услуги: спортивные секции",True),
     ("dorozhnaya","раскраски"):("Раскраски по ПДД",True),("stranitsa-sovetnika","https"):("Сценарии мероприятий",False),
     ("novosti-shkoly",""):("",False),
     ("page33194858","положением об организации"):("Положение об организации (порядке оказания) дополнительных платных образовательных услуг",True),
     ("platnye-obrazovatelnye","положением об организации"):("Положение об организации (порядке оказания) дополнительных платных образовательных услуг",True),
     ("pedagogicheskiy-sostav","список классных"):("Список классных руководителей",True),
     ("priyom-v-1-klass","информацию о наличии"):("Информация о наличии свободных мест в образовательных организациях",True)}
out=[];stat=collections.Counter();PARTNERS=set()
for r in rows:
    lt=cl(r['link_text']); url=r['url'].strip(); low=lt.lower().rstrip('.:')
    if 'политикой конфиденциальности' in low or 'Форма обратной связи' in r['before'] or 'обработку персональных данных в соответствии' in r['context']:
        stat['выкинуто: форма']+=1; out.append(dict(page=r['page'],url=r['url'].strip(),old=lt,title='',how='выкинуто',place='0',grp='')); continue
    if low.startswith('меню ежедневного'):
        stat['выкинуто: меню']+=1; out.append(dict(page=r['page'],url=r['url'].strip(),old=lt,title='',how='выкинуто',place='0',grp='')); continue
    place=True; how='как есть'; title=lt
    man=[v for k,v in MANUAL.items() if low.startswith(k)]
    if lt.startswith('http') and 'infourok' in r['before']: man=[]; low=''  # сценарии с чужого сайта
    if not lt.strip(): low=''

    if man: title=man[0]; how='вручную'
    elif low in UNPLACE or low.startswith('презентацией'):
        place=False; how='не на сайте'
    elif low in POINTER or lt.startswith('http'):
        c=cut(r['after']) or cut(r['context']) or cut(re.sub(r'\s*Ссылка\s*$','',cl(r['before'])))
        if c and c.isupper(): c=c.capitalize()
        title=c or lt; how='указатель'
    elif low in GEN or len(lt)<16 or ' ' not in lt.strip() or lt[:1].islower():
        a=cut(r['after'])
        if a: title=f'{lt} {a}'; how='после'
        elif r['where']=='рядом' and cl(r['context']):
            c=cut(r['context']); title=c if c.lower().startswith(low) else f'{lt} {c}'; how='рядом'
        else: how='не найдено'
    elif how=='как есть' and len(lt)<90 and not lt.rstrip().endswith(('»','"',')')):
        a=cut(r['after'])
        quoted_ok = bool(re.search(r'(№\s*\S+|\d|-р|-адм|России|Комитета|образованию|Минпросвещения|Рособрнадзора|района|Петербурга|Правительства|РФ)$', lt.strip())) or low.split()[-1] in GEN
        GENIT=re.match(r'(РФ|№|Пушкинского|Российской|Комитета|Министерства|Правительства|Администрации|Санкт)',a or '')
        last=low.split()[-1] if low.split() else ''
        genit_ok = bool(GENIT) and last in ('закон','администрации','комитета','министерства','правительства','распоряжение','приказ','постановление','письмо','указ')
        if a and (a[:1].islower() or a[:1]=='(' or (a[:1] in '"«“' and quoted_ok) or genit_ok):
            if a[:1].islower():
                m=re.search(r'\s[«"“]',a)
                if m and m.start()>40: a=a[:m.start()]
            title=f'{lt} {a}'; how='продолжение'
    if how in ('как есть',) and low and lt.startswith('Протоколы'): pass
    title=quotes(re.sub(r'\s+',' ',title)).strip(' -–—:;,.')
    title=re.sub(r'«([а-яё])',lambda m:'«'+m.group(1).upper(),title)
    title=title.replace('Кванрториум','Кванториум').replace('утвержении','утверждении').replace('соченения','сочинения').replace('Петерурга','Петербурга')
    title=title[:1].upper()+title[1:]
    for k,v in MANUAL.items():
        if title.lower().startswith(k): title=v
    if len(title)>400: title=title[:397].rsplit(' ',1)[0]+'…'+('»' if title.count('«')>title[:397].count('»') else '')
    stat[how]+=1
    for (pg,st),(v,pl) in FIX.items():
        if pg in r['page'] and ((st.endswith('$') and lt.lower()==st[:-1]) or (not st.endswith('$') and lt.lower().startswith(st))):
            title=v; place=pl; how='вручную'
    grp=re.sub(r'\s+',' ',JUNK.sub(' ',r['block_title'] or '')).strip(' -–—:;,.>')
    if 'Наши партнёры' in r['before'] or 'Наши партнеры' in r['before']: PARTNERS.add(r['page'])
    if r['page'] in PARTNERS and not r['after'].strip(): grp='Партнёры психолого-педагогических классов'

    if len(grp)>140 or len(grp)<4 or grp.lower() in ('р','документы'): grp=''
    out.append(dict(page=r['page'],url=url,old=lt,title=title,how=how,place='1' if place else '0',grp=grp))
print(stat)
with open('doc_titles.csv','w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=['page','url','old','title','how','place','grp'],delimiter=';'); w.writeheader(); w.writerows(out)
