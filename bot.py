import asyncio
import sqlite3
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import CommandStart
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

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
dp = Dispatcher(storage=MemoryStorage())

# =======================
# DATABASE
# =======================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

def init_db():
    cursor.execute("""CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER,
        items TEXT,
        total REAL,
        address TEXT,
        payment TEXT,
        status TEXT
    )""")
    conn.commit()

# =======================
# STATES
# =======================
class OrderState(StatesGroup):
    waiting_address = State()
    waiting_payment = State()

# =======================
# CART
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
# MENU (ثابت للتبسيط)
# =======================
MENU = [
    ("Burger", 5),
    ("Pizza", 8),
    ("Coke", 2),
    ("Pepsi", 2),
    ("Juice", 3)
]

def main_kb():
    buttons = []
    for i, item in enumerate(MENU):
        buttons.append([InlineKeyboardButton(text=f"{item[0]} - ${item[1]}", callback_data=f"add_{i}")])

    buttons.append([InlineKeyboardButton(text="🛒 Cart", callback_data="cart")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

def cart_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Checkout", callback_data="checkout")],
        [InlineKeyboardButton(text="🗑 Clear", callback_data="clear")]
    ])

def payment_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 Cash", callback_data="pay_cash")],
        [InlineKeyboardButton(text="💳 Card", callback_data="pay_card")]
    ])

# =======================
# START
# =======================
@dp.message(CommandStart())
async def start(message: Message):
    await message.answer("🍔 Welcome! Choose items:", reply_markup=main_kb())

# =======================
# ADD
# =======================
@dp.callback_query(F.data.startswith("add_"))
async def add(cb: CallbackQuery):
    idx = int(cb.data.split("_")[1])
    item = MENU[idx]

    add_to_cart(cb.from_user.id, item[0], item[1])
    await cb.answer("Added ✅")

# =======================
# CART
# =======================
@dp.callback_query(F.data == "cart")
async def show_cart(cb: CallbackQuery):
    user_cart = cart.get(cb.from_user.id, {})

    if not user_cart:
        await cb.message.answer("Cart empty")
        return

    text = "🛒 Cart:\n\n"
    total = 0

    for name, data in user_cart.items():
        subtotal = data["price"] * data["qty"]
        total += subtotal
        text += f"{name} x{data['qty']} = ${subtotal}\n"

    text += f"\n💰 Total: ${total}"

    await cb.message.answer(text, reply_markup=cart_kb())

# =======================
# CLEAR
# =======================
@dp.callback_query(F.data == "clear")
async def clear(cb: CallbackQuery):
    clear_cart(cb.from_user.id)
    await cb.message.answer("Cart cleared")

# =======================
# CHECKOUT → ADDRESS
# =======================
@dp.callback_query(F.data == "checkout")
async def checkout(cb: CallbackQuery, state: FSMContext):
    if not cart.get(cb.from_user.id):
        await cb.answer("Cart empty")
        return

    await state.set_state(OrderState.waiting_address)
    await cb.message.answer("📍 Send your address:")

# =======================
# ADDRESS → PAYMENT
# =======================
@dp.message(OrderState.waiting_address)
async def get_address(message: Message, state: FSMContext):
    await state.update_data(address=message.text)
    await state.set_state(OrderState.waiting_payment)

    await message.answer("💳 Choose payment method:", reply_markup=payment_kb())

# =======================
# PAYMENT → CONFIRM
# =======================
@dp.callback_query(F.data.startswith("pay_"))
async def payment(cb: CallbackQuery, state: FSMContext):
    payment_method = "Cash" if "cash" in cb.data else "Card"
    await state.update_data(payment=payment_method)

    data = await state.get_data()
    user_cart = cart.get(cb.from_user.id, {})

    items_text = "\n".join([f"{k} x{v['qty']}" for k, v in user_cart.items()])
    total = sum(v["price"] * v["qty"] for v in user_cart.values())

    order_text = f"""
🧾 Order Summary:

{items_text}

📍 {data['address']}
💳 {payment_method}
💰 {total}$

Confirm?
"""

    await cb.message.answer(order_text, reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Confirm", callback_data="confirm")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel")]
        ]
    ))

# =======================
# CONFIRM
# =======================
@dp.callback_query(F.data == "confirm")
async def confirm(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_cart = cart.get(cb.from_user.id, {})

    items_text = "\n".join([f"{k} x{v['qty']}" for k, v in user_cart.items()])
    total = sum(v["price"] * v["qty"] for v in user_cart.values())

    cursor.execute(
        "INSERT INTO orders (telegram_id, items, total, address, payment, status) VALUES (?,?,?,?,?,?)",
        (cb.from_user.id, items_text, total, data['address'], data['payment'], "Pending")
    )
    conn.commit()

    order_id = cursor.lastrowid

    admin_msg = f"""
📦 NEW ORDER #{order_id}

👤 User: {cb.from_user.id}

{items_text}

📍 {data['address']}
💳 {data['payment']}
💰 {total}$
"""

    for admin in ADMIN_IDS:
        await bot.send_message(admin, admin_msg)

    clear_cart(cb.from_user.id)
    await state.clear()

    await cb.message.answer(f"✅ Order #{order_id} sent!")

# =======================
# CANCEL
# =======================
@dp.callback_query(F.data == "cancel")
async def cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.answer("❌ Order cancelled")

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
