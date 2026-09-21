# ============================================
# MAKSYM BOT
# Версія: 3.0.1
# Дата: 2026-09-21
# Автор: morestry
# Зміни від 3.0:
#   - Фікс: детектори спрацьовують до перевірки сесії
#   - Фікс: телефони з нового рядка в GPT промпті
#   - Фікс: медичний детектор — додано нечіткі паттерни
#   - Фікс: нечитабельний ввід — ужорсткено поріг
#   - Додано: російські паттерни військового контексту
#   - Додано: російські паттерни пошуку психолога
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
import pytz

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
GOOGLE_CREDENTIALS = os.environ.get("GOOGLE_CREDENTIALS")

VERSION = "3.0.1 | 2026-09-21"
KYIV_TZ = pytz.timezone("Europe/Kyiv")

def now_kyiv():
    return datetime.now(KYIV_TZ)

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

def get_users_sheet():
    try:
        creds_dict = json.loads(GOOGLE_CREDENTIALS)
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)
        try:
            return spreadsheet.worksheet("Користувачі")
        except:
            sheet = spreadsheet.add_worksheet(title="Користувачі", rows=1000, cols=12)
            sheet.append_row([
                "ID", "Username", "Ім'я (TG)", "Ім'я (назвав сам)",
                "Стать", "Вік", "Місто", "Мова", "Перший візит",
                "Останній візит", "Всього сесій", "Повідомлень Максиму"
            ], value_input_option="RAW", table_range="A1")
            return sheet
    except Exception as e:
        print(f"GET_USERS_SHEET ERROR: {e}")
        return None

def log_event(event_type, user_id, username="", first_name="", language="",
              hour="", last_button="", msg_count="", duration=""):
    try:
        sheet = get_sheet()
        if not sheet:
            return
        now = now_kyiv().strftime("%Y-%m-%d %H:%M:%S")
        is_anon = "Анонім" if not username else "Є username"
        row = [
            now, event_type, str(user_id),
            str(username or ""), str(first_name or ""), str(language or ""),
            str(hour or ""), is_anon,
            get_weekday_ua(), get_time_of_day(),
            str(last_button or ""), str(msg_count or ""), str(duration or ""),
        ]
        sheet.append_row(row, value_input_option="RAW", table_range="A1")
        print(f"LOG OK: {event_type} {user_id}")
    except Exception as e:
        print(f"LOG_EVENT ERROR: {e}")

def update_user_record(user_id, username, first_name, language, udata, is_start=False, new_message=False):
    try:
        sheet = get_users_sheet()
        if not sheet:
            return
        now = now_kyiv().strftime("%Y-%m-%d %H:%M:%S")
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
            if new_message:
                messages += 1
            new_values = [[
                username, first_name,
                best(udata.get("name", ""), existing[3]),
                best(udata.get("gender", ""), existing[4]),
                best(udata.get("age", ""), existing[5]),
                best(udata.get("location", ""), existing[6]),
                language,
                existing[8] if existing[8] else now,
                now, sessions, messages,
            ]]
            sheet.update(values=new_values, range_name=f"B{user_row}:L{user_row}")
        else:
            sheet.append_row([
                str(user_id), username, first_name,
                udata.get("name", ""), udata.get("gender", ""),
                udata.get("age", ""), udata.get("location", ""),
                language, now, now,
                1 if is_start else 0,
                1 if new_message else 0,
            ], value_input_option="RAW", table_range="A1")
    except Exception as e:
        print(f"UPDATE_USER ERROR: {e}")

def get_time_of_day():
    h = now_kyiv().hour
    if 6 <= h < 12:
        return "Ранок"
    elif 12 <= h < 18:
        return "День"
    elif 18 <= h < 23:
        return "Вечір"
    else:
        return "Ніч"

def get_weekday_ua():
    weekday = now_kyiv().strftime("%A")
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
        r'мене звати\s+(\w+)', r'мене зовуть\s+(\w+)',
        r'меня зовут\s+(\w+)', r'я\s+(\w+)$', r'я\s+(\w+),',
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
    return user_data

