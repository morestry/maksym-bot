# ============================================
# MAKSYM BOT
# Версія: 2.8
# Дата: 2026-09-19
# Зміни: прибрано кешування get_sheet,
#        кожен раз нове з'єднання з Sheets
# ============================================

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

VERSION = "2.8 | 2026-09-19"

# ============ GOOGLE SHEETS ============

def get_sheet():
    try:
        creds_dict = json.loads(GOOGLE_CREDENTIALS)
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_key(GOOGLE_SHEET_ID).sheet1
    except Exception as e:
        print(f"GET_SHEET ERROR: {e}")
        return None

def log_event(event_type, user_id, username="", first_name="", language="",
              hour="", last_button="", msg_count="", duration=""):
    try:
        sheet = get_sheet()
        if not sheet:
            print(f"LOG SKIP: no sheet for {event_type}")
            return
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        is_anon = "Анонім" if not username else "Є username"
        row = [
            now,
            event_type,
            str(user_id),
            str(username),
            str(first_name),
            str(language),
            str(hour),
            is_anon,
            get_weekday_ua(),
            get_time_of_day(),
            str(last_button),
            str(msg_count),
            str(duration),
        ]
        sheet.append_row(row, value_input_option="RAW")
        print(f"LOG OK: {event_type} {user_id}")
    except Exception as e:
        print(f"LOG_EVENT ERROR: {e}")

# ============ ДОПОМІЖНІ ============

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
    name_patterns = [
        r'мене звати\s+(\w+)',
        r'мене зовуть\s+(\w+)',
        r'меня зовут\s+(\w+)',
        r'я\s+(\w+)$',
        r'я\s+(\w+),',
    ]
    if not user_data.get("name"):
        for pattern in name_patterns:
            match = re.search(pattern, text_lower)
            if match:
                name = match.group(1).capitalize()
                if len(name) > 1:
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
                "ксенія", "ксения", "карина", "іринa", "ирина",
            ]
            if name in female_names:
                user_data["gender"] = "Жінка"
    return user_data

# ============ КРИЗОВИЙ МОДУЛЬ ============

SUICIDE_PATTERNS = [
    r"не\s*хоч\w*\s*(більше\s*|вже\s*|далі\s*)?жи\w*",
    r"жи\w*\s*не\s*хоч\w*",
    r"хоч\w*\s*(по)?мерт\w*",
    r"хоч\w*\s*зник\w*",
    r"суїцид\w*|суицид\w*|самогубств\w*|самоубийств\w*",
    r"(по)?кінч\w*\s*(із|з|с)\s*(соб|жит)\w*",
    r"вбит\w*\s*себе|убит\w*\s*себя",
    r"нема\w*\s*сенс\w*\s*жи\w*|нет\s*смысла\s*жи\w*",
    r"(всім|всем)\s*.{0,15}(краще|лучше)\s*без\s*мен\w*",
    r"(краще|лучше)\s*(б|бы)\s*мен\w*\s*не\s*бул\w*",
    r"я\s*(всім|всем)\s*(тягар|обуза)",
    r"хоч\w*\s*щоб\s*(це|всё|все)\s*.{0,15}(закінч|кончил)\w*\s*назавжди",
]

SELF_HARM_PATTERNS = [
    r"(зроб|сдел)\w*\s*соб[іе]\s*боля\w*",
    r"(по)?р[іи]з\w*\s*себе|(по)?рез\w*\s*себя",
    r"(вдар|удар)\w*\s*себе",
    r"шрам\w*\s*на\s*рук\w*",
    r"self.?harm|селфхарм",
]

VIOLENCE_PATTERNS = [
    r"(він|он|чоловік|муж|батько|партнер)\s*.{0,20}(б'є|бье|бив|бил|вдар|удар)\w*",
    r"мене\s*(б'ют|бьют|б'є|бье|побил|побив)\w*",
    r"меня\s*(бьют|бьет|избил|ударил)\w*",
    r"домашн\w*\s*насильств\w*|домашн\w*\s*насили\w*",
    r"(з|)ґвалт\w*|изнасилов\w*",
]

_SUICIDE_RE = [re.compile(p, re.IGNORECASE) for p in SUICIDE_PATTERNS]
_SELF_HARM_RE = [re.compile(p, re.IGNORECASE) for p in SELF_HARM_PATTERNS]
_VIOLENCE_RE = [re.compile(p, re.IGNORECASE) for p in VIOLENCE_PATTERNS]

