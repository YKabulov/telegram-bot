import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    Filters,
    ContextTypes,
)
from dotenv import load_dotenv
import os
import logging
from aiohttp import web

# .env faylidan ma'lumotlarni o'qish
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# Logging sozlamalari
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# SQLite ma'lumotlar bazasini sozlash
def init_db():
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS movies
                 (code TEXT PRIMARY KEY, message_id INTEGER, download_count INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, is_subscribed INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

# Kanalga obuna bo'lganligini tekshirish
async def check_subscription(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"Obuna tekshirishda xato: {e}")
        return False

# Foydalanuvchi obuna bo'lganligini saqlash
def save_user_subscription(user_id: int, is_subscribed: int):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, is_subscribed) VALUES (?, ?)",
              (user_id, is_subscribed))
    conn.commit()
    conn.close()

# /start buyrug'i
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_subscribed = await check_subscription(context, user_id)

    if is_subscribed:
        save_user_subscription(user_id, 1)
        await update.message.reply_text(
            "Salom! Siz @wwkino_b kanaliga obuna bo'lgansiz. 🎉 "
            "Film kodini yuboring (masalan, 15), shu kod ostidagi filmni yuboramiz!"
        )
    else:
        save_user_subscription(user_id, 0)
        keyboard = [
            [InlineKeyboardButton("Kanalga obuna bo‘lish", url=f"https://t.me/{CHANNEL_ID[1:]}")],
            [InlineKeyboardButton("Obuna bo‘ldim", callback_data="check_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Iltimos, avval @wwkino_b kanaliga obuna bo‘ling! Keyin 'Obuna bo‘ldim' tugmasini bosing.",
            reply_markup=reply_markup
        )

# Obuna bo'lganligini tekshirish tugmasi
async def check_subscription_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    is_subscribed = await check_subscription(context, user_id)

    if is_subscribed:
        save_user_subscription(user_id, 1)
        await query.message.edit_text(
            "Obuna tasdiqlandi! 🎉 Endi film kodini yuboring (masalan, 15)."
        )
    else:
        await query.message.edit_text(
            "Siz hali @wwkino_b kanaliga obuna bo‘lmagansiz. Iltimos, obuna bo‘ling va qayta urinib ko‘ring.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Kanalga obuna bo‘lish", url=f"https://t.me/{CHANNEL_ID[1:]}")],
                [InlineKeyboardButton("Obuna bo‘ldim", callback_data="check_subscription")]
            ])
        )

# Film qo'shish (/add)
async def add_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("Bu buyruq faqat admin uchun! 🚫")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Iltimos, /add <kod> <xabar_id> formatida yozing. Masalan: /add 15 12345")
        return

    code, message_id = context.args
    try:
        message_id = int(message_id)
        conn = sqlite3.connect("bot.db")
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO movies (code, message_id, download_count) VALUES (?, ?, 0)",
                  (code, message_id))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"Film {code} kodi bilan qo‘shildi! ✅")
    except ValueError:
        await update.message.reply_text("Xabar ID raqam bo‘lishi kerak! 🚫")
    except Exception as e:
        logger.error(f"Film qo‘shishda xato: {e}")
        await update.message.reply_text("Xatolik yuz berdi, qayta urinib ko‘ring. 🚫")

# Film yuborish
async def send_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_subscribed = await check_subscription(context, user_id)

    if not is_subscribed:
        keyboard = [
            [InlineKeyboardButton("Kanalga obuna bo‘lish", url=f"https://t.me/{CHANNEL_ID[1:]}")],
            [InlineKeyboardButton("Obuna bo‘ldim", callback_data="check_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Iltimos, avval @wwkino_b kanaliga obuna bo‘ling! Keyin 'Obuna bo‘ldim' tugmasini bosing.",
            reply_markup=reply_markup
        )
        return

    code = update.message.text.strip()
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT message_id, download_count FROM movies WHERE code = ?", (code,))
    result = c.fetchone()

    if result:
        message_id, download_count = result
        try:
            await context.bot.forward_message(
                chat_id=user_id,
                from_chat_id=CHANNEL_ID,
                message_id=message_id
            )
            c.execute("UPDATE movies SET download_count = download_count + 1 WHERE code = ?", (code,))
            conn.commit()
            await update.message.reply_text(f"{code} kodi ostidagi film yuborildi! 🎥")
        except Exception as e:
            logger.error(f"Film yuborishda xato: {e}")
            await update.message.reply_text("Film yuborishda xatolik yuz berdi. 🚫")
    else:
        await update.message.reply_text("Bunday kod topilmadi. Iltimos, to‘g‘ri kod yuboring. 🚫")
    conn.close()

# Statistika (/stats)
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("Bu buyruq faqat admin uchun! 🚫")
        return

    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT code, download_count FROM movies ORDER BY download_count DESC")
    results = c.fetchall()
    conn.close()

    if not results:
        await update.message.reply_text("Hozircha hech qanday statistika yo‘q. 🚫")
        return

    message = "📊 Film statistikasi:\n\n"
    for code, count in results:
        message += f"Kod: {code}, Yuklashlar: {count} marta\n"
    await update.message.reply_text(message)

# Xato xabarlari uchun handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Xato yuz berdi: {context.error}")
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"Xato: {context.error}"
    )
    if update and update.message:
        await update.message.reply_text("Xatolik yuz berdi, iltimos qayta urinib ko‘ring. 🚫")

# Webhook uchun handler
async def webhook(request):
    app = request.app['bot']
    update = Update.de_json(await request.json(), app.bot)
    await app.process_update(update)
    return web.Response()

async def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Buyruqlar va handler'lar
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_movie))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(check_subscription_button, pattern="check_subscription"))
    app.add_handler(MessageHandler(Filters.text & ~Filters.command, send_movie))
    app.add_error_handler(error_handler)

    # Web server
    web_app = web.Application()
    web_app['bot'] = app
    web_app.router.add_post('/webhook', webhook)

    # Webhook sozlamasi
    webhook_url = os.getenv("WEBHOOK_URL")  # Render'dan olinadigan URL
    await app.bot.set_webhook(url=webhook_url)

    # Web serverni ishga tushirish
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    logger.info("Webhook server ishga tushdi! 🚀")

    # Botni doimiy ishlashda ushlab turish
    while True:
        await asyncio.sleep(3600)  # 1 soat kutish

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())