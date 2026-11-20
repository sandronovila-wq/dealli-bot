import os
import sqlite3
import asyncio
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_PATH = "dealli.db"

if not TOKEN:
    raise RuntimeError("Set BOT_TOKEN environment variable")
if not ADMIN_ID:
    raise RuntimeError("Set ADMIN_ID environment variable")

bot = Bot(TOKEN)
dp = Dispatcher()

def db():
    return sqlite3.connect(DB_PATH)

def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY, joined_at TEXT, notifications INTEGER DEFAULT 1
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS deals(
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, price TEXT, old_price TEXT,
            url TEXT, category TEXT, description TEXT, created_at TEXT
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS requests(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, query TEXT, created_at TEXT
        )""")

def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔥 Выгодные предложения", callback_data="deals")
    kb.button(text="🔎 Найти товар", callback_data="search")
    kb.button(text="🔔 Уведомления", callback_data="notifications")
    kb.button(text="ℹ️ О боте", callback_data="about")
    kb.adjust(1)
    return kb.as_markup()

def deals_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="Все предложения", callback_data="category:all")
    kb.button(text="Техника", callback_data="category:tech")
    kb.button(text="Игры и аксессуары", callback_data="category:gaming")
    kb.button(text="Одежда", callback_data="category:clothes")
    kb.button(text="⬅️ Главное меню", callback_data="home")
    kb.adjust(1)
    return kb.as_markup()

@dp.message(Command("start"))
async def start(message: Message):
    with db() as con:
        con.execute("INSERT OR IGNORE INTO users(user_id, joined_at) VALUES(?,?)",
                   (message.from_user.id, datetime.now().isoformat(timespec="seconds")))
    await message.answer(
        "👋 Привет! Это DEALLI — бот, который помогает находить выгодные покупки.\n\n"
        "Выбирай раздел ниже. Мы не обещаем скидки на всё подряд — только предложения, "
        "которые добавлены в нашу подборку.",
        reply_markup=main_menu()
    )

@dp.callback_query(F.data == "home")
async def home(call: CallbackQuery):
    await call.message.edit_text("Главное меню DEALLI:", reply_markup=main_menu())
    await call.answer()

@dp.callback_query(F.data == "deals")
async def deals(call: Callback):
    await call.message.edit_text("Выбери категорию:", reply_markup=deals_menu())
    await call.answer()

@dp.callback_query(F.data.startswith("category:"))
async def show_category(call: CallbackQuery):
    category = call.data.split(":", 1)[1]
    label = {"all":"все", "tech":"техника", "gaming":"игры и аксессуары", "clothes":"одежда"}.get(category, "все")
    with db() as con:
        if category == "all":
            rows = con.execute("SELECT title,price,old_price,url,description FROM deals ORDER BY id DESC LIMIT 15").fetchall()
        else:
            rows = con.execute("SELECT title,price,old_price,url,description FROM deals WHERE category=? ORDER BY id DESC LIMIT 15", (category,)).fetchall()
    if not rows:
        text = f"Пока предложений в категории «{label}» нет.\n\nСкоро добавим первые находки 👀"
    else:
        chunks = []
        for title, price, old_price, url, description in rows:
            block = f"🛍 <b>{title}</b>\n💰 Цена: <b>{price}</b>"
            if old_price:
                block += f"\nБыло: {old_price}"
            if description:
                block += f"\n{description}"
            if url:
                block += f"\n<a href='{url}'>Открыть предложение</a>"
            chunks.append(block)
        text = "\n\n────────────\n\n".join(chunks)
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Категории", callback_data="deals")
    kb.button(text="🏠 Главное меню", callback_data="home")
    kb.adjust(1)
    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML", disable_web_page_preview=True)
    await call.answer()

@dp.callback_query(F.data == "search")
async def search_start(call: CallbackQuery):
    await call.message.answer("Напиши название товара и, если есть, бюджет.\nНапример: «беспроводные наушники до 30€»")
    await call.answer()

@dp.message(F.text & ~F.text.startswith("/"))
async def handle_search(message: Message):
    query = message.text.strip()
    if len(query) < 2:
        await message.answer("Напиши чуть подробнее, какой товар ищешь.")
        return
    with db() as con:
        con.execute("INSERT INTO requests(user_id,query,created_at) VALUES(?,?,?)",
                   (message.from_user.id, query, datetime.now().isoformat(timespec="seconds")))
    await message.answer("✅ Запрос записан! Когда найдём подходящие варианты, сможем прислать их сюда.")
    try:
        await bot.send_message(ADMIN_ID, f"🔎 Новый запрос от пользователя {message.from_user.id}:\n{query}")
    except Exception:
        pass

@dp.callback_query(F.data == "notifications")
async def notifications(call: CallbackQuery):
    with db() as con:
        row = con.execute("SELECT notifications FROM users WHERE user_id=?", (call.from_user.id,)).fetchone()
        current = row[0] if row else 1
        new_value = 0 if current else 1
        con.execute("INSERT OR IGNORE INTO users(user_id,joined_at) VALUES(?,?)",
                   (call.from_user.id, datetime.now().isoformat(timespec="seconds")))
        con.execute("UPDATE users SET notifications=? WHERE user_id=?", (new_value, call.from_user.id))
    kb = InlineKeyboardBuilder()
    kb.button(text=("🔕 Выключить уведомления" if new_value else "🔔 Включить уведомления"), callback_data="notifications")
    kb.button(text="🏠 Главное меню", callback_data="home")
    kb.adjust(1)
    await call.message.edit_text(
        f"Уведомления о новых предложениях: {'включены ✅' if new_value else 'выключены 💤'}",
        reply_markup=kb.as_markup()
    )
    await call.answer()

@dp.callback_query(F.data == "about")
async def about(call: CallbackQuery):
    await call.message.edit_text(
        "DEALLI помогает находить интересные предложения.\n\n"
        "Цены, наличие и условия покупки проверяй на сайте продавца перед заказом.",
        reply_markup=InlineKeyboardBuilder().button(text="⬅️ Назад", callback_data="home").as_markup()
    )
    await call.answer()

# Admin command:
# /deal category | title | price | old_price | url | description
# category: tech / gaming / clothes / all
@dp.message(Command("deal"))
async def add_deal(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split("|", 5)
    if len(parts) < 6:
        await message.answer(
            "Формат:\n/deal tech | Название | 29€ | 39€ | https://ссылка | Описание\n\n"
            "Категории: tech, gaming, clothes"
        )
        return
    first = parts[0].split(maxsplit=1)
    category = first[1].strip().lower() if len(first) > 1 else "all"
    title, price, old_price, url, description = [p.strip() for p in parts[1:6]]
    with db() as con:
        con.execute("INSERT INTO deals(title,price,old_price,url,category,description,created_at) VALUES(?,?,?,?,?,?,?)",
                   (title, price, old_price, url, category, description, datetime.now().isoformat(timespec="seconds")))
        users = con.execute("SELECT user_id FROM users WHERE notifications=1").fetchall()
    await message.answer(f"✅ Предложение добавлено: {title}")
    # Send new deal to subscribed users
    notification = f"🔥 Новое предложение!\n\n<b>{title}</b>\nЦена: <b>{price}</b>"
    if old_price:
        notification += f"\nБыло: {old_price}"
    if description:
        notification += f"\n{description}"
    if url:
        notification += f"\n<a href='{url}'>Смотреть</a>"
    for (uid,) in users:
        try:
            await bot.send_message(uid, notification, parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            pass

@dp.message(Command("stats"))
async def stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    with db() as con:
        users = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        deals = con.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
        requests = con.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
    await message.answer(f"📊 DEALLI статистика\nПользователей: {users}\nПредложений: {deals}\nЗапросов: {requests}")

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