CLASSIFIER_PROMPT = """Ти — класифікатор безпеки. Визнач чи містить повідомлення маркери кризового стану.
Категорії: suicide, self_harm, violence, none.
Класифікуй НАМІР. Безглузді слова — none. Впевненість нижче 0.7 — none.
JSON: {"category": "...", "confidence": 0.0-1.0}"""

def _regex_check(text):
    t = text.lower()
    if any(r.search(t) for r in _SUICIDE_RE):
        return "suicide"
    if any(r.search(t) for r in _SELF_HARM_RE):
        return "self_harm"
    if any(r.search(t) for r in _VIOLENCE_RE):
        return "violence"
    return None

def _llm_check(text):
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": CLASSIFIER_PROMPT},
                {"role": "user", "content": text[:500]},
            ],
            max_tokens=40,
            temperature=0,
            response_format={"type": "json_object"},
        )
        data = json.loads(r.choices[0].message.content)
        cat = data.get("category")
        conf = float(data.get("confidence", 0))
        if cat in ("suicide", "self_harm", "violence") and conf >= 0.7:
            return cat
        return None
    except:
        return None

def detect_crisis(text):
    if len(text.strip()) < 3:
        return None
    hit = _regex_check(text)
    if hit:
        return hit
    return _llm_check(text)

CRISIS_REPLIES = {
    "suicide": (
        "Я бачу, що тобі зараз неймовірно важко. Дякую, що написав(ла) про це.\n\n"
        "Будь ласка, зателефонуй — тебе вислухають:\n\n"
        "📞 7333 — Lifeline Ukraine (цілодобово, безкоштовно)\n"
        "📞 116 123 — Національна гаряча лінія\n"
        "📞 1545 — Урядова гаряча лінія\n"
        "📞 112 — Екстрена допомога\n\n"
        "Ти важлива людина. Розкажи мені що зараз відбувається? Я тут. 💙"
    ),
    "self_harm": (
        "Я чую, що тобі зараз дуже боляче. Дякую, що сказав(ла) про це.\n\n"
        "Будь ласка, не залишайся з цим наодинці:\n\n"
        "📞 7333 — Lifeline Ukraine (цілодобово, безкоштовно)\n"
        "📞 116 123 — Національна гаряча лінія\n\n"
        "Розкажи мені що зараз відбувається? Я тут. 💙"
    ),
    "violence": (
        "Те, про що ти зараз пишеш — серйозно. І добре, що ти це сказав(ла).\n\n"
        "Ти не мусиш бути з цим наодинці:\n\n"
        "📞 116 123 — Національна лінія (насильство, цілодобово, безкоштовно)\n"
        "📞 1547 — Урядова лінія підтримки\n"
        "📞 102 — Поліція (якщо є безпосередня загроза)\n\n"
        "Якщо ти зараз у небезпеці — зателефонуй або вийди в безпечне місце. 💙"
    ),
}

class CrisisState:
    def __init__(self):
        self.active = False
        self.entered_at = None
        self.messages_since = 0
        self.stable_streak = 0
        self.category = None

    def enter(self, category):
        self.active = True
        self.category = category
        self.entered_at = datetime.now()
        self.messages_since = 0
        self.stable_streak = 0

    def register_message(self, had_marker):
        if not self.active:
            return
        self.messages_since += 1
        if had_marker:
            self.stable_streak = 0
            self.entered_at = datetime.now()
        else:
            self.stable_streak += 1

    def can_exit(self):
        if not self.active:
            return False
        if self.messages_since < 8:
            return False
        if self.stable_streak < 4:
            return False
        minutes = (datetime.now() - self.entered_at).total_seconds() / 60
        return minutes >= 20

    def exit(self):
        self.active = False
        self.category = None
        self.stable_streak = 0

# ============ ТЕКСТИ КНОПОК ============