def is_gibberish(text):
    text = text.strip()
    if len(text) < 3:
        return True
    if not re.search(r'[a-zA-Zа-яА-ЯіІїЇєЄґҐ]', text):
        return True
    if re.match(r'^(.)\1{4,}$', text):
        return True
    letters = re.findall(r'[a-zA-Zа-яА-ЯіІїЇєЄґҐ]', text)
    if len(letters) < 3:
        return True
    vowels = re.findall(r'[aeiouаеіоуиєїюя]', text.lower())
    if len(letters) >= 4 and len(vowels) / len(letters) < 0.25:
        return True
    if ' ' not in text and len(text) > 5:
        if len(vowels) / max(len(letters), 1) < 0.25:
            return True
    return False

MEDICAL_PATTERNS = [
    r'задиха\w*|задыха\w*',
    r'не\s*мо[жг]\w*\s*(дихати|дышать)',
    r'важко\s*дихати|тяжело\s*дышать',
    r'втрача\w*\s*свідом\w*|теря\w*\s*созна\w*',
    r'знепритомн\w*|непритомн\w*',
    r'серцев\w*\s*напад|сердечн\w*\s*(напад|приступ)',
    r'інсульт\w*|инсульт\w*',
    r'болить\s*серце|болит\s*сердце|серце\s*болить',
    r'не\s*мо[жг]\w*\s*(встати|встать)',
    r'кровотеч\w*|кровотек\w*',
    r'оніміл\w*\s*(руки?|ноги?)|онемел\w*\s*(руки?|ноги?)',
    r'втрача\w*\s*зір|теря\w*\s*зрен',
    r'виклич\w*\s*швидку|вызов\w*\s*скорую',
    r'умира\w*|помира\w*',
]
_MEDICAL_RE = [re.compile(p, re.IGNORECASE) for p in MEDICAL_PATTERNS]

def detect_medical_emergency(text):
    return any(r.search(text) for r in _MEDICAL_RE)

MEDICAL_REPLY = (
    "Це серйозно. Будь ласка, негайно:\n\n"
    "📞 112 — Екстрена медична допомога\n\n"
    "Якщо можеш — ляж горизонтально. "
    "Попроси когось поруч допомогти або зателефонувати. "
    "Я тут, але зараз найважливіше — виклик 112. 💙"
)

ALL_AT_ONCE_PATTERNS = [
    r'все\s*(і|и|та)\s*одразу',
    r'всё\s*сразу',
    r'все\s*одночасно',
    r'всі\s*(пункти|кнопки|теми)',
    r'і\s*(стрес|тривога|апатія|злість|сон|самотність).{0,30}і\s*(стрес|тривога|апатія|злість|сон|самотність)',
]
_ALL_AT_ONCE_RE = [re.compile(p, re.IGNORECASE) for p in ALL_AT_ONCE_PATTERNS]

def detect_all_at_once(text):
    return any(r.search(text) for r in _ALL_AT_ONCE_RE)

ALL_AT_ONCE_REPLY = (
    "Коли все навалюється одразу — це дуже важко. "
    "Не треба обирати одну тему.\n\n"
    "Просто напиши Максиму як є — він вислухає. 💙"
)

HOMICIDAL_PATTERNS = [
    r'хоч\w+\s*вби\w+|хочу\s*убит\w+',
    r"вб'ю\s*(його|її|тебе|вас)",
    r'убью\s*(его|её|тебя|вас)',
    r'він\s*.{0,20}не\s*доживе|она\s*.{0,20}не\s*доживет',
    r'хоч\w+\s*щоб\s*(він|вона|он|она)\s*.{0,20}(помер|помрла|умер|умерла)',
    r'знищ\w+\s*(його|її|его|её)',
]
_HOMICIDAL_RE = [re.compile(p, re.IGNORECASE) for p in HOMICIDAL_PATTERNS]

def detect_homicidal(text):
    return any(r.search(text) for r in _HOMICIDAL_RE)

HOMICIDAL_REPLY = (
    "Я чую, що ти зараз переживаєш дуже сильний гнів або відчай. "
    "Це важкі емоції, і ти маєш право їх відчувати.\n\n"
    "Але намір завдати шкоди іншій людині — це межа, яку не можна переходити.\n\n"
    "Зараз важливо зупинитися. Відійди фізично від ситуації.\n\n"
    "Будь ласка, зателефонуй:\n\n"
    "📞 0 800 100 102 — психологічна допомога (безкоштовно, анонімно)\n"
    "📞 116 123 — кризова підтримка\n"
    "📞 102 — поліція (якщо конфлікт вже фізичний)\n\n"
    "Розкажи мені — що сталося? Давай розберемося в емоціях, без насильства. 💙"
)

