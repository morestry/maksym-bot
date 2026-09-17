import os
import json
import re
import openai
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from datetime import datetime

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
GOOGLE_CREDENTIALS = os.environ.get("GOOGLE_CREDENTIALS")

# ============ GOOGLE SHEETS ============

def get_spreadsheet():
    try:
        creds_dict = json.loads(GOOGLE_CREDENTIALS)
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_key(GOOGLE_SHEET_ID)
    except:
        return None

def get_sheet():
    try:
        return get_spreadsheet().sheet1
    except:
        return None

def get_users_sheet():
    try:
        spreadsheet = get_spreadsheet()
        if not spreadsheet:
            return None
        try:
            return spreadsheet.worksheet("Користувачі")
        except:
            sheet = spreadsheet.add_worksheet(title="Користувачі", rows=1000, cols=12)
            sheet.append_row([
                "ID", "Username", "Ім'я (TG)", "Ім'я (назвав сам)",
                "Стать", "Вік", "Місто", "Мова", "Перший візит",
                "Останній візит", "Всього сесій", "Повідомлень Максиму"
            ])
            return sheet
    except:
        return None

def log_event(event_type, user_id, username="", first_name="", language="", hour="", extra="", user_name_given="", gender="", age="", location=""):
    try:
        sheet = get_sheet()
        if sheet:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            is_anon = "Анонім" if not username else "Є username"
            weekday_ua = get_weekday_ua()
            time_of_day = get_time_of_day()
            row = [
                now, event_type, str(user_id), username, first_name,
                language, hour, is_anon, weekday_ua, time_of_day, extra,
                user_name_given, gender, age, location
            ]
            sheet.append_row(row, value_input_option="RAW")
    except:
        pass

def update_user_record(user_id, username, first_name, language, udata, is_start=False):
    try:
        sheet = get_users_sheet()
        if not sheet:
            return
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        all_records = sheet.get_all_values()
        user_row = None
        for i, row in enumerate(all_records):
            if row and str(row[0]) == str(user_id):
                user_row = i + 1
                break

        def safe_int(val):
            try:
                return int(str(val).strip())
            except:
                return 0

        def best(new_val, old_val):
            return new_val if new_val else old_val

        if user_row:
            existing = all_records[user_row - 1]
            while len(existing) < 12:
                existing.append("")
            sessions = safe_int(existing[10])
            messages = safe_int(existing[11])
            if is_start:
                sessions += 1
            else:
                messages += 1
            sheet.update(f"B{user_row}:L{user_row}", [[
                username, first_name,
                best(udata.get("name", ""), existing[3]),
                best(udata.get("gender", ""), existing[4]),
                best(udata.get("age", ""), existing[5]),
                best(udata.get("location", ""), existing[6]),
                language,
                existing[8] if existing[8] else now,
                now, sessions, messages,
            ]], value_input_option="RAW")
        else:
            sheet.append_row([
                str(user_id), username, first_name,
                udata.get("name", ""), udata.get("gender", ""),
                udata.get("age", ""), udata.get("location", ""),
                language, now, now,
                1 if is_start else 0,
                0 if is_start else 1,
            ], value_input_option="RAW")
    except:
        pass

# ============ ДОПОМІЖНІ ФУНКЦІЇ ============

def get_time_of_day():
    h = int(datetime.now().strftime("%H"))
    if 6 <= h < 12:
        return "Ранок"
    elif 12 <= h < 18:
        return "День"
    elif 18 <= h < 23:
        return "Вечір"
    else:
        return "Ніч"

def get_weekday_ua():
    weekday = datetime.now().strftime("%A")
    return {
        "Monday": "Понеділок", "Tuesday": "Вівторок",
        "Wednesday": "Середа", "Thursday": "Четвер",
        "Friday": "П'ятниця", "Saturday": "Субота", "Sunday": "Неділя"
    }.get(weekday, weekday)

def clean_markdown(text):
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)
    text = re.sub(r'_(.*?)_', r'\1', text)
    text = re.sub(r'`(.*?)`', r'\1', text)
    text = re.sub(r'#{1,6}\s', '', text)
    return text

