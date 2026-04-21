import asyncio
import sqlite3
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = os.getenv("ADMIN_IDS")

if ADMIN_IDS:
    ADMIN_IDS = list(map(int, ADMIN_IDS.split(",")))
else:
    ADMIN_IDS = [550027227]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ================= DB =================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

def init_db():
    cursor.execute("""CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER,
        phone TEXT,
        items TEXT,
        total REAL,
        address TEXT,
        payment TEXT,
        status TEXT
    )""")
    conn.commit()

# ================= STATES =================
class OrderState(StatesGroup):
    phone = State()
    address = State()
    payment = State()

# ================= MENU =================
MENU = {
    "Burgers": [("Burger", 5), ("Double Burger", 7)],
    "Drinks": [("Coke", 2), ("Pepsi", 2), ("Juice", 3)],
    "Desserts": [("Ice Cream", 3), ("Cake", 4)]
}

cart = {}

def add_to_cart(user_id, name, price):
    user_cart = cart.setdefault(user_id, {})
    if name in user_cart:
        user_cart[name]["qty"] += 1
    else:
        user_cart[name] = {"price": price, "qty": 1}

def clear_cart(user_id):
    cart[user_id] = {}

# ================= KEYBOARDS =================
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍽 Menu", callback_data="menu")],
        [InlineKeyboardButton(text="🛒 Cart", callback_data="cart")]
    ])

def categories_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍔 Burgers", callback_data="cat_Burgers")],
        [InlineKeyboardButton(text="🥤 Drinks", callback_data="cat_Drinks")],
        [InlineKeyboardButton(text="🍰 Desserts", callback_data="cat_Desserts")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="back_main")]
    ])

def items_kb(cat):
    buttons = []
    for i, item in enumerate(MENU[cat]):
        buttons.append([
            InlineKeyboardButton(
                text=f"{item[0]} - ${item[1]}",
                callback_data=f"add_{cat}_{i}"
            )
        ])

    buttons.append([InlineKeyboardButton(text="⬅️ Back", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def cart_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Checkout", callback_data="checkout")],
        [InlineKeyboardButton(text="🗑 Clear", callback_data="clear")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="menu")]
    ])

def payment_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 Cash", callback_data="pay_cash")],
        [InlineKeyboardButton(text="💳 Card", callback_data="pay_card")]
    ])

phone_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📱 Send Phone", request_contact=True)]],
    resize_keyboard=True
)

# ================= START =================
@dp.message(CommandStart())
async def start(message: Message):
    await message.answer("🍔 Welcome!", reply_markup=main_kb())

# ================= MENU =================
@dp.callback_query(F.data == "menu")
async def menu(cb: CallbackQuery):
    await cb.message.edit_text("📋 Choose category:", reply_markup=categories_kb())

@dp.callback_query(F.data == "back_main")
async def back(cb: CallbackQuery):
    await cb.message.edit_text("🍔 Welcome!", reply_markup=main_kb())

# ================= CATEGORY =================
@dp.callback_query(F.data.startswith("cat_"))
async def category(cb: CallbackQuery):
    cat = cb.data.split("_")[1]
    await cb.message.edit_text(f"{cat} Menu:", reply_markup=items_kb(cat))

# ================= ADD =================
@dp.callback_query(F.data.startswith("add_"))
async def add(cb: CallbackQuery):
    _, cat, idx = cb.data.split("_")
    item = MENU[cat][int(idx)]

    add_to_cart(cb.from_user.id, item[0], item[1])
    await cb.answer("Added ✅")

# ================= CART =================
@dp.callback_query(F.data == "cart")
async def show_cart(cb: CallbackQuery):
    user_cart = cart.get(cb.from_user.id, {})

    if not user_cart:
        await cb.message.answer("🛒 Cart empty")
        return

    text = "🛒 Cart:\n\n"
    total = 0

    for name, data in user_cart.items():
        subtotal = data["price"] * data["qty"]
        total += subtotal
        text += f"{name} x{data['qty']} = ${subtotal}\n"

    text += f"\n💰 Total: ${total}"

    await cb.message.answer(text, reply_markup=cart_kb())

# ================= CLEAR =================
@dp.callback_query(F.data == "clear")
async def clear(cb: CallbackQuery):
    clear_cart(cb.from_user.id)
    await cb.message.answer("Cart cleared")

# ================= CHECKOUT =================
@dp.callback_query(F.data == "checkout")
async def checkout(cb: CallbackQuery, state: FSMContext):
    if not cart.get(cb.from_user.id):
        await cb.answer("Cart empty")
        return

    await state.set_state(OrderState.phone)
    await cb.message.answer("📱 Send phone number:", reply_markup=phone_kb)

# ================= PHONE =================
@dp.message(OrderState.phone)
async def phone(message: Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else message.text
    await state.update_data(phone=phone)

    await state.set_state(OrderState.address)
    await message.answer("📍 Send your address:")

# ================= ADDRESS =================
@dp.message(OrderState.address)
async def address(message: Message, state: FSMContext):
    await state.update_data(address=message.text)
    await state.set_state(OrderState.payment)

    await message.answer("💳 Payment method:", reply_markup=payment_kb())

# ================= PAYMENT =================
@dp.callback_query(F.data.startswith("pay_"))
async def payment(cb: CallbackQuery, state: FSMContext):
    pay = "Cash" if "cash" in cb.data else "Card"
    await state.update_data(payment=pay)

    data = await state.get_data()
    user_cart = cart.get(cb.from_user.id, {})

    items_text = "\n".join([f"{k} x{v['qty']}" for k, v in user_cart.items()])
    total = sum(v["price"] * v["qty"] for v in user_cart.values())

    await cb.message.answer(
        f"{items_text}\n\n📱 {data['phone']}\n📍 {data['address']}\n💳 {pay}\n💰 {total}$\n\nConfirm?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Confirm", callback_data="confirm")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel")]
        ])
    )

# ================= CONFIRM =================
@dp.callback_query(F.data == "confirm")
async def confirm(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_cart = cart.get(cb.from_user.id, {})

    items_text = "\n".join([f"{k} x{v['qty']}" for k, v in user_cart.items()])
    total = sum(v["price"] * v["qty"] for v in user_cart.values())

    cursor.execute(
        "INSERT INTO orders (telegram_id, phone, items, total, address, payment, status) VALUES (?,?,?,?,?,?,?)",
        (cb.from_user.id, data['phone'], items_text, total, data['address'], data['payment'], "Pending")
    )
    conn.commit()

    order_id = cursor.lastrowid

    username = cb.from_user.username
    name = cb.from_user.full_name

    user_info = f"{name}"
    if username:
        user_info += f" (@{username})"

    admin_msg = f"""
📦 ORDER #{order_id}

👤 {user_info}
📱 {data['phone']}

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

# ================= MAIN =================
async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
