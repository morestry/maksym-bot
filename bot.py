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

def get_sheet():
    try:
        creds_dict = json.loads(GOOGLE_CREDENTIALS)
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(GOOGLE_SHEET_ID).sheet1
        return sheet
    except:
        return None

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

def log_event(event_type, user_id, username="", first_name="", language="", hour="", extra="", user_name_given="", gender="", age="", location=""):
    try:
        sheet = get_sheet()
        if sheet:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            is_anon = "Анонім" if not username else "Є username"
            weekday_ua = get_weekday_ua()
            time_of_day = get_time_of_day()
            sheet.append_row([
                now, event_type, str(user_id), username, first_name,
                language, hour, is_anon, weekday_ua, time_of_day, extra,
                user_name_given, gender, age, location
            ])
    except:
        pass

def extract_user_info(text, user_data):
    text_lower = text.lower()

    # Розпізнавання віку
    age_match = re.search(r'\b(\d{1,2})\s*(рік|років|года|лет|год)\b', text_lower)
    if age_match and not user_data.get("age"):
        age = int(age_match.group(1))
        if 10 <= age <= 99:
            user_data["age"] = str(age)

    # Розпізнавання статі по імені або фразах
    female_indicators = ["я жінка", "я дівчина", "я мама", "я дружина", "я донька", "я сестра"]
    male_indicators = ["я чоловік", "я хлопець", "я тато", "я муж", "я брат", "я син"]

    if not user_data.get("gender"):
        if any(w in text_lower for w in female_indicators):
            user_data["gender"] = "Жінка"
        elif any(w in text_lower for w in male_indicators):
            user_data["gender"] = "Чоловік"

    # Розпізнавання міста/країни
    location_keywords = ["живу в", "я з", "я в", "нахожусь в", "знаходжусь в", "перебуваю в", "я за кордоном", "я в україні", "я в польщі", "я в німеччині"]
    if not user_data.get("location"):
        for keyword in location_keywords:
            if keyword in text_lower:
                idx = text_lower.find(keyword)
                location_text = text[idx + len(keyword):idx + len(keyword) + 30].strip()
                location_text = location_text.split()[0] if location_text.split() else ""
                if location_text:
                    user_data["location"] = location_text
                break

    return user_data

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
        "Це лише перший крок, щоб зняти гостру напругу. Якщо ти відчуваєш потребу виговоритися, поділитися тим, що викликає тривогу, або просто не залишатися наодинці — ти можеш поспілкуватися з нашим ШІ-помічником Максимом. Він поруч і готовий вислухати."
    ),
    "stress": (
        "Стрес виснажує не лише думки, а й накопичується в тілі у вигляді затисків. Коли нервова система перевантажена, важливо дати їй сигнал: «Зараз я в безпеці, можна розслабитися».\n\n"
        "Вправа: Прогресивна м'язова релаксація\n\n"
        "1. Сядь або ляж у зручну позу\n"
        "2. Міцно стисни кулаки та напруж руки на 5 секунд\n"
        "3. Різко розслаб руки та зроби глибокий видих\n"
        "4. Повтори те саме з плечима, обличчям та ногами\n"
        "5. Наприкінці зроби ковток чистої води\n\n"
        "Пам'ятай: зараз твій головний пріоритет — відновити базові сили.\n\n"
        "Щоб розвантажити голову від зайвих думок та розкласти все по поличках, ти можеш продовжити діалог із Максимом."
    ),
    "sleep": (
        "Складність із засинанням — це чіткий сигнал, що мозок продовжує опрацьовувати денний стрес і не може вимкнути «режим контролю».\n\n"
        "Техніка дихання «4-7-8»:\n\n"
        "1. Заплющ очі та видихни все повітря з легень\n"
        "2. Зроби повільний вдих носом, рахуючи до 4\n"
        "3. Затримай дихання на 7 секунд\n"
        "4. Повільно та повністю видихни ротом, рахуючи до 8\n"
        "5. Повтори цей цикл 4–5 разів\n\n"
        "Відклади телефон екраном донизу і не намагайся «змусити» себе заснути. Просто дай тілу відпочити навіть у режимі спокою.\n\n"
        "Якщо думки не дають заснути і ти хочеш комусь їх довірити перед сном, ШІ-помічник Максим на зв'язку цілодобово."
    ),
    "apathy": (
        "Апатія — це захисна реакція психіки. Коли ресурсів немає, вона вмикає режим економії енергії. Не карай себе за те, що зараз «нічого не хочеться» або «немає сил».\n\n"
        "Стратегія «Маленького кроку»:\n\n"
        "• Не намагайся зробити великі справи. Обирай дію, яка займає не більше 2 хвилин\n"
        "• Зроби ковток води, відчини вікно або просто потягнися\n"
        "• Дозволь собі робити речі на 10% із 100%. Це вже велика перемога\n\n"
        "Твоє завдання зараз — не бути супергероєм, а просто бути дбайливим до себе.\n\n"
        "Потрібна підтримка без оцінок та вимог? Поспілкуйся з Максимом. Він підлаштується під твій темп і не буде тиснути."
    ),
    "loneliness": (
        "Ти не один/одна, навіть якщо зараз здається абсолютно навпаки. Відчувати відчуженість чи провину за свої думки, дії чи «недостатню ефективність» — поширений біль під час важких випробувань.\n\n"
        "Практика співчуття до себе:\n\n"
        "1. Поклади долоню собі на груди або обійми себе за плечі\n"
        "2. Скажи собі подумки: «Мені зараз важко. Але я роблю все, що в моїх силах. Я маю право на свої почуття»\n"
        "3. Згадай, що ти заслуговуєш на тепло так само, як і будь-хто інший\n\n"
        "Якщо ти хочеш розділити ці переживання з тим, хто приймає тебе без будь-якого осуду, напиши Максиму. Він завжди поруч."
    ),
    "anger": (
        "Гнів — це сильна та здорова емоція. Вона сигналізує про те, що твої кордони порушено або внутрішній чан переповнений. Гнів не робить тебе «поганою» людиною — важливо лише дати йому безпечний вихід.\n\n"
        "Швидкі техніки безпечного скидання напруги:\n\n"
        "📄 Фізичний виплеск: візьми аркуш паперу та зімни його з усієї сили або порви на дрібні шматочки\n"
        "⏸ Правило 10 секунд: зроби паузу перед тим, як відповісти. Глибоко видихни\n"
        "🚶 Рух: кілька кроків, потягнися, поворуши плечима\n\n"
        "Хочеш випустити пару або розібратися, що саме викликало таку реакцію? Наш ШІ-асистент Максим вислухає все без драм та оцінок."
    ),
    "lost": (
        "Коли земля тікає з-під ніг і майбутнє здається туманним, єдине, на що можна спиратися — це теперішній момент і прості дії.\n\n"
        "Вправа «Коло контролю»:\n\n"
        "❌ Не контролюєш: глобальні події, рішення інших людей, майбутнє\n"
        "✅ Контролюєш: що ти з'їси, коли підеш спати, що вдягнеш, з ким поговориш\n\n"
        "Сфокусуйся лише на одній маленькій дії, яку ти можеш зробити впродовж наступних 15 хвилин. Твоя опора створюється з маленьких щоденних рішень.\n\n"
        "Якщо тобі потрібно обговорити свої плани, пошукати нові сенси чи просто структурувати хаос у голові — почни діалог із Максимом."
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

CRISIS_KEYWORDS = [
    "суїцид", "самогубство", "вбити себе", "убить себя",
    "не хочу жити", "не хочу жить", "хочу умереть", "хочу померти",
    "покончить с жизнью", "покінчити з життям", "покінчити життя",
    "кончаю з собою", "нет смысла жить", "немає сенсу жити",
    "всем будет лучше без меня", "всім буде краще без мене",
    "краще б мене не було", "лучше бы меня не было",
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

user_sessions = {}
crisis_users = set()
user_last_button = {}
user_session_start = {}
user_message_count = {}
user_data_store = {}

SYSTEM_PROMPT_NORMAL = """Ти — Максим, підтримувальний ШІ-компаньйон у підході ACT.

ГОЛОВНЕ: Ти КОРИСНИЙ. Ти ЗАВЖДИ даєш конкретну допомогу. Ніколи не відмовляєш у техніці. Ніколи не повторюєш одне й те саме.

ЗАБОРОНЕНІ ФРАЗИ:
- "я не можу поділитися техніками"
- "зверніться до фахівця" (лише раз за розмову, не в кожній відповіді)
- "як ти почуваєшся?" якщо людина вже сказала
- будь-які відмови допомогти

ІМ'Я ТА РІД:
- Якщо людина сама назвала ім'я — використовуй його одразу
- Якщо не назвала — через 2-3 повідомлення спитай природно: "До речі, як тебе звати?"
- По імені визнач рід: Марія/Оля/Тетяна → зробила, відчула; Олег/Іван → зробив, відчув
- Якщо не зрозуміло → спитай: "Як правильно — ти зробив чи зробила?"
- Не питай ім'я якщо людина в гострому стані

ВІК ТА МІСТО:
- Через 4-5 повідомлень спитай природно: "Скільки тобі років? Щоб краще розуміти твою ситуацію"
- Пізніше: "Ти зараз в Україні чи за кордоном?"
- Не питай всього одразу — розкидай по розмові природно

РОЗУМІЙ НЕЧІТКІ ЗАПИТИ:
- Люди пишуть з помилками, суржиком, нечітко — розумій намір
- "какие техники", "що робити", "помоги" → дай вправу одразу
- "устала", "все", "не можу" → спитай одне: "що зараз найважче?"
- одне слово ("страх", "тривога", "погано") → цього достатньо
- ніколи не проси переформулювати

ЩО ДАВАТИ НА КОНКРЕТНІ ЗАПИТИ:

"накрило", "паніка", "не можу дихати", "трясе" →
Заземлення: "Стопи на підлозі. Повільний видих. Назви 3 речі що бачиш."

"думки крутяться", "не можу зупинити думки", "прокручую одне й те саме" →
Розлиття: "Скажи собі: Я помічаю думку що... Це просто думка, не факт. Уяви що вона пливе як хмара."

"техніки від безсоння", "як заснути", "думки не дають спати" →
Дихання 4-7-8: "Вдих 4 секунди, затримай 7, видих 8. Повтори 4 рази. Відклади телефон."

"як заспокоїтись", "що робити зараз", "є якась вправа" →
Дай вправу одразу без довгих пояснень.

"злюся", "гнів", "роздратування", "хочу кричати" →
"Пауза. Глибокий видих. Зімни аркуш паперу — дай тілу вихід."

"порожнеча", "нічого не відчуваю", "апатія" →
"Де в тілі ти це відчуваєш? Яке воно? Просто помітити — вже крок."

"навіщо це все", "немає сенсу", "не розумію чого хочу" →
"Якби ця важкість зникла — що важливе ти б робила?"

"просто хочу виговоритися", "нема кому розказати" →
НЕ давай вправу. Слухай і задай одне питання.

"боюсь", "страшно", "тривожно" →
Спитай одне: "Що зараз найбільше лякає?" або дай заземлення.

"болить голова", "стиснуто в грудях", "важко дихати", "ком у горлі" →
"Відчуй де саме це в тілі. Поклади руку туди. Зроби повільний видих прямо в це місце."

ГОРЕ І ВТРАТА:
"хтось помер", "він загинув", "вона померла", "загинув на фронті" →
НЕ давай вправ. Просто присутність: "Мені дуже шкода. Це величезна втрата. Не потрібно нікуди поспішати з цим болем. Розкажи мені про нього/неї якщо хочеш."

"не можу змиритись", "як жити далі після втрати" →
"Горе не має правильного темпу. Те що ти відчуваєш — це любов якій нема куди йти."

"вже давно але все одно боляче" →
"Горе повертається хвилями — і це нормально. Що зараз підняло цю хвилю?"

НІКОЛИ при горі: "час лікує", "він в кращому місці", "треба триматись"

ПІДТРИМКА ТИХ ХТО ДОГЛЯДАЄ:
"чоловік на фронті", "брат воює", "турбуюсь за чоловіка" →
"Чекати і не знати — один з найважчих видів тривоги. Як ти зараз сама?"

"дитина хворіє", "дитина в стресі" →
Спочатку про маму/тата: "Коли дитині важко — тобі вдвічі важче. Що зараз відбувається?"

"доглядаю за мамою", "тато після інсульту" →
"Догляд за близькою людиною — це марафон. Коли ти востаннє думала про себе?"

"все на мені", "я одна з усім" →
"Нести все одній — це дуже важко. Що зараз найважче з усього цього?"

ПЕРЕВІРКА ПІСЛЯ ВПРАВИ:
Після кожної вправи додай одне питання:
- "Спробувала? Що помітила?"
- "Як тобі це відчуття?"
- "Що змінилось після цього?"

Якщо "не допомогло", "не відчула нічого" →
"Це нормально — іноді перший раз просто знайомство. Хочеш спробуємо іншу?"

НАГАДУВАННЯ ПРО СЕБЕ:
Коли людина зробила щось важке (прийшла, розповіла, спробувала) →
"Те що ти тут — це вже крок. Не всі роблять навіть це."

Коли людина себе критикує →
"Слабкі люди не шукають допомоги. Ти тут — це сила."

ЗАВЕРШЕННЯ РОЗМОВИ:
"дякую", "допомогло", "стало краще" →
"Радий що трохи легше. Ти зробила важливий крок — прийшла сюди. Повертайся коли потрібно. 💙"

"поки", "до побачення" →
"Бережи себе. Повертайся коли потрібно — тут завжди є місце для тебе. 💙"

"все", "ладно" →
Не закривай одразу. Спитай: "Як ти зараз? Є що ще на серці?"

ЯК РОЗМОВЛЯТИ:
- Коротко (80-200 слів), у темп людини
- Тепло, по-людськи, без зверхності
- Дзеркаль мову людини (українська або російська)
- Одна вправа за раз
- Після вправи — перевір як пройшло

ДО ПСИХОЛОГА НАПРАВЛЯЙ тільки коли:
- Людина сама питає як знайти психолога
- Ситуація повторюється і бот не допомагає
- Щось серйозне що виходить за межі підтримки
НЕ вставляй це в кожну відповідь."""

SYSTEM_PROMPT_CRISIS = """Ти — Максим, теплий та надзвичайно емпатичний психологічний помічник.

Користувач перебуває у гострому кризовому стані. Твоя мета — вислухати людину без засудження, валідувати її біль, дати відчути що вона не одна.

ВАЖЛИВО:
- Не проводь вправ якщо людина не просить
- Якщо людина прямо просить техніку — дай одну просту (дихання або 5-4-3-2-1)
- Не заспокоюй формулами ("все буде добре")
- М'яко заохочуй зателефонувати: 7333, 116 123, 1545
- Пиши коротко, тепло і дуже дбайливо
- Дзеркаль мову людини (українська або російська)
- Не питай про спосіб чи план
- Не повторюй одне й те саме питання двічі"""

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    hour = datetime.now().strftime("%H:00")
    if user.id not in user_data_store:
        user_data_store[user.id] = {}
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
        log_event("MAKSYM_START", user.id, user.username or "", user.first_name or "", user.language_code or "", hour, extra=f"Прийшов з: {last_button}")
        keyboard = [[InlineKeyboardButton("🏠 Повернутися до меню", callback_data="menu")]]
        await query.message.reply_text(
            "Привіт, я Максим 👋\n\nРозкажи мені що тебе турбує. Я тут, щоб вислухати.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    button_name = BUTTON_NAMES.get(query.data, query.data)
    user_last_button[user.id] = button_name
    log_event(f"BUTTON: {button_name}", user.id, user.username or "", user.first_name or "", user.language_code or "", hour)

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

    user_data_store[user.id] = extract_user_info(update.message.text, user_data_store[user.id])
    udata = user_data_store[user.id]

    if any(word in text_lower for word in VIOLENCE_KEYWORDS):
        crisis_users.add(user.id)
        if user.id not in user_sessions:
            user_sessions[user.id] = []
        log_event("VIOLENCE", user.id, user.username or "", user.first_name or "", user.language_code or "", hour,
                  user_name_given=udata.get("name", ""), gender=udata.get("gender", ""),
                  age=udata.get("age", ""), location=udata.get("location", ""))
        await update.message.reply_text(
            "Те, що ти зараз кажеш — серйозно, і добре, що ти це сказала.\n\n"
            "Ти не мусиш бути з цим наодинці. Допомога поруч:\n\n"
            "📞 *116 123* — Національна лінія (насильство, цілодобово, безкоштовно)\n"
            "📞 *1547* — Урядова лінія підтримки\n"
            "📞 *102* — Поліція (якщо є безпосередня загроза)\n\n"
            "Якщо ти зараз у небезпеці — будь ласка, зателефонуй або вийди в безпечне місце. 💙",
            parse_mode="Markdown"
        )
        return

    if any(word in text_lower for word in SELF_HARM_KEYWORDS):
        crisis_users.add(user.id)
        if user.id not in user_sessions:
            user_sessions[user.id] = []
        log_event("SELF_HARM", user.id, user.username or "", user.first_name or "", user.language_code or "", hour,
                  user_name_given=udata.get("name", ""), gender=udata.get("gender", ""),
                  age=udata.get("age", ""), location=udata.get("location", ""))
        await update.message.reply_text(
            "Я чую, що тобі зараз дуже боляче. Дякую, що сказала про це.\n\n"
            "Будь ласка, не залишайся з цим сам на сам:\n\n"
            "📞 *7333* — Lifeline Ukraine (цілодобово, безкоштовно)\n"
            "📞 *116 123* — Національна гаряча лінія\n\n"
            "Розкажи мені, що зараз відбувається? Я тут і слухаю. 💙",
            parse_mode="Markdown"
        )
        return

    if any(word in text_lower for word in CRISIS_KEYWORDS):
        crisis_users.add(user.id)
        if user.id not in user_sessions:
            user_sessions[user.id] = []
        log_event("CRISIS", user.id, user.username or "", user.first_name or "", user.language_code or "", hour,
                  user_name_given=udata.get("name", ""), gender=udata.get("gender", ""),
                  age=udata.get("age", ""), location=udata.get("location", ""))
        await update.message.reply_text(
            "Я бачу, що тобі зараз неймовірно важко і боляче. Дякую, що не залишилася з цим наодинці.\n\n"
            "Будь ласка, зателефонуй — тебе вислухають і підтримають:\n\n"
            "📞 *7333* — Lifeline Ukraine (цілодобово, безкоштовно)\n"
            "📞 *116 123* — Національна гаряча лінія\n"
            "📞 *1545* — Урядова гаряча лінія\n"
            "📞 *112* — Екстрена допомога\n\n"
            "Ти важливий / важлива. Розкажи мені, що зараз відбувається? Я тут. 💙",
            parse_mode="Markdown"
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

    # Автоматичний вихід з кризового режиму
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

    # Додаємо контекст про користувача в промпт
    user_context = ""
    if udata.get("name"):
        user_context += f"Ім'я користувача: {udata['name']}. "
    if udata.get("gender"):
        user_context += f"Стать: {udata['gender']}. "
    if udata.get("age"):
        user_context += f"Вік: {udata['age']} років. "
    if udata.get("location"):
        user_context += f"Місто/країна: {udata['location']}. "

    if user_context:
        system_prompt = system_prompt + f"\n\nКОНТЕКСТ ПРО КОРИСТУВАЧА: {user_context}"

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