def extract_user_info(text, user_data):
    text_lower = text.lower().strip()

    BAD_NAMES = [
        "бьет", "бить", "каже", "пише", "робить", "живе", "хоче",
        "знає", "думає", "каже", "говорит", "бьёт", "ударил", "сказал",
        "нормально", "добре", "погано", "просто", "дуже", "мене",
    ]

    name_patterns = [
        r'мене звати\s+(\w+)',
        r'мене зовуть\s+(\w+)',
        r'меня зовут\s+(\w+)',
        r'меня зовут\s+(\w+)',
        r'я\s+(\w+)$',
        r'^(\w+)$',
    ]
    if not user_data.get("name"):
        for pattern in name_patterns:
            match = re.search(pattern, text_lower)
            if match:
                name = match.group(1).capitalize()
                if len(name) > 1 and name.lower() not in BAD_NAMES:
                    user_data["name"] = name
                    break

    age_match = re.search(r'\b(\d{1,2})\s*(рік|років|года|лет|год|роки)\b', text_lower)
    if age_match and not user_data.get("age"):
        age = int(age_match.group(1))
        if 10 <= age <= 99:
            user_data["age"] = str(age)

    simple_age = re.search(r'^\s*(\d{1,2})\s*$', text.strip())
    if simple_age and not user_data.get("age"):
        age = int(simple_age.group(1))
        if 10 <= age <= 99:
            user_data["age"] = str(age)

    female_indicators = ["я жінка", "я дівчина", "я мама", "я дружина", "я донька", "я сестра"]
    male_indicators = ["я чоловік", "я хлопець", "я тато", "я муж", "я брат", "я син"]

    if not user_data.get("gender"):
        if any(w in text_lower for w in female_indicators):
            user_data["gender"] = "Жінка"
        elif any(w in text_lower for w in male_indicators):
            user_data["gender"] = "Чоловік"
        elif user_data.get("name"):
            name = user_data["name"].lower()
            female_names = [
                "mary", "maria", "марія", "оля", "ольга", "катя", "катерина",
                "аня", "анна", "таня", "тетяна", "наташа", "наталія", "лена",
                "олена", "юля", "юлія", "іра", "ірина", "света", "світлана",
                "люда", "людмила", "надя", "надія", "соня", "софія", "ліза",
                "єлизавета", "віка", "вікторія", "даша", "дарина", "настя",
                "анастасія", "маша", "марина", "галя", "галина", "лара", "лариса",
                "жанна", "діана", "аліна", "інна", "вера", "лілія", "христина",
            ]
            if name in female_names:
                user_data["gender"] = "Жінка"

    BAD_LOCATIONS = [
        "нашим", "мною", "тобою", "ним", "нею", "нами",
        "мене", "тебе", "його", "неї",
    ]
    location_patterns = [
        r'живу в\s+(\w+)',
        r'я з\s+(\w+)',
        r'нахожусь в\s+(\w+)',
        r'знаходжусь в\s+(\w+)',
        r'перебуваю в\s+(\w+)',
        r'я зараз в\s+(\w+)',
    ]
    if not user_data.get("location"):
        for pattern in location_patterns:
            match = re.search(pattern, text_lower)
            if match:
                loc = match.group(1).capitalize()
                if loc.lower() not in BAD_LOCATIONS and len(loc) > 2:
                    user_data["location"] = loc
                break
        if "за кордоном" in text_lower or "заграницей" in text_lower:
            user_data["location"] = "За кордоном"
        elif "в україні" in text_lower or "в украине" in text_lower:
            user_data["location"] = "Україна"

    return user_data

# ============ ТЕКСТИ КНОПОК ============