MESSAGES = {
    "anxiety": (
        "Відчувати тривогу зараз — це нормальна реакція тіла на ненормальні обставини.\n\n"
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
        "Стрес виснажує не лише думки, а й накопичується в тілі.\n\n"
        "Вправа: Прогресивна м'язова релаксація\n\n"
        "1. Сядь або ляж у зручну позу\n"
        "2. Стисни кулаки на 5 секунд — відпусти\n"
        "3. Підтягни плечі до вух — відпусти\n"
        "4. Зажмур очі — відпусти\n"
        "5. Зроби ковток чистої води\n\n"
        "Щоб розвантажити голову — продовжи діалог із Максимом."
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

user_sessions = {}
crisis_states = {}
user_last_button = {}
user_session_start = {}
user_message_count = {}
user_data_store = {}

SYSTEM_PROMPT_NORMAL = """Ти — Максим, підтримувальний ШІ-компаньйон у підході ACT.

ГОЛОВНЕ: Ти КОРИСНИЙ. Ти ЗАВЖДИ даєш конкретну допомогу. Ніколи не відмовляєш у техніці. Ніколи не повторюєш одне й те саме.

ФОРМАТ:
- Простий текст БЕЗ зірочок, БЕЗ жирного, БЕЗ нумерованих списків
- 80-200 слів
- Тепло, по-людськи
- Дзеркаль мову людини (українська або російська)

ЗАБОРОНЕНО:
- Відмовляти у техніці
- Питати "хочеш техніку?" — давай одразу якщо людина описує стан
- Повторювати одне й те саме питання двічі
- Згадувати гарячі лінії при звичайних зверненнях

ГАРЯЧІ ЛІНІЇ — ТІЛЬКИ КОЛИ людина сама просить або кризові слова.

ДАВАЙ ТЕХНІКУ ОДРАЗУ:
"не можу уснуть", "думки не дають спати" → "Вдих 4 секунди, затримай 7, видих 8. Повтори 4 рази. Відклади телефон."
"накрило", "паніка", "трясе" → "Стопи на підлозі. Повільний видих. Назви 3 речі що бачиш."
"думки крутяться" → "Скажи собі: Я помічаю думку що... Це просто думка. Уяви що вона пливе як хмара."
"злюся", "гнів" → "Пауза. Глибокий видих. Зімни аркуш паперу."
"порожнеча", "апатія" → "Де в тілі ти це відчуваєш? Яке воно? Просто помітити — вже крок."
"навіщо це все", "немає сенсу" → "Якби ця важкість зникла — що важливе ти б робила?"
"болить голова", "стиснуто в грудях" → "Поклади руку туди де відчуваєш. Зроби повільний видих."
"просто хочу виговоритися" → НЕ давай вправу. Слухай і задай одне питання.

ЯКЩО ЛЮДИНА ПРОСИТЬ ГАРЯЧУ ЛІНІЮ:
📞 7333 — Lifeline Ukraine
📞 116 123 — Національна гаряча лінія
📞 1545 — Урядова лінія

РОЗУМІЙ НЕЧІТКІ ЗАПИТИ:
- Помилки, суржик — розумій намір
- "устала", "все", "не можу" → "що зараз найважче?"
- Одне слово → дай техніку або спитай одне

ІМ'Я ТА РІД:
- Тільки ім'я з контексту або що людина сама написала
- НЕ вигадуй і НЕ скорочуй
- Жіночі → зробила, відчула
- Чоловічі → зробив, відчув

ГОРЕ: НЕ давай вправ. "Мені дуже шкода. Це величезна втрата."
ПІДТРИМКА ДОГЛЯДАЧІВ: → "Коли несеш стільки — хто зараз піклується про тебе?"
ПІСЛЯ ВПРАВИ: "Спробував(ла)? Що помітив(ла)?"
ЗАВЕРШЕННЯ:
"дякую" → "Радий що трохи легше. Повертайся коли потрібно. 💙"
"поки" → "Бережи себе. 💙"
"все" → "Як ти зараз? Є що ще на серці?" """

SYSTEM_PROMPT_CRISIS = """Ти — Максим, теплий та надзвичайно емпатичний психологічний помічник.
Користувач перебуває у гострому кризовому стані.
ФОРМАТ: Простий текст БЕЗ зірочок.
- Не проводь вправ якщо не просить
- Якщо просить — дай одну просту (дихання або 5-4-3-2-1)
- Не заспокоюй формулами
- М'яко заохочуй: 7333, 116 123, 1545
- Коротко і дбайливо. Дзеркаль мову."""

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

async def version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Maksym Bot v{VERSION}")
    try:
        sheet = get_sheet()
        if sheet:
            sheet.append_row(["TEST", "version_check", str(update.effective_user.id)], value_input_option="RAW")
            await update.message.reply_text("✅ Google Sheets працює")
        else:
            await update.message.reply_text("❌ Google Sheets не підключений")
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    hour = datetime.now().strftime("%H:00")
    if user.id not in user_data_store:
        user_data_store[user.id] = {}
    if user.id not in crisis_states:
        crisis_states[user.id] = CrisisState()
    log_event("START", user.id, user.username or "", user.first_name or "", user.language_code or "", hour)
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
        await query.message.reply_text("Як ти зараз почуваєшся?", reply_markup=get_main_keyboard())
        return

    if query.data == "maksym":
        if user.id not in user_sessions:
            user_sessions[user.id] = []
        user_session_start[user.id] = datetime.now()
        user_message_count[user.id] = 0
        last_button = user_last_button.get(user.id, "—")
        log_event("MAKSYM_START", user.id, user.username or "", user.first_name or "",
                  user.language_code or "", hour, last_button=last_button)
        keyboard = [[InlineKeyboardButton("🏠 Повернутися до меню", callback_data="menu")]]
        await query.message.reply_text(
            "Привіт, я Максим 👋\n\nРозкажи мені що тебе турбує. Я тут, щоб вислухати.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    button_name = BUTTON_NAMES.get(query.data, query.data)
    user_last_button[user.id] = button_name
    log_event(f"BUTTON: {button_name}", user.id, user.username or "", user.first_name or "",
              user.language_code or "", hour)

    text = MESSAGES.get(query.data, "")
    keyboard = [
        [InlineKeyboardButton("🤖 Почати розмову з Максимом", callback_data="maksym")],
        [InlineKeyboardButton("🏠 Повернутися до меню", callback_data="menu")],
    ]
    await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    hour = datetime.now().strftime("%H:00")

    if user.id not in user_data_store:
        user_data_store[user.id] = {}
    if user.id not in crisis_states:
        crisis_states[user.id] = CrisisState()

    user_data_store[user.id] = extract_user_info(update.message.text, user_data_store[user.id])
    udata = user_data_store[user.id]
    crisis = crisis_states[user.id]

    crisis_type = detect_crisis(update.message.text)

    if crisis_type:
        if not crisis.active:
            crisis.enter(crisis_type)
        else:
            crisis.register_message(had_marker=True)
        if user.id not in user_sessions:
            user_sessions[user.id] = []
        log_event(crisis_type.upper(), user.id, user.username or "", user.first_name or "",
                  user.language_code or "", hour)
        await update.message.reply_text(CRISIS_REPLIES.get(crisis_type, CRISIS_REPLIES["suicide"]))
        return

    if crisis.active:
        crisis.register_message(had_marker=False)
        if crisis.can_exit():
            crisis.exit()

    if user.id not in user_sessions and not crisis.active:
        await update.message.reply_text(
            "Як ти зараз почуваєшся?",
            reply_markup=get_main_keyboard()
        )
        return

    if user.id not in user_sessions:
        user_sessions[user.id] = []

    history = user_sessions.get(user.id, [])
    history.append({"role": "user", "content": update.message.text})
    if len(history) > 20:
        history = history[-20:]

    user_message_count[user.id] = user_message_count.get(user.id, 0) + 1
    count = user_message_count.get(user.id, 0)
    start_time = user_session_start.get(user.id)
    duration = int((datetime.now() - start_time).total_seconds() / 60) if start_time else 0
    last_button = user_last_button.get(user.id, "—")

    system_prompt = SYSTEM_PROMPT_CRISIS if crisis.active else SYSTEM_PROMPT_NORMAL

    user_context = ""
    if udata.get("name"):
        user_context += f"Ім'я: {udata['name']}. "
    if udata.get("gender"):
        user_context += f"Стать: {udata['gender']}. "
    if udata.get("age"):
        user_context += f"Вік: {udata['age']} років. "
    if user_context:
        system_prompt = system_prompt + f"\n\nКОНТЕКСТ: {user_context}"

    extra_question = ""
    if count == 3 and not udata.get("name") and not crisis.active:
        extra_question = "\n\nДо речі, як тебе звати?"
    elif count == 5 and not udata.get("age") and not crisis.active:
        extra_question = "\n\nСкільки тобі років? Щоб краще розуміти твою ситуацію."

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
                  user.language_code or "", hour,
                  last_button=last_button, msg_count=count, duration=duration)
        keyboard = [[InlineKeyboardButton("🏠 Повернутися до меню", callback_data="menu")]]
        await update.message.reply_text(reply, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        print(f"GPT ERROR: {e}")
        await update.message.reply_text("Вибач, сталася помилка. Спробуй ще раз.")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("version", version))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
