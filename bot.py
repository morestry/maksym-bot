import os
import openai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

openai.api_key = OPENAI_API_KEY

MESSAGES = {
    "anxiety": "Відчувати тривогу зараз — це нормальна реакція тіла на ненормальні обставини.\n\nПрактика заземлення «5-4-3-2-1»:\n\n👁 5 предметів, які ти бачиш\n✋ 4 речі, які ти можеш відчути на дотик\n👂 3 звуки, які ти чуєш прямо зараз\n👃 2 запахи, які ти відчуваєш\n👅 1 смак — зроби ковток води\n\nЗроби повільний глибокий вдих і видих. Ти впораєшся. 💙",
    "stress": "Стрес виснажує не лише думки, а й накопичується в тілі.\n\nВправа: Прогресивна м'язова релаксація\n\n1. Сядь або ляж у зручну позу\n2. Стисни кулаки на 5 секунд — відпусти\n3. Підтягни плечі до вух — відпусти\n4. Зажмур очі — відпусти\n5. Зроби ковток чистої води 💧",
    "sleep": "Складність із засинанням — сигнал що мозок не може вимкнути «режим контролю».\n\nТехніка дихання «4-7-8»:\n\n1. Видихни все повітря\n2. Вдих носом — 4 секунди\n3. Затримай дихання — 7 секунд\n4. Видих ротом — 8 секунд\n\nПовтори 4-5 разів. Відклади телефон екраном донизу 🌙",
    "apathy": "Апатія — це захисна реакція психіки. Не карай себе за те, що зараз «нічого не хочеться».\n\nСтратегія «Маленького кроку»:\n\n• Обирай дію не більше 2 хвилин\n• Зроби ковток води або відчини вікно\n• Дозволь собі робити речі на 10% із 100%\n\nЦе вже велика перемога 🌱",
    "loneliness": "Ти не один/одна, навіть якщо зараз здається навпаки.\n\nПрактика співчуття до себе:\n\n1. Поклади долоню на серце або обійми себе\n2. Скажи подумки: «Мені зараз важко. Але я роблю все, що в моїх силах»\n3. Ти заслуговуєш на тепло так само, як і будь-хто інший 💛",
    "anger": "Гнів — це сильна та здорова емоція. Важливо дати йому безпечний вихід.\n\nШвидкі техніки:\n\n🚿 Умийся холодною водою\n📄 Зімни аркуш паперу з усієї сили\n⏸ Правило 10 секунд: глибоко видихни перед відповіддю",
    "lost": "Коли земля тікає з-під ніг — спирайся на теперішній момент.\n\nВправа «Коло контролю»:\n\n❌ Не контролюєш: глобальні події, рішення інших\n✅ Контролюєш: що з'їси, коли ляжеш спати, з ким поговориш\n\nСфокусуйся на одній маленькій дії впродовж 15 хвилин 🧭",
}

user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("😰 Тривога та паніка", callback_data="anxiety")],
        [InlineKeyboardButton("😤 Стрес та перенапруження", callback_data="stress")],
        [InlineKeyboardButton("😴 Проблеми зі сном", callback_data="sleep")],
        [InlineKeyboardButton("😶 Апатія та виснаження", callback_data="apathy")],
        [InlineKeyboardButton("😔 Самотність або провина", callback_data="loneliness")],
        [InlineKeyboardButton("😠 Дратівливість та гнів", callback_data="anger")],
        [InlineKeyboardButton("😵 Втрата опори", callback_data="lost")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Привіт 👋\n\nЯ тут, щоб підтримати тебе. Як ти зараз почуваєшся?",
        reply_markup=reply_markup
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "maksym":
        user_sessions[query.from_user.id] = []
        keyboard = [[InlineKeyboardButton("🏠 Повернутися до меню", callback_data="menu")]]
        await query.message.reply_text(
            "Привіт, я Максим 👋\n\nРозкажи мені що тебе турбує. Я тут, щоб вислухати.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    if query.data == "menu":
        await start_from_callback(query, context)
        return
    
    text = MESSAGES.get(query.data, "")
    keyboard = [
        [InlineKeyboardButton("🤖 Поспілкуватися з Максимом", callback_data="maksym")],
        [InlineKeyboardButton("🏠 Повернутися до меню", callback_data="menu")],
    ]
    await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def start_from_callback(query, context):
    keyboard = [
        [InlineKeyboardButton("😰 Тривога та паніка", callback_data="anxiety")],
        [InlineKeyboardButton("😤 Стрес та перенапруження", callback_data="stress")],
        [InlineKeyboardButton("😴 Проблеми зі сном", callback_data="sleep")],
        [InlineKeyboardButton("😶 Апатія та виснаження", callback_data="apathy")],
        [InlineKeyboardButton("😔 Самотність або провина", callback_data="loneliness")],
        [InlineKeyboardButton("😠 Дратівливість та гнів", callback_data="anger")],
        [InlineKeyboardButton("😵 Втрата опори", callback_data="lost")],
    ]
    await query.message.reply_text(
        "Як ти зараз почуваєшся?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        await start(update, context)
        return
    
    crisis_keywords = ["суїцид", "вбити себе", "не хочу жити", "покінчити з життям", "самогубство"]
    if any(word in update.message.text.lower() for word in crisis_keywords):
        await update.message.reply_text(
            "⚠️ Я бачу, що тобі зараз дуже важко.\n\nБудь ласка, зателефонуй на гарячу лінію:\n📞 7333 — безкоштовно, цілодобово\n\nТи не один/одна. Є люди які готові допомогти прямо зараз."
        )
        return
    
    history = user_sessions.get(user_id, [])
    history.append({"role": "user", "content": update.message.text})
    
    if len(history) > 20:
        history = history[-20:]
    
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ти — Максим, емпатичний психологічний помічник. Спілкуєшся українською мовою. Використовуєш техніки активного слухання, валідуєш емоції користувача. Не ставиш медичних діагнозів і не призначаєш медикаменти. Відповідаєш тепло, коротко і по суті."},
                *history
            ],
            max_tokens=500
        )
        reply = response.choices[0].message.content
        history.append({"role": "assistant", "content": reply})
        user_sessions[user_id] = history
        
        keyboard = [[InlineKeyboardButton("🏠 Повернутися до меню", callback_data="menu")]]
        await update.message.reply_text(reply, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        await update.message.reply_text("Вибач, сталася помилка. Спробуй ще раз.")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
