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

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# =======================
# DATABASE
# =======================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

def init_db():
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
        status TEXT
    )""")

    cursor.execute("SELECT COUNT(*) FROM menu")
    if cursor.fetchone()[0] == 0:
        sample = [
            ("Cheeseburger", "Juicy burger", 5.5, "Burgers"),
            ("Pizza", "Hot pizza", 8.0, "Pizza"),
            ("Coke", "Cold drink", 2.0, "Drinks"),
            ("Ice Cream", "Dessert", 3.5, "Desserts"),
        ]
        cursor.executemany(
            "INSERT INTO menu (name, description, price, category) VALUES (?,?,?,?)",
            sample
        )

    conn.commit()

# =======================
# CART (with quantity)
# =======================
cart = {}

def add_to_cart(user_id, name, price):
    user_cart = cart.setdefault(user_id, {})
    if name in user_cart:
        user_cart[name]["qty"] += 1
    else:
        user_cart[name] = {"price": price, "qty": 1}

def clear_cart(user_id):
    cart[user_id] = {}

# =======================
# KEYBOARDS
# =======================
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍽 View Menu", callback_data="menu")]
    ])

def categories_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍔 Burgers", callback_data="cat_Burgers")],
        [InlineKeyboardButton(text="🍕 Pizza", callback_data="cat_Pizza")],
        [InlineKeyboardButton(text="🥤 Drinks", callback_data="cat_Drinks")],
        [InlineKeyboardButton(text="🍰 Desserts", callback_data="cat_Desserts")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="back_main")]
    ])

def item_kb(item_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Add", callback_data=f"add_{item_id}")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="menu")]
    ])

def cart_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Checkout", callback_data="checkout")],
        [InlineKeyboardButton(text="🗑 Clear", callback_data="clear")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="menu")]
    ])

def confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Confirm", callback_data="confirm")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="menu")]
    ])

# =======================
# START
# =======================
@dp.message(CommandStart())
async def start(message: Message):
    await message.answer("👋 Welcome!", reply_markup=main_kb())

# =======================
# MENU
# =======================
@dp.callback_query(F.data == "menu")
async def menu(cb: CallbackQuery):
    await cb.message.edit_text("📋 Choose category:", reply_markup=categories_kb())

@dp.callback_query(F.data == "back_main")
async def back_main(cb: CallbackQuery):
    await cb.message.edit_text("👋 Welcome!", reply_markup=main_kb())

# =======================
# SHOW ITEMS
# =======================
@dp.callback_query(F.data.startswith("cat_"))
async def show_items(cb: CallbackQuery):
    cat = cb.data.split("_")[1]

    cursor.execute("SELECT * FROM menu WHERE category=?", (cat,))
    items = cursor.fetchall()

    if not items:
        await cb.message.answer("No items.")
        return

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
        add_to_cart(cb.from_user.id, item[0], item[1])
        await cb.answer("Added ✅")

# =======================
# CART
# =======================
@dp.message(F.text == "/cart")
async def show_cart(message: Message):
    user_cart = cart.get(message.from_user.id, {})

    if not user_cart:
        await message.answer("🛒 Cart is empty")
        return

    text = "🛒 Your Cart:\n\n"
    total = 0

    for name, data in user_cart.items():
        subtotal = data["price"] * data["qty"]
        total += subtotal
        text += f"{name} x{data['qty']} = ${subtotal}\n"

    text += f"\n💰 Total: ${total}"

    await message.answer(text, reply_markup=cart_kb())

# =======================
# CLEAR
# =======================
@dp.callback_query(F.data == "clear")
async def clear(cb: CallbackQuery):
    clear_cart(cb.from_user.id)
    await cb.message.answer("Cart cleared 🗑")

# =======================
# CHECKOUT
# =======================
@dp.callback_query(F.data == "checkout")
async def checkout(cb: CallbackQuery):
    user_cart = cart.get(cb.from_user.id, {})

    if not user_cart:
        await cb.answer("Cart empty")
        return

    total = sum(v["price"] * v["qty"] for v in user_cart.values())

    await cb.message.answer(
        f"💰 Total: ${total}\n\nConfirm order?",
        reply_markup=confirm_kb()
    )

# =======================
# CONFIRM
# =======================
@dp.callback_query(F.data == "confirm")
async def confirm(cb: CallbackQuery):
    user_cart = cart.get(cb.from_user.id, {})

    items_text = ", ".join([f"{k} x{v['qty']}" for k, v in user_cart.items()])
    total = sum(v["price"] * v["qty"] for v in user_cart.values())

    cursor.execute(
        "INSERT INTO orders (telegram_id, items, total, status) VALUES (?,?,?,?)",
        (cb.from_user.id, items_text, total, "Pending")
    )
    conn.commit()

    clear_cart(cb.from_user.id)

    await cb.message.answer("✅ Order confirmed!")

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
    