MILITARY_SELF_PATTERNS = [
    r'я\s*(військов\w+|солдат|боєць|офіцер|сержант)',
    r'я\s*(на\s*передовій|в\s*окопі|на\s*позиції|на\s*фронті)',
    r'у\s*мене\s*(бойове\s*завдання|ротація|демобілізація)',
    r'я\s*(ветеран|демобілізован\w+)',
    r'я\s*(военн\w+|солдат|боец|офицер|сержант)',
    r'я\s*(на\s*фронте|в\s*окопе|на\s*позиции|на\s*передовой)',
    r'я\s*(ветеран|демобилизован\w+)',
    r'я\s*в\s*армии|я\s*служу',
    r'наша\s*часть|мой\s*взвод|мой\s*командир',
]
_MILITARY_SELF_RE = [re.compile(p, re.IGNORECASE) for p in MILITARY_SELF_PATTERNS]

def detect_military_self(text):
    return any(r.search(text) for r in _MILITARY_SELF_RE)

MILITARY_REPLY = (
    "Я чую тебе. Те, що ти несеш — дуже важко.\n\n"
    "Я цивільний бот і не маю підготовки для роботи з бойовим досвідом. "
    "Для тебе є фахівці які розуміють цей контекст:\n\n"
    "📞 7333 — Lifeline Ukraine, є досвід з військовими (цілодобово)\n"
    "📞 5522 — Військова психологічна підтримка\n\n"
    "Зателефонуй — там тебе зрозуміють. 💙"
)

COMBAT_GRIEF_PATTERNS = [
    r'(побратим|товариш|бойовий\s*друг).{0,50}(помер|загин\w+|вбил\w+|втрат\w+)',
    r'(загин\w+|помер|вбил\w+).{0,50}(побратим|товариш)',
    r'командир.{0,50}(вбит\w+|вин\w+|відправ\w+|послав)',
    r'(вбит\w+|ненавиджу|хочу\s*вби\w+).{0,50}командир',
    r'через\s*командира.{0,30}(загин\w+|помер|вбил\w+)',
    r'(побратим|товарищ).{0,50}(погиб|убил\w+|потерял\w+)',
    r'командир.{0,50}(виноват|отправил|послал)',
    r'хочу\s*убить\s*командира',
]
_COMBAT_GRIEF_RE = [re.compile(p, re.IGNORECASE) for p in COMBAT_GRIEF_PATTERNS]

def detect_combat_grief(text):
    return any(r.search(text) for r in _COMBAT_GRIEF_RE)

COMBAT_GRIEF_REPLY = (
    "Втратити побратима — це біль, який неможливо описати словами. "
    "Мені дуже шкода.\n\n"
    "Гнів який ти відчуваєш — він реальний і зрозумілий. "
    "Але намір завдати шкоди — це межа.\n\n"
    "Я цивільний бот. Те що ти переживаєш потребує фахової підтримки:\n\n"
    "📞 7333 — Lifeline Ukraine, досвід з військовими (цілодобово)\n"
    "📞 5522 — Військова психологічна підтримка\n\n"
    "Зателефонуй. Ти не повинен нести це один. 💙"
)

PSYCHOLOGIST_PATTERNS = [
    r'(знайди|знайдіть|порадь|де\s*знайти|як\s*знайти)\s*.{0,15}психолог\w+',
    r'хоч\w+\s*(до\s*)?психолог\w+',
    r'потрібн\w+\s*психолог\w+',
    r'запис\w+\s*(до\s*)?психолог\w+',
    r'(найди|найдите|посоветуй|где\s*найти|как\s*найти)\s*.{0,15}психолог\w+',
    r'хочу\s*(к\s*)?психолог\w+',
    r'нужен\s*психолог\w*',
    r'запись\s*(к\s*)?психолог\w+',
    r'ищу\s*психолог\w+',
]
_PSYCHOLOGIST_RE = [re.compile(p, re.IGNORECASE) for p in PSYCHOLOGIST_PATTERNS]

def detect_psychologist_request(text):
    return any(r.search(text) for r in _PSYCHOLOGIST_RE)