MESSAGES = {
    "anxiety": (
        "Відчувати тривогу зараз — це нормальна реакція тіла на ненормальні обставини. Коли накриває хвиля паніки, наше тіло готується тікати або битися, навіть якщо прямої загрози поруч немає.\n\n"
        "Практика заземлення «5-4-3-2-1»:\n\n"
        "👁 5 предметів, які ти бачиш\n"
        "✋ 4 речі, які ти можеш відчути на дотик\n"
        "👂 3 звуки, які ти чуєш прямо зараз\n"
        "👃 2 запахи, які ти відчуваєш\n"
        "👅 1 смак — зроби ковток води\n\n"
        "Зроби повільний глибокий вдих і видих.\n\n"
        "Це лише перший крок. Якщо хочеш виговоритися — Максим поруч і готовий вислухати."
    ),
    "stress": (
        "Стрес виснажує не лише думки, а й накопичується в тілі. Коли нервова система перевантажена, важливо дати їй сигнал: «Зараз я в безпеці, можна розслабитися».\n\n"
        "Вправа: Прогресивна м'язова релаксація\n\n"
        "1. Сядь або ляж у зручну позу\n"
        "2. Міцно стисни кулаки та напруж руки на 5 секунд\n"
        "3. Різко розслаб руки та зроби глибокий видих\n"
        "4. Повтори те саме з плечима, обличчям та ногами\n"
        "5. Зроби ковток чистої води\n\n"
        "Щоб розвантажити голову від зайвих думок — продовжи діалог із Максимом."
    ),
    "sleep": (
        "Складність із засинанням — сигнал що мозок не може вимкнути «режим контролю».\n\n"
        "Техніка дихання «4-7-8»:\n\n"
        "1. Видихни все повітря\n"
        "2. Вдих носом — 4 секунди\n"
        "3. Затримай дихання — 7 секунд\n"
        "4. Видих ротом — 8 секунд\n"
        "5. Повтори 4–5 разів\n\n"
        "Відклади телефон екраном донизу. Якщо думки не дають спати — Максим на зв'язку цілодобово."
    ),
    "apathy": (
        "Апатія — це захисна реакція психіки. Не карай себе за те, що зараз «нічого не хочеться».\n\n"
        "Стратегія «Маленького кроку»:\n\n"
        "— Обирай дію не більше 2 хвилин\n"
        "— Зроби ковток води або відчини вікно\n"
        "— Дозволь собі робити речі на 10% із 100%\n\n"
        "Потрібна підтримка без оцінок? Поспілкуйся з Максимом."
    ),
    "loneliness": (
        "Ти не один/одна, навіть якщо зараз здається навпаки.\n\n"
        "Практика співчуття до себе:\n\n"
        "1. Поклади долоню на груди або обійми себе за плечі\n"
        "2. Скажи собі: «Мені зараз важко. Але я роблю все що в моїх силах»\n"
        "3. Ти заслуговуєш на тепло так само як і будь-хто інший\n\n"
        "Якщо хочеш розділити переживання — напиши Максиму. Він завжди поруч."
    ),
    "anger": (
        "Гнів — це сильна та здорова емоція. Важливо дати йому безпечний вихід.\n\n"
        "Швидкі техніки:\n\n"
        "📄 Зімни аркуш паперу з усієї сили або порви його\n"
        "⏸ Правило 10 секунд: глибоко видихни перед відповіддю\n"
        "🚶 Рух: кілька кроків, потягнися, поворуши плечима\n\n"
        "Хочеш розібратися що викликало реакцію? Максим вислухає без оцінок."
    ),
    "lost": (
        "Коли земля тікає з-під ніг — спирайся на теперішній момент.\n\n"
        "Вправа «Коло контролю»:\n\n"
        "❌ Не контролюєш: глобальні події, рішення інших, майбутнє\n"
        "✅ Контролюєш: що з'їси, коли ляжеш спати, з ким поговориш\n\n"
        "Сфокусуйся на одній маленькій дії впродовж 15 хвилин.\n\n"
        "Якщо потрібно структурувати хаос у голові — почни діалог із Максимом."
    ),
}

BUTTON_NAMES = {
    "anxiety": "Тривога та паніка",
    "stress": "Стрес та перенапруження",
    "sleep": "Проблеми зі сном",
    "apathy": "Апатія та виснаження",
    "loneliness": "Самотність або провина",
    "anger": "Дратівливість та гнів",
    "lost": "Втрата опори",
}

# ============ КРИЗОВІ СЛОВА ============

