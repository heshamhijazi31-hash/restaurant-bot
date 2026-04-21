import asyncio
import sqlite3
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import CommandStart

# =======================
# CONFIG
# =======================

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = os.getenv("ADMIN_IDS")

if ADMIN_IDS:
    ADMIN_IDS = list(map(int, ADMIN_IDS.split(",")))
else:
    ADMIN_IDS = [550027227]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# =======================
# DATABASE
# =======================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

def init_db():
    cursor.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE
    )""")

    cursor.execute("""CREATE TABLE IF NOT EXISTS menu (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        description TEXT,
        price REAL,
        category TEXT
    )""")

    cursor.execute("""CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER,
        items TEXT,
        total REAL,
        status TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")

    cursor.execute("SELECT COUNT(*) FROM menu")
    if cursor.fetchone()[0] == 0:
        sample = [
            ("Cheeseburger", "Juicy beef burger", 5.5, "Burgers"),
            ("Pepperoni Pizza", "Classic pizza", 8.0, "Pizza"),
            ("Coke", "Cold drink", 2.0, "Drinks"),
            ("Ice Cream", "Sweet dessert", 3.5, "Desserts"),
        ]
        cursor.executemany(
            "INSERT INTO menu (name, description, price, category) VALUES (?,?,?,?)",
            sample
        )

    conn.commit()

# =======================
# CART
# =======================
cart = {}

def add_to_cart(user_id, item):
    cart.setdefault(user_id, []).append(item)

def get_cart(user_id):
    return cart.get(user_id, [])

def clear_cart(user_id):
    cart[user_id] = []

# =======================
# KEYBOARDS
# =======================
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍽 View Menu", callback_data="menu")]
    ])

def categories_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍔 Burgers", callback_data="cat_Burgers"),
         InlineKeyboardButton(text="🍕 Pizza", callback_data="cat_Pizza")],
        [InlineKeyboardButton(text="🥤 Drinks", callback_data="cat_Drinks"),
         InlineKeyboardButton(text="🍰 Desserts", callback_data="cat_Desserts")]
    ])

def item_kb(item_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Add", callback_data=f"add_{item_id}")]
    ])

def cart_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Checkout", callback_data="checkout")],
        [InlineKeyboardButton(text="🗑 Clear", callback_data="clear")]
    ])

# =======================
# START
# =======================
@dp.message(CommandStart())
async def start(message: Message):
    cursor.execute("INSERT OR IGNORE INTO users (telegram_id) VALUES (?)", (message.from_user.id,))
    conn.commit()

    await message.answer("👋 Welcome!", reply_markup=main_kb())

# =======================
# MENU
# =======================
@dp.callback_query(F.data == "menu")
async def menu(cb: CallbackQuery):
    await cb.message.edit_text("📋 Choose category:", reply_markup=categories_kb())

@dp.callback_query(F.data.startswith("cat_"))
async def show_items(cb: CallbackQuery):
    cat = cb.data.split("_")[1]

    cursor.execute("SELECT * FROM menu WHERE category=?", (cat,))
    items = cursor.fetchall()

    for item in items:
        text = f"🍽 {item[1]}\n💵 ${item[3]}\n{item[2]}"
        await cb.message.answer(text, reply_markup=item_kb(item[0]))

# =======================
# ADD
# =======================
@dp.callback_query(F.data.startswith("add_"))
async def add(cb: CallbackQuery):
    item_id = int(cb.data.split("_")[1])

    cursor.execute("SELECT name, price FROM menu WHERE id=?", (item_id,))
    item = cursor.fetchone()

    if item:
        add_to_cart(cb.from_user.id, item)
        await cb.answer("Added ✅")

# =======================
# CART
# =======================
@dp.message(F.text == "/cart")
async def show_cart(message: Message):
    items = get_cart(message.from_user.id)

    if not items:
        await message.answer("Cart empty")
        return

    text = "🛒 Cart:\n\n"
    total = sum(i[1] for i in items)

    for i in items:
        text += f"{i[0]} - ${i[1]}\n"

    text += f"\nTotal: ${total}"

    await message.answer(text, reply_markup=cart_kb())

# =======================
# CHECKOUT
# =======================
@dp.callback_query(F.data == "checkout")
async def checkout(cb: CallbackQuery):
    items = get_cart(cb.from_user.id)

    if not items:
        await cb.answer("Cart empty")
        return

    total = sum(i[1] for i in items)
    items_text = ", ".join([i[0] for i in items])

    cursor.execute(
        "INSERT INTO orders (telegram_id, items, total, status) VALUES (?,?,?,?)",
        (cb.from_user.id, items_text, total, "Pending")
    )
    conn.commit()

    clear_cart(cb.from_user.id)

    await cb.message.answer(f"✅ Order placed\n💰 {total}$")

# =======================
# MAIN
# =======================
async def main():
    init_db()

    if not BOT_TOKEN:
        print("Missing BOT_TOKEN")
        return

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())