PSYCHOLOGIST_REPLY = (
    "Я не можу знайти психолога за тебе, але можу підказати куди звернутися.\n\n"
    "🆓 Безкоштовна допомога в Одесі:\n"
    "Психологічний центр «Альянс ментального здоров'я»\n"
    "📞 +38093 90 333 90\n"
    "📍 пров. Івана Луценка 21/23, БЦ «Ольвія», 6 поверх\n"
    "🕐 Пн–Сб 10:00–17:00\n"
    "💬 t.me/AMZ_psychology\n\n"
    "Або шукай самостійно через реєстр психологів чи платформи онлайн-терапії.\n\n"
    "Що зараз важливіше — поговорити зі мною або знайти фахівця?"
)

SUICIDE_PATTERNS = [
    r"не\s*хоч\w*\s*(більше\s*|вже\s*|далі\s*)?жи\w*",
    r"жи\w*\s*не\s*хоч\w*",
    r"суїцид\w*|суицид\w*|самогубств\w*|самоубийств\w*",
    r"(по)?кінч\w*\s*(із|з|с)\s*(соб|жит)\w*",
    r"вбит\w*\s*себе|убит\w*\s*себя",
    r"нема\w*\s*сенс\w*\s*жи\w*|нет\s*смысла\s*жи\w*",
    r"(всім|всем)\s*.{0,15}(краще|лучше)\s*без\s*мен\w*",
    r"я\s*(всім|всем)\s*(тягар|обуза)",
    r"повіс\w+|повес\w+",
    r"зарізати\s*себе|перерізати\s*вени|скоротити\s*вік\w+",
    r"не\s*хочу\s*жить|не\s*хочу\s*жити",
]

SELF_HARM_PATTERNS = [
    r"(по)?р[іи]з\w*\s*себе|(по)?рез\w*\s*себя",
    r"(вдар|удар)\w*\s*себе",
    r"self.?harm|селфхарм",
    r"різати\s*вени|резать\s*вены",
]

VIOLENCE_VICTIM_PATTERNS = [
    r"мене\s*(б'ют|бьют|б'є|бье|побил|побив)\w*",
    r"меня\s*(бьют|бьет|избил|ударил)\w*",
    r"домашн\w*\s*насильств\w*",
    r"(він|чоловік|муж|батько)\s*.{0,20}(б'є|бье|бив|бил)\w*",
]

_SUICIDE_RE = [re.compile(p, re.IGNORECASE) for p in SUICIDE_PATTERNS]
_SELF_HARM_RE = [re.compile(p, re.IGNORECASE) for p in SELF_HARM_PATTERNS]
_VIOLENCE_VICTIM_RE = [re.compile(p, re.IGNORECASE) for p in VIOLENCE_VICTIM_PATTERNS]

CLASSIFIER_PROMPT = """Ти — класифікатор безпеки. Визнач чи містить повідомлення маркери кризового стану.
Категорії: suicide, self_harm, violence, none.
Безглузді слова — none. Впевненість нижче 0.7 — none.
JSON: {"category": "...", "confidence": 0.0-1.0}"""

def _regex_check(text):
    t = text.lower()
    if any(r.search(t) for r in _SUICIDE_RE):
        return "suicide"
    if any(r.search(t) for r in _SELF_HARM_RE):
        return "self_harm"
    if any(r.search(t) for r in _VIOLENCE_VICTIM_RE):
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
            max_tokens=40, temperature=0,
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