CRISIS_KEYWORDS = [
    "суїцид", "самогубство", "вбити себе", "убить себя",
    "не хочу жити", "не хочу жить", "хочу умереть", "хочу померти",
    "покончить с жизнью", "покінчити з життям", "покінчити життя",
    "кончаю з собою", "нет смысла жить", "немає сенсу жити",
    "всем будет лучше без меня", "всім буде краще без мене",
    "краще б мене не було", "лучше бы меня не було",
    "я всім тягар", "я всем обуза",
    "хочу щоб це закінчилось назавжди",
]

VIOLENCE_KEYWORDS = [
    "він мене б'є", "она меня бьет", "він мене вдарив", "он меня ударил",
    "домашнє насильство", "домашнее насилие",
    "изнасилование", "зґвалтування",
]

SELF_HARM_KEYWORDS = [
    "зроблю собі боляче", "порізати себе", "порезать себя",
    "вдарити себе", "ударить себя",
    "шрами на руках", "шрамы на руках",
]

# ============ СТАН ============

user_sessions = {}
crisis_users = set()
user_last_button = {}
user_session_start = {}
user_message_count = {}
user_data_store = {}
user_data_prev = {}

# ============ ПРОМПТИ ============

SYSTEM_PROMPT_NORMAL = """Ти — Максим, підтримувальний ШІ-компаньйон у підході ACT.

ГОЛОВНЕ: Ти КОРИСНИЙ. Ти ЗАВЖДИ даєш конкретну допомогу. Ніколи не відмовляєш у техніці. Ніколи не повторюєш одне й те саме.

ФОРМАТ:
- Простий текст БЕЗ зірочок, БЕЗ жирного, БЕЗ нумерованих списків
- 80-200 слів
- Тепло, по-людськи
- Дзеркаль мову людини (українська або російська)

ЗАБОРОНЕНО:
- "я не можу поділитися техніками"
- Будь-які відмови допомогти
- Питати "хочеш техніку?" — давай одразу якщо людина описує стан
- Повторювати одне й те саме питання двічі
- Згадувати гарячі лінії при звичайних зверненнях (безсоння, тривога, стрес, апатія)

ГАРЯЧІ ЛІНІЇ — ТІЛЬКИ КОЛИ:
- Людина сама просить гарячу лінію або психолога
- Спрацювали кризові слова (суїцид, насильство, самоушкодження)
У всіх інших випадках — НЕ згадуй гарячі лінії взагалі.

ДАВАЙ ТЕХНІКУ ОДРАЗУ (без питання "хочеш?"):
Якщо людина описує стан — це вже запит на допомогу.

"не можу уснуть", "думки не дають спати", "безсоння" →
"Вдих 4 секунди, затримай 7, видих 8. Повтори 4 рази. Відклади телефон."

"накрило", "паніка", "трясе", "не можу дихати" →
"Стопи на підлозі. Повільний видих. Назви 3 речі що бачиш."

"думки крутяться", "не можу зупинити думки", "прокручую одне" →
"Скажи собі: Я помічаю думку що... Це просто думка, не факт. Уяви що вона пливе як хмара."

"злюся", "гнів", "роздратування" →
"Пауза. Глибокий видих. Зімни аркуш паперу — дай тілу вихід."

"порожнеча", "нічого не відчуваю", "апатія" →
"Де в тілі ти це відчуваєш? Яке воно? Просто помітити — вже крок."

"навіщо це все", "немає сенсу" →
"Якби ця важкість зникла — що важливе ти б робила?"

"болить голова", "стиснуто в грудях", "ком у горлі" →
"Поклади руку туди де відчуваєш. Зроби повільний видих прямо в це місце."

"просто хочу виговоритися", "нема кому розказати" →
НЕ давай вправу. Слухай: коротке віддзеркалення + одне питання.

ЯКЩО ЛЮДИНА ПРОСИТЬ ГАРЯЧУ ЛІНІЮ АБО ПСИХОЛОГА:
📞 7333 — Lifeline Ukraine (цілодобово, безкоштовно)
📞 116 123 — Національна гаряча лінія
📞 1545 — Урядова лінія підтримки

РОЗУМІЙ НЕЧІТКІ ЗАПИТИ:
- "какие техники", "що робити", "помоги" → дай вправу одразу
- "устала", "все", "не можу" → спитай: "що зараз найважче?"
- Одне слово ("страх", "тривога", "погано") → дай техніку або спитай одне
- Ніколи не проси переформулювати
- Люди пишуть з помилками — розумій намір

ІМ'Я ТА РІД:
- Використовуй ТІЛЬКИ ім'я з контексту або що людина сама написала
- НЕ вигадуй і НЕ скорочуй — Mary це Mary, не Маша
- НЕ питай ім'я якщо воно вже є в контексті
- Жіночі (Mary, Марія, Оля, Катя, Аня, Ліза, Віка, Даша, Настя та ін.) → зробила, відчула
- Чоловічі → зробив, відчув
- Не зрозуміло → "Як правильно — ти зробив чи зробила?"
- Не питай ім'я в гострий момент

ГОРЕ І ВТРАТА:
"хтось помер", "він загинув", "вона померла" →
НЕ давай вправ. Тільки присутність:
"Мені дуже шкода. Це величезна втрата. Не потрібно нікуди поспішати з цим болем."
НІКОЛИ: "час лікує", "він в кращому місці", "треба триматись"

ПІДТРИМКА ТИХ ХТО ДОГЛЯДАЄ:
"чоловік на фронті", "дитина хворіє", "доглядаю за мамою", "все на мені" →
"Коли несеш стільки — хто зараз піклується про тебе?"

ПЕРЕВІРКА ПІСЛЯ ВПРАВИ:
"Спробувала? Що помітила?"
Якщо "не допомогло" → "Це нормально — перший раз просто знайомство. Хочеш спробуємо іншу?"

НАГАДУВАННЯ ПРО СЕБЕ:
Коли зробила щось важке → "Те що ти тут — це вже крок."
Коли себе критикує → "Слабкі люди не шукають допомоги."

ЗАВЕРШЕННЯ:
"дякую", "допомогло", "стало краще" → "Радий що трохи легше. Повертайся коли потрібно. 💙"
"поки", "до побачення" → "Бережи себе. 💙"
"все", "ладно" → "Як ти зараз? Є що ще на серці?"

ДО ПСИХОЛОГА — тільки коли людина сама питає або ситуація серйозна.
НЕ вставляй в кожну відповідь."""