CRISIS_SYSTEM_PROMPTS = {
    "suicide": """Ти — Максим, теплий психологічний помічник. Користувач висловив суїцидальні думки.

ОБОВ'ЯЗКОВО в кожній відповіді (різними словами):
- Визнання болю (1-2 речення)
- Номери телефонів КОЖЕН З НОВОГО РЯДКА:
  📞 7333 — Lifeline Ukraine (цілодобово, безкоштовно)
  📞 116 123 — Національна гаряча лінія
  📞 1545 — Урядова гаряча лінія
  📞 112 — Екстрена допомога
- Одне запитання про те що зараз відбувається

ЗАБОРОНЕНО: "добре що сказав(ла)", техніки, телефони в один рядок через кому, повтор попередньої відповіді дослівно.
Простий текст БЕЗ зірочок. Дзеркаль мову (UA/RU). 80-120 слів.""",

    "self_harm": """Ти — Максим, теплий психологічний помічник. Користувач говорить про самоушкодження.

ОБОВ'ЯЗКОВО (кожен номер з нового рядка):
- Визнання болю (1-2 речення)
- 📞 7333 — Lifeline Ukraine (цілодобово, безкоштовно)
- 📞 116 123 — Національна гаряча лінія
- Одне запитання

ЗАБОРОНЕНО: "добре що сказав", техніки, телефони через кому, повтор дослівно.
БЕЗ зірочок. Дзеркаль мову. 60-100 слів.""",

    "violence": """Ти — Максим, теплий психологічний помічник. Користувач повідомляє про насильство щодо себе.

ОБОВ'ЯЗКОВО (кожен номер з нового рядка):
- Визнання ситуації
- 📞 116 123 — Національна лінія (насильство, цілодобово)
- 📞 1547 — Урядова лінія підтримки
- 📞 102 — Поліція (якщо пряма загроза)
- Питання про безпеку прямо зараз

ЗАБОРОНЕНО: "добре що сказав", телефони через кому, повтор дослівно.
БЕЗ зірочок. Дзеркаль мову. 60-100 слів.""",
}

def generate_crisis_response(user_message, crisis_type, conversation_history):
    try:
        system = CRISIS_SYSTEM_PROMPTS.get(crisis_type, CRISIS_SYSTEM_PROMPTS["suicide"])
        recent_history = conversation_history[-4:] if len(conversation_history) > 4 else conversation_history
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                *recent_history,
                {"role": "user", "content": user_message},
            ],
            max_tokens=300, temperature=0.7,
        )
        return clean_markdown(response.choices[0].message.content)
    except Exception as e:
        print(f"CRISIS GPT ERROR: {e}")
        fallbacks = {
            "suicide": "Я чую що тобі зараз дуже важко.\n\n📞 7333 — Lifeline Ukraine\n📞 116 123\n📞 112\n\nРозкажи що зараз відбувається? 💙",
            "self_harm": "Я чую тебе.\n\n📞 7333 — Lifeline Ukraine\n📞 116 123\n\nЩо зараз відбувається? 💙",
            "violence": "Ти зараз у безпеці?\n\n📞 116 123\n📞 102 — Поліція\n\n💙",
        }
        return fallbacks.get(crisis_type, fallbacks["suicide"])

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
        self.entered_at = now_kyiv()
        self.messages_since = 0
        self.stable_streak = 0

    def register_message(self, had_marker):
        if not self.active:
            return
        self.messages_since += 1
        if had_marker:
            self.stable_streak = 0
            self.entered_at = now_kyiv()
        else:
            self.stable_streak += 1

    def can_exit(self):
        if not self.active:
            return False
        if self.messages_since < 8:
            return False
        if self.stable_streak < 4:
            return False
        minutes = (now_kyiv() - self.entered_at).total_seconds() / 60
        return minutes >= 20

    def exit(self):
        self.active = False
        self.category = None
        self.stable_streak = 0

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
        "Якщо хочеш виговоритися — Максим поруч."
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
        "Відклади телефон. Якщо думки не дають спати — Максим на зв'язку цілодобово."
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
        "Якщо хочеш розділити переживання — напиши Максиму."
    ),
    "anger": (
        "Гнів — це сильна та здорова емоція. Важливо дати йому безпечний вихід.\n\n"
        "Швидкі техніки:\n\n"
        "📄 Зімни аркуш паперу з усієї сили або порви його\n"
        "⏸ Правило 10 секунд: глибоко видихни перед відповіддю\n"
        "🚶 Рух: кілька кроків, потягнися\n\n"
        "Хочеш розібратися що викликало реакцію? Максим вислухає без оцінок."
    ),
    "lost": (
        "Коли земля тікає з-під ніг — спирайся на теперішній момент.\n\n"
        "Вправа «Коло контролю»:\n\n"
        "❌ Не контролюєш: глобальні події, рішення інших, майбутнє\n"
        "✅ Контролюєш: що з'їси, коли ляжеш спати, з ким поговориш\n\n"
        "Сфокусуйся на одній маленькій дії впродовж 15 хвилин.\n\n"
        "Якщо потрібно структурувати хаос — почни діалог із Максимом."
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
psychologist_request_count = {}

SYSTEM_PROMPT_NORMAL = """Ти — Максим, підтримувальний ШІ-компаньйон у підході ACT.

ГОЛОВНЕ: Ти КОРИСНИЙ. ЗАВЖДИ даєш конкретну допомогу. Ніколи не відмовляєш у техніці.

ФОРМАТ: Простий текст БЕЗ зірочок. 80-200 слів. Тепло, по-людськи.
Дзеркаль мову (українська або російська).
Якщо згадуєш номери телефонів — КОЖЕН З НОВОГО РЯДКА, не через кому.

ЗАБОРОНЕНО:
- Відмовляти у техніці
- Питати "хочеш техніку?" — давай одразу
- Повторювати одне й те саме питання двічі
- Згадувати гарячі лінії при звичайних зверненнях
- Давати поради щодо фізичних симптомів (біль в серці, задишка) — направляй до 112

ДАВАЙ ТЕХНІКУ ОДРАЗУ:
"не можу уснуть" → дихання 4-7-8
"паніка", "трясе" → заземлення 5-4-3-2-1
"злюся" → пауза + фізичний виплеск
"апатія" → маленький крок
"просто хочу виговоритися" → НЕ давай вправу. Слухай.

ІМ'Я: тільки з контексту. Жіночі → зробила. Чоловічі → зробив.
ГОРЕ: НЕ давай вправ. "Мені дуже шкода. Це величезна втрата."
ЗАВЕРШЕННЯ: "дякую" → "Радий що трохи легше. Повертайся коли потрібно. 💙" """

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("😰 Тривога та паніка", callback_data="anxiety")],
        [InlineKeyboardButton("😤 Стрес та перенапруження", callback_data="stress")],
        [InlineKeyboardButton("😴 Проблеми зі сном", callback_data="sleep")],
        [InlineKeyboardButton("😶 Апатія та виснаження", callback_data="apathy")],
        [InlineKeyboardButton("😔 Самотність або провина", callback_data="loneliness")],
        [InlineKeyboardButton("😠 Дратівливість та гнів", callback_data="anger")],
        [InlineKeyboardButton("😵 Втрата опори", callback_data="lost")],
    ])