SYSTEM_PROMPT_CRISIS = """Ти — Максим, теплий та надзвичайно емпатичний психологічний помічник.

Користувач перебуває у гострому кризовому стані.

ФОРМАТ: Простий текст БЕЗ зірочок і Markdown.

ВАЖЛИВО:
- Не проводь вправ якщо людина не просить
- Якщо просить техніку — дай одну просту (дихання або 5-4-3-2-1)
- Не заспокоюй формулами ("все буде добре")
- М'яко заохочуй зателефонувати: 7333, 116 123, 1545
- Пиши коротко і дуже дбайливо
- Дзеркаль мову (українська або російська)
- Не питай про спосіб чи план
- Не повторюй одне й те саме двічі"""

# ============ КЛАВІАТУРА ============

def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("😰 Тривога та паніка", callback_data="anxiety")],
        [InlineKeyboardButton("😤 Стрес та перенапруження", callback_data="stress")],
        [InlineKeyboardButton("😴 Проблеми зі сном", callback_data="sleep")],
        [InlineKeyboardButton("😶 Апатія та виснаження", callback_data="apathy")],
        [InlineKeyboardButton("😔 Самотність або провина", callback_data="loneliness")],
        [InlineKeyboardButton("😠 Дратівливість та гнів", callback_data="anger")],
        [InlineKeyboardButton("😵 Втрата опори", callback_data="lost")],
    ]
    return InlineKeyboardMarkup(keyboard)

# ============ ХЕНДЛЕРИ ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    hour = datetime.now().strftime("%H:00")
    if user.id not in user_data_store:
        user_data_store[user.id] = {}
    log_event("START", user.id, user.username or "", user.first_name or "", user.language_code or "", hour)
    update_user_record(user.id, user.username or "", user.first_name or "", user.language_code or "", user_data_store[user.id], is_start=True)
    await update.message.reply_text(
        "Привіт 👋\n\nЯ тут, щоб підтримати тебе. Як ти зараз почуваєшся?",
        reply_markup=get_main_keyboard()
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    hour = datetime.now().strftime("%H:00")

    if query.data == "menu":
        await query.message.reply_text(
            "Як ти зараз почуваєшся?",
            reply_markup=get_main_keyboard()
        )
        return

    if query.data == "maksym":
        if user.id not in user_sessions:
            user_sessions[user.id] = []
        user_session_start[user.id] = datetime.now()
        user_message_count[user.id] = 0
        last_button = user_last_button.get(user.id, "—")
        udata = user_data_store.get(user.id, {})
        log_event("MAKSYM_START", user.id, user.username or "", user.first_name or "",
                  user.language_code or "", hour, extra=f"Прийшов з: {last_button}",
                  user_name_given=udata.get("name", ""), gender=udata.get("gender", ""),
                  age=udata.get("age", ""), location=udata.get("location", ""))
        keyboard = [[InlineKeyboardButton("🏠 Повернутися до меню", callback_data="menu")]]
        await query.message.reply_text(
            "Привіт, я Максим 👋\n\nРозкажи мені що тебе турбує. Я тут, щоб вислухати.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    button_name = BUTTON_NAMES.get(query.data, query.data)
    user_last_button[user.id] = button_name
    udata = user_data_store.get(user.id, {})
    log_event(f"BUTTON: {button_name}", user.id, user.username or "", user.first_name or "",
              user.language_code or "", hour,
              user_name_given=udata.get("name", ""), gender=udata.get("gender", ""),
              age=udata.get("age", ""), location=udata.get("location", ""))

    text = MESSAGES.get(query.data, "")
    keyboard = [
        [InlineKeyboardButton("🤖 Почати розмову з Максимом", callback_data="maksym")],
        [InlineKeyboardButton("🏠 Повернутися до меню", callback_data="menu")],
    ]
    await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    hour = datetime.now().strftime("%H:00")
    text_lower = update.message.text.lower()

    if user.id not in user_data_store:
        user_data_store[user.id] = {}

    prev_data = dict(user_data_store[user.id])
    user_data_store[user.id] = extract_user_info(update.message.text, user_data_store[user.id])
    udata = user_data_store[user.id]

    # Оновлюємо лист користувачів тільки якщо є нові дані
    if udata != prev_data:
        update_user_record(user.id, user.username or "", user.first_name or "", user.language_code or "", udata)

    if any(word in text_lower for word in VIOLENCE_KEYWORDS):
        crisis_users.add(user.id)
        if user.id not in user_sessions:
            user_sessions[user.id] = []
        log_event("VIOLENCE", user.id, user.username or "", user.first_name or "",
                  user.language_code or "", hour,
                  user_name_given=udata.get("name", ""), gender=udata.get("gender", ""),
                  age=udata.get("age", ""), location=udata.get("location", ""))
        await update.message.reply_text(
            "Те, що ти зараз кажеш — серйозно, і добре, що ти це сказала.\n\n"
            "Ти не мусиш бути з цим наодинці:\n\n"
            "📞 116 123 — Національна лінія (насильство, цілодобово, безкоштовно)\n"
            "📞 1547 — Урядова лінія підтримки\n"
            "📞 102 — Поліція (якщо є безпосередня загроза)\n\n"
            "Якщо ти зараз у небезпеці — зателефонуй або вийди в безпечне місце. 💙"
        )
        return

    if any(word in text_lower for word in SELF_HARM_KEYWORDS):
        crisis_users.add(user.id)
        if user.id not in user_sessions:
            user_sessions[user.id] = []
        log_event("SELF_HARM", user.id, user.username or "", user.first_name or "",
                  user.language_code or "", hour,
                  user_name_given=udata.get("name", ""), gender=udata.get("gender", ""),
                  age=udata.get("age", ""), location=udata.get("location", ""))
        await update.message.reply_text(
            "Я чую, що тобі зараз дуже боляче. Дякую, що сказала про це.\n\n"
            "Будь ласка, не залишайся з цим сам на сам:\n\n"
            "📞 7333 — Lifeline Ukraine (цілодобово, безкоштовно)\n"
            "📞 116 123 — Національна гаряча лінія\n\n"
            "Розкажи мені що зараз відбувається? Я тут. 💙"
        )
        return

    if any(word in text_lower for word in CRISIS_KEYWORDS):
        crisis_users.add(user.id)
        if user.id not in user_sessions:
            user_sessions[user.id] = []
        log_event("CRISIS", user.id, user.username or "", user.first_name or "",
                  user.language_code or "", hour,
                  user_name_given=udata.get("name", ""), gender=udata.get("gender", ""),
                  age=udata.get("age", ""), location=udata.get("location", ""))
        await update.message.reply_text(
            "Я бачу, що тобі зараз неймовірно важко. Дякую, що не залишилася з цим наодинці.\n\n"
            "Будь ласка, зателефонуй — тебе вислухають:\n\n"
            "📞 7333 — Lifeline Ukraine (цілодобово, безкоштовно)\n"
            "📞 116 123 — Національна гаряча лінія\n"
            "📞 1545 — Урядова гаряча лінія\n"
            "📞 112 — Екстрена допомога\n\n"
            "Ти важлива. Розкажи мені що зараз відбувається? Я тут. 💙"
        )
        return

    if user.id not in user_sessions and user.id not in crisis_users:
        await update.message.reply_text(
            "Як ти зараз почуваєшся?",
            reply_markup=get_main_keyboard()
        )
        return

    if user.id not in user_sessions:
        user_sessions[user.id] = []

    if user.id in crisis_users:
        count = user_message_count.get(user.id, 0)
        if count >= 3 and not any(word in text_lower for word in CRISIS_KEYWORDS + SELF_HARM_KEYWORDS + VIOLENCE_KEYWORDS):
            crisis_users.discard(user.id)

    history = user_sessions.get(user.id, [])
    history.append({"role": "user", "content": update.message.text})
    if len(history) > 20:
        history = history[-20:]

    user_message_count[user.id] = user_message_count.get(user.id, 0) + 1
    count = user_message_count.get(user.id, 0)
    start_time = user_session_start.get(user.id)
    duration = int((datetime.now() - start_time).total_seconds() / 60) if start_time else 0
    extra = f"Повідомлень: {count}, Тривалість: {duration} хв"

    system_prompt = SYSTEM_PROMPT_CRISIS if user.id in crisis_users else SYSTEM_PROMPT_NORMAL

    user_context = ""
    if udata.get("name"):
        user_context += f"Ім'я: {udata['name']}. "
    if udata.get("gender"):
        user_context += f"Стать: {udata['gender']}. "
    if udata.get("age"):
        user_context += f"Вік: {udata['age']} років. "
    if udata.get("location"):
        user_context += f"Місто/країна: {udata['location']}. "
    if user_context:
        system_prompt = system_prompt + f"\n\nКОНТЕКСТ: {user_context}"

    extra_question = ""
    if count == 3 and not udata.get("name") and user.id not in crisis_users:
        extra_question = "\n\nДо речі, як тебе звати?"
    elif count == 5 and not udata.get("age") and user.id not in crisis_users:
        extra_question = "\n\nСкільки тобі років? Щоб краще розуміти твою ситуацію."
    elif count == 7 and not udata.get("location") and user.id not in crisis_users:
        extra_question = "\n\nТи зараз в Україні чи за кордоном?"

    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                *history
            ],
            max_tokens=500
        )
        reply = response.choices[0].message.content
        reply = clean_markdown(reply)

        if extra_question:
            reply = reply + extra_question

        history.append({"role": "assistant", "content": reply})
        user_sessions[user.id] = history

        log_event("MAKSYM_MESSAGE", user.id, user.username or "", user.first_name or "",
                  user.language_code or "", hour, extra=extra,
                  user_name_given=udata.get("name", ""), gender=udata.get("gender", ""),
                  age=udata.get("age", ""), location=udata.get("location", ""))

        keyboard = [[InlineKeyboardButton("🏠 Повернутися до меню", callback_data="menu")]]
        await update.message.reply_text(reply, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        await update.message.reply_text("Вибач, сталася помилка. Спробуй ще раз.")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