def get_maksym_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Повернутися до меню", callback_data="menu")]])

async def version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Maksym Bot v{VERSION}")
    try:
        sheet = get_sheet()
        if sheet:
            sheet.append_row(["TEST", "version_check", str(update.effective_user.id)],
                             value_input_option="RAW", table_range="A1")
            await update.message.reply_text("✅ Google Sheets працює")
        else:
            await update.message.reply_text("❌ Google Sheets не підключений")
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    hour = now_kyiv().strftime("%H:00")
    if user.id not in user_data_store:
        user_data_store[user.id] = {}
    if user.id not in crisis_states:
        crisis_states[user.id] = CrisisState()
    log_event("START", user.id, user.username or "", user.first_name or "", user.language_code or "", hour)
    try:
        update_user_record(user.id, user.username or "", user.first_name or "",
                          user.language_code or "", user_data_store[user.id], is_start=True)
    except Exception as e:
        print(f"START user record ERROR: {e}")
    await update.message.reply_text(
        "Привіт 👋\n\nЯ тут, щоб підтримати тебе. Як ти зараз почуваєшся?",
        reply_markup=get_main_keyboard()
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    hour = now_kyiv().strftime("%H:00")

    if query.data == "menu":
        await query.message.reply_text("Як ти зараз почуваєшся?", reply_markup=get_main_keyboard())
        return

    if query.data == "maksym":
        if user.id not in user_sessions:
            user_sessions[user.id] = []
        user_session_start[user.id] = now_kyiv()
        user_message_count[user.id] = 0
        last_button = user_last_button.get(user.id, "—")
        log_event("MAKSYM_START", user.id, user.username or "", user.first_name or "",
                  user.language_code or "", hour, last_button=last_button)
        await query.message.reply_text(
            "Привіт, я Максим 👋\n\nРозкажи мені що тебе турбує. Я тут, щоб вислухати.",
            reply_markup=get_maksym_keyboard()
        )
        return

    if query.data == "psychologist_chat":
        if user.id not in user_sessions:
            user_sessions[user.id] = []
        await query.message.reply_text("Добре, розповідай. Я тут. 💙", reply_markup=get_maksym_keyboard())
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
    text = update.message.text
    hour = now_kyiv().strftime("%H:00")

    if user.id not in user_data_store:
        user_data_store[user.id] = {}
    if user.id not in crisis_states:
        crisis_states[user.id] = CrisisState()

    crisis = crisis_states[user.id]

    if is_gibberish(text):
        await update.message.reply_text(
            "Не зовсім зрозумів. Розкажи що відчуваєш? 💙",
            reply_markup=get_maksym_keyboard()
        )
        return

    if detect_medical_emergency(text):
        log_event("MEDICAL_EMERGENCY", user.id, user.username or "", user.first_name or "",
                  user.language_code or "", hour)
        await update.message.reply_text(MEDICAL_REPLY)
        return

    if detect_combat_grief(text):
        log_event("COMBAT_GRIEF", user.id, user.username or "", user.first_name or "",
                  user.language_code or "", hour)
        await update.message.reply_text(COMBAT_GRIEF_REPLY)
        return

    if detect_military_self(text):
        log_event("MILITARY_CONTEXT", user.id, user.username or "", user.first_name or "",
                  user.language_code or "", hour)
        await update.message.reply_text(MILITARY_REPLY)
        return

    if detect_homicidal(text):
        log_event("HOMICIDAL_INTENT", user.id, user.username or "", user.first_name or "",
                  user.language_code or "", hour)
        await update.message.reply_text(HOMICIDAL_REPLY, reply_markup=get_maksym_keyboard())
        return

    if detect_psychologist_request(text):
        psychologist_request_count[user.id] = psychologist_request_count.get(user.id, 0) + 1
        log_event("PSYCHOLOGIST_REQUEST", user.id, user.username or "", user.first_name or "",
                  user.language_code or "", hour)
        keyboard = [
            [InlineKeyboardButton("💬 Поговорити з Максимом", callback_data="psychologist_chat")],
            [InlineKeyboardButton("🏠 Повернутися до меню", callback_data="menu")],
        ]
        await update.message.reply_text(PSYCHOLOGIST_REPLY, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if detect_all_at_once(text):
        keyboard = [
            [InlineKeyboardButton("🤖 Говорити з Максимом", callback_data="maksym")],
            [InlineKeyboardButton("🏠 До меню", callback_data="menu")],
        ]
        await update.message.reply_text(ALL_AT_ONCE_REPLY, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    prev_data = dict(user_data_store[user.id])
    user_data_store[user.id] = extract_user_info(text, user_data_store[user.id])
    udata = user_data_store[user.id]

    crisis_type = detect_crisis(text)

    if crisis_type:
        if not crisis.active:
            crisis.enter(crisis_type)
        else:
            crisis.register_message(had_marker=True)
        if user.id not in user_sessions:
            user_sessions[user.id] = []
        log_event(crisis_type.upper(), user.id, user.username or "", user.first_name or "",
                  user.language_code or "", hour)
        history = user_sessions.get(user.id, [])
        reply = generate_crisis_response(text, crisis_type, history)
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": reply})
        if len(history) > 20:
            history = history[-20:]
        user_sessions[user.id] = history
        await update.message.reply_text(reply, reply_markup=get_maksym_keyboard())
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
    history.append({"role": "user", "content": text})
    if len(history) > 20:
        history = history[-20:]

    user_message_count[user.id] = user_message_count.get(user.id, 0) + 1
    count = user_message_count.get(user.id, 0)
    start_time = user_session_start.get(user.id)
    duration = int((now_kyiv() - start_time).total_seconds() / 60) if start_time else 0
    last_button = user_last_button.get(user.id, "—")

    system_prompt = SYSTEM_PROMPT_NORMAL
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
            messages=[{"role": "system", "content": system_prompt}, *history],
            max_tokens=500
        )
        reply = clean_markdown(response.choices[0].message.content)
        if extra_question:
            reply = reply + extra_question
        history.append({"role": "assistant", "content": reply})
        user_sessions[user.id] = history
        log_event("MAKSYM_MESSAGE", user.id, user.username or "", user.first_name or "",
                  user.language_code or "", hour,
                  last_button=last_button, msg_count=count, duration=duration)
        if udata != prev_data:
            try:
                update_user_record(user.id, user.username or "", user.first_name or "",
                                  user.language_code or "", udata, new_message=True)
            except Exception as e:
                print(f"MSG user record ERROR: {e}")
        await update.message.reply_text(reply, reply_markup=get_maksym_keyboard())
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
