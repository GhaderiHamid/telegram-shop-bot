import json
import bcrypt
import os
import logging
import requests
import jdatetime
from dotenv import load_dotenv
from flask import Flask, request
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
import mysql.connector

# بارگذاری متغیرهای محیطی
load_dotenv()
TOKEN = os.environ["TOKEN"]
DB_HOST = os.environ["DB_HOST"]
DB_PORT = int(os.environ.get("DB_PORT", 3306))
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]
DB_NAME = os.environ["DB_NAME"]
RENDER_URL = os.environ["RENDER_URL"]

# تنظیم لاگر
logging.basicConfig(level=logging.INFO)

# اتصال به دیتابیس
db = mysql.connector.connect(
    host=DB_HOST,
    port=DB_PORT,
    user=DB_USER,
    password=DB_PASSWORD,
    database=DB_NAME
)
cursor = db.cursor()

# اپلیکیشن تلگرام
application = ApplicationBuilder().token(TOKEN).build()

# ------------------- توابع بات -------------------






# حالت‌ها برای تعامل کاربر
STATES = {
    'AWAITING_EMAIL': 1,
    'AWAITING_PASSWORD': 2,
    'AWAITING_FIRST_NAME': 3,
    'AWAITING_LAST_NAME': 4,
    'AWAITING_PHONE': 5
}

# هش کردن رمز عبور
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

# بررسی تطابق رمز عبور
def check_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

# فرمت قیمت
def format_price(price):
    return "{:,}".format(int(price))
# شروع فرآیند login/register
async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("ورود", callback_data='login')],
        [InlineKeyboardButton("ثبت‌نام", callback_data='register')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("لطفا انتخاب کنید:", reply_markup=reply_markup)

# کلیک روی دکمه‌های ورود یا ثبت‌نام
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'login':
        await query.message.reply_text('لطفا نام کاربری خود را وارد کنید:')
        context.user_data['state'] = STATES['AWAITING_EMAIL']
        context.user_data['action'] = 'login'

    elif query.data == 'register':
        await query.message.reply_text('لطفا نام خود را وارد کنید:')
        context.user_data['state'] = STATES['AWAITING_FIRST_NAME']
        context.user_data['action'] = 'register'

# پردازش پیام‌های متنی کاربر (فرآیند login و register مرحله‌ای)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state = context.user_data.get('state')
    user_action = context.user_data.get('action')
    text = update.message.text

    if user_action == 'login':
        if user_state == STATES['AWAITING_EMAIL']:
            context.user_data['email'] = text
            await update.message.reply_text('لطفا رمز عبور خود را وارد کنید:')
            context.user_data['state'] = STATES['AWAITING_PASSWORD']

        elif user_state == STATES['AWAITING_PASSWORD']:
            email = context.user_data['email']
            password = text
            cursor.execute("SELECT password FROM users WHERE email = %s", (email,))
            result = cursor.fetchone()

            if result and check_password(password, result[0]):
                await update.message.reply_text('✅ ورود موفقیت‌آمیز بود!')
                context.user_data['logged_in'] = True
                context.user_data['user_email'] = email
            else:
                await update.message.reply_text('❌ ایمیل یا رمز عبور اشتباه است!')

            context.user_data.pop('state', None)
            context.user_data.pop('action', None)
            context.user_data.pop('password', None)
            context.user_data.pop('email', None)

    elif user_action == 'register':
        if user_state == STATES['AWAITING_FIRST_NAME']:
            context.user_data['first_name'] = text
            await update.message.reply_text('لطفا نام خانوادگی خود را وارد کنید:')
            context.user_data['state'] = STATES['AWAITING_LAST_NAME']

        elif user_state == STATES['AWAITING_LAST_NAME']:
            context.user_data['last_name'] = text
            await update.message.reply_text('لطفا ایمیل خود را وارد کنید:')
            context.user_data['state'] = STATES['AWAITING_EMAIL']

        elif user_state == STATES['AWAITING_EMAIL']:
            context.user_data['email'] = text
            await update.message.reply_text('لطفا رمز عبور خود را وارد کنید:')
            context.user_data['state'] = STATES['AWAITING_PASSWORD']

        elif user_state == STATES['AWAITING_PASSWORD']:
            context.user_data['password'] = text
            await update.message.reply_text('لطفا شماره تلفن خود را وارد کنید:')
            context.user_data['state'] = STATES['AWAITING_PHONE']

        elif user_state == STATES['AWAITING_PHONE']:
            context.user_data['phone'] = text
            first_name = context.user_data['first_name']
            last_name = context.user_data['last_name']
            email = context.user_data['email']
            password = hash_password(context.user_data['password'])
            phone = context.user_data['phone']

            cursor.execute(
                "INSERT INTO users (first_name, last_name, email, password, phone) VALUES (%s, %s, %s, %s, %s)",
                (first_name, last_name, email, password, phone)
            )
            db.commit()

            await update.message.reply_text('✅ ثبت‌نام موفقیت‌آمیز بود!')
            context.user_data.clear()
# نمایش دسته‌بندی محصولات
async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT id, category_name FROM categories")
    results = cursor.fetchall()

    if results:
        buttons, row = [], []
        for i, (cat_id, name) in enumerate(results, 1):
            row.append(InlineKeyboardButton(name, callback_data=f"categoryid_{cat_id}"))
            if i % 4 == 0:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        reply_markup = InlineKeyboardMarkup(buttons)
        await update.message.reply_text("📚 لطفاً یک دسته‌بندی را انتخاب کن:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("❌ هیچ دسته‌ای پیدا نشد.")

# کلیک روی دسته و نمایش محصولات
async def show_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    category_id = int(query.data.replace("categoryid_", ""))
    context.user_data['category_id'] = category_id
    context.user_data['product_offset'] = 0
    await send_product_page(update, context, page=0)

# نمایش ۴ محصول در هر صفحه
async def send_product_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int):
    category_id = context.user_data['category_id']
    offset = page * 4

    cursor.execute("""
        SELECT id, name, description, image_path, price, discount, quntity 
        FROM products 
        WHERE category_id = %s 
        LIMIT 4 OFFSET %s
    """, (category_id, offset))
    products = cursor.fetchall()

    if not products:
        await update.effective_chat.send_message("❌ هیچ محصولی در این دسته یافت نشد.")
        return

    for product in products:
        prod_id, name, desc, image_path, price, discount, quntity = product
        final_price = int(price * (1 - discount / 100))
        caption = (
            f"🛍 {name}\n📄 {desc}\n💰 قیمت اصلی: {format_price(price)} تومان\n"
            f"🎯 تخفیف: {discount}%\n💵 قیمت نهایی: {format_price(final_price)} تومان\n"
        )

        if quntity == 0:
            caption += "❌ موجودی نداره"
            product_buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐ افزودن به علاقه‌مندی‌ها", callback_data=f"bookmark_{prod_id}")]
            ])
        else:
            product_buttons = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⭐ علاقه‌مندی", callback_data=f"bookmark_{prod_id}"),
                    InlineKeyboardButton("🛒 افزودن به سبد خرید", callback_data=f"addcart_{prod_id}")
                ]
            ])

        image_full_path = os.path.join("public", image_path)
        try:
            with open(image_full_path, 'rb') as img:
                await update.effective_chat.send_photo(photo=img, caption=caption, reply_markup=product_buttons)
        except FileNotFoundError:
            await update.effective_chat.send_message(f"🚫 تصویر {image_path} پیدا نشد.", reply_markup=product_buttons)

    cursor.execute("SELECT COUNT(*) FROM products WHERE category_id = %s", (category_id,))
    total_products = cursor.fetchone()[0]
    current_page_count = offset + len(products)

    nav_buttons = []
    if current_page_count < total_products:
        nav_buttons.append(InlineKeyboardButton("بعدی ⏩", callback_data="next_page"))
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⏪ قبلی", callback_data="prev_page"))

    if nav_buttons:
        reply_markup = InlineKeyboardMarkup([nav_buttons])
        await update.effective_chat.send_message("📦 صفحه محصولات:", reply_markup=reply_markup)

# هندلر صفحه بعدی/قبلی
async def pagination_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    page = context.user_data.get('product_offset', 0)
    if query.data == "next_page":
        page += 1
    elif query.data == "prev_page" and page > 0:
        page -= 1

    context.user_data['product_offset'] = page
    await send_product_page(update, context, page)
# جستجوی محصول
async def search_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ لطفاً یک عبارت برای جستجو وارد کنید.\nمثال: `/search گوشی`")
        return

    search_query = f"%{' '.join(context.args)}%"

    cursor.execute("""
        SELECT id, name, brand, description, image_path, price, discount 
        FROM products 
        WHERE name LIKE %s OR brand LIKE %s OR description LIKE %s 
        LIMIT 5
    """, (search_query, search_query, search_query))

    products = cursor.fetchall()

    if not products:
        await update.message.reply_text("❌ محصولی با این مشخصات یافت نشد.")
        return

    for product in products:
        prod_id, name, brand, desc, image_path, price, discount = product
        final_price = int(price * (1 - discount / 100))
        caption = (
            f"🛍 {name} ({brand})\n📄 {desc}\n💰 قیمت: {format_price(price)} تومان\n"
            f"🎯 تخفیف: {discount}%\n✅ نهایی: {format_price(final_price)} تومان"
        )
        image_full_path = f"public/{image_path}"

        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⭐ علاقه‌مندی", callback_data=f"bookmark_{prod_id}"),
                InlineKeyboardButton("🛒 افزودن به سبد", callback_data=f"addcart_{prod_id}")
            ]
        ])

        try:
            with open(image_full_path, 'rb') as img:
                await update.message.reply_photo(photo=img, caption=caption, reply_markup=buttons)
        except FileNotFoundError:
            await update.message.reply_text(f"{name}\n🚫 تصویر یافت نشد.", reply_markup=buttons)

# افزودن به علاقه‌مندی‌ها
async def add_bookmark_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prod_id = int(query.data.replace("bookmark_", ""))

    if not context.user_data.get('logged_in'):
        await query.message.reply_text("❗ ابتدا وارد شوید.")
        return

    email = context.user_data['user_email']
    cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()
    if not user:
        await query.message.reply_text("❗ کاربر یافت نشد.")
        return

    user_id = user[0]
    cursor.execute("SELECT 1 FROM bookmarks WHERE user_id = %s AND product_id = %s", (user_id, prod_id))
    if cursor.fetchone():
        await query.message.reply_text("⭐ قبلاً به علاقه‌مندی افزوده شده.")
    else:
        cursor.execute("INSERT INTO bookmarks (user_id, product_id) VALUES (%s, %s)", (user_id, prod_id))
        db.commit()
        await query.message.reply_text("✅ به علاقه‌مندی‌ها افزوده شد.")

# افزودن به سبد خرید
async def add_to_cart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prod_id = int(query.data.replace("addcart_", ""))

    if not context.user_data.get('logged_in'):
        await query.message.reply_text("❗ ابتدا وارد شوید.")
        return

    cart = context.user_data.get('cart', {})
    cart[prod_id] = cart.get(prod_id, 0) + 1
    context.user_data['cart'] = cart
    await query.message.reply_text("🛒 به سبد خرید افزوده شد.")

# نمایش سبد خرید
async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('logged_in'):
        await update.message.reply_text("❗ برای مشاهده سبد خرید وارد شوید.")
        return

    cart = context.user_data.get('cart', {})
    if not cart:
        await update.message.reply_text("🛒 سبد خرید شما خالی است.")
        return

    total = 0
    for prod_id, qty in cart.items():
        cursor.execute("SELECT name, price, discount, image_path FROM products WHERE id = %s", (prod_id,))
        row = cursor.fetchone()
        if not row:
            continue
        name, price, discount, image_path = row
        final_price = int(price * (1 - discount / 100))
        subtotal = final_price * qty
        total += subtotal

        caption = (
            f"🛍 {name}\n"
            f"تعداد: {qty}\n"
            f"قیمت واحد: {format_price(final_price)} تومان\n"
            f"جمع: {format_price(subtotal)} تومان"
        )

        try:
            with open(f"public/{image_path}", "rb") as img:
                await update.message.reply_photo(photo=img, caption=caption)
        except:
            await update.message.reply_text(caption + "\n🚫 تصویر یافت نشد.")

    pay_button = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 پرداخت", callback_data="pay_cart")]
    ])
    await update.message.reply_text(f"💵 مجموع کل: {format_price(total)} تومان", reply_markup=pay_button)

# هندلر پرداخت
async def pay_cart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not context.user_data.get('logged_in'):
        await query.message.reply_text("❗ ابتدا وارد شوید.")
        return

    cart = context.user_data.get('cart', {})
    if not cart:
        await query.message.reply_text("🛒 سبد خرید خالی است.")
        return

    email = context.user_data['user_email']
    cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()
    if not user:
        await query.message.reply_text("❌ خطا در شناسایی کاربر.")
        return
    user_id = user[0]

    products = []
    subtotal = 0
    for prod_id, qty in cart.items():
        cursor.execute("SELECT price, discount FROM products WHERE id = %s", (prod_id,))
        p = cursor.fetchone()
        if not p: continue
        price, discount = p
        final_price = int(price * (1 - discount / 100))
        subtotal += final_price * qty
        products.append({
            "product_id": prod_id,
            "price": int(price),
            "discount": int(discount),
            "quantity": qty
        })

    try:
        response = requests.post(
            "https://hamidstore.liara.run/payment",
            headers={'Content-Type': 'application/json'},
            json={
                "user_id": user_id,
                "subtotal": int(subtotal),
                "products": products
            }
        )
        res_json = response.json()
        if response.status_code == 200 and res_json.get("success"):
            payment_url = res_json.get("payment_url")
            button = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 مشاهده صفحه پرداخت", url=payment_url)]
            ])
            await query.message.reply_text("برای پرداخت روی دکمه زیر کلیک کنید:", reply_markup=button)
        else:
            await query.message.reply_text("❌ خطا در پاسخ سرور پرداخت.")
    except Exception as e:
        await query.message.reply_text(f"❌ اتصال به سرور پرداخت ناموفق بود.\n{str(e)}")

# نمایش سفارش‌ها و محصولات خریداری شده
async def show_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('logged_in'):
        await update.message.reply_text("❗ ابتدا وارد شوید.")
        return

    context.user_data['orders_page'] = 0
    await send_orders_page(update, context, page=0)

# نمایش سفارش‌های کاربر با جزئیات
async def send_orders_page(update, context, page: int):
    email = context.user_data.get('user_email')
    cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()
    if not user:
        await update.message.reply_text("❌ کاربر یافت نشد.")
        return
    user_id = user[0]

    cursor.execute("SELECT id, status, created_at FROM orders WHERE user_id = %s ORDER BY id DESC", (user_id,))
    orders = cursor.fetchall()
    if not orders:
        await update.message.reply_text("📦 هیچ سفارشی ثبت نشده.")
        return

    page_size = 4
    start = page * page_size
    end = start + page_size
    orders_page = orders[start:end]

    status_map = {
        "processing": "در حال پردازش",
        "shipped": "ارسال شده",
        "delivered": "تحویل‌شده",
        "returned": "مرجوع شده"
    }

    for order_id, status, created_at in orders_page:
        status_fa = status_map.get(str(status).lower(), status)
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        created_jalali = jdatetime.datetime.fromgregorian(datetime=created_at).strftime("%Y/%m/%d ساعت %H:%M")

        msg = f"🧾 سفارش #{order_id}\nتاریخ ثبت: {created_jalali}\nوضعیت: {status_fa}\n"

        cursor.execute("""
            SELECT od.product_id, od.quantity, od.price, p.name, p.image_path
            FROM order_details od
            JOIN products p ON od.product_id = p.id
            WHERE od.order_id = %s
        """, (order_id,))
        details = cursor.fetchall()
        total = 0
        lines = []
        images = []

        for pid, qty, price, name, img in details:
            total += price * qty
            lines.append(f"🔸 {name}\nتعداد: {qty}\nقیمت: {format_price(price)}\nجمع: {format_price(price * qty)}")
            images.append({"prod_id": pid, "name": name, "image_path": img})

        msg += "\n" + "\n".join(lines) + f"\n💰 مجموع کل: {format_price(total)} تومان"
        button = InlineKeyboardMarkup([
            [InlineKeyboardButton("📷 تصاویر محصولات", callback_data=f"orderimgs_{order_id}")]
        ])
        context.user_data.setdefault('order_images', {})[str(order_id)] = images
        await update.effective_chat.send_message(msg, reply_markup=button)

    nav_btns = []
    if end < len(orders):
        nav_btns.append(InlineKeyboardButton("بعدی ⏩", callback_data="orders_next_page"))
    if page > 0:
        nav_btns.append(InlineKeyboardButton("⏪ قبلی", callback_data="orders_prev_page"))
    if nav_btns:
        await update.effective_chat.send_message("📑 صفحه سفارش‌ها:", reply_markup=InlineKeyboardMarkup([nav_btns]))

# هندلر صفحه‌بندی سفارش‌ها
async def orders_pagination_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    page = context.user_data.get('orders_page', 0)
    if query.data == "orders_next_page":
        page += 1
    elif query.data == "orders_prev_page" and page > 0:
        page -= 1
    context.user_data['orders_page'] = page
    await send_orders_page(update, context, page)

# هندلر حذف محصول از سبد خرید
async def remove_from_cart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not context.user_data.get('logged_in'):
        await query.message.reply_text("❗ ابتدا وارد شوید.")
        return

    prod_id = int(query.data.replace("remove_cart_", ""))
    cart = context.user_data.get('cart', {})
    
    if prod_id in cart:
        cart.pop(prod_id)
        context.user_data['cart'] = cart
        await query.message.reply_text("✅ محصول از سبد خرید حذف شد.")
    else:
        await query.message.reply_text("❗ این محصول در سبد خرید شما نیست.")

    # نمایش مجدد سبد خرید
    class DummyMessage:
        def __init__(self, chat, from_user):
            self.chat = chat
            self.from_user = from_user
        async def reply_text(self, *args, **kwargs):
            await query.message.reply_text(*args, **kwargs)
        async def reply_photo(self, *args, **kwargs):
            await query.message.reply_photo(*args, **kwargs)

    dummy_update = Update(update.update_id, message=DummyMessage(query.message.chat, query.from_user))
    await show_cart(dummy_update, context)

# نمایش تصاویر محصولات سفارش
async def order_images_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    try:
        _, order_id = data.split("_")
    except Exception:
        await query.message.reply_text("❌ خطا در دریافت اطلاعات سفارش.")
        return

    order_images = context.user_data.get('order_images', {})
    images = order_images.get(str(order_id))
    if not images:
        await query.message.reply_text("❌ تصویر محصولات سفارش یافت نشد.")
        return

    for item in images:
        name = item["name"]
        image_path = item["image_path"]
        image_full_path = f"public/{image_path}"
        try:
            with open(image_full_path, 'rb') as img:
                await query.message.reply_photo(photo=img, caption=name)
        except:
            await query.message.reply_text(f"{name}\n🚫 تصویر یافت نشد.")

# منوی شروع
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("ورود / ثبت‌نام", callback_data='menu_login')],
        [InlineKeyboardButton("دسته‌بندی محصولات", callback_data='menu_categories')],
        [InlineKeyboardButton("جستجوی محصول", callback_data='menu_search')],
        [InlineKeyboardButton("سبد خرید", callback_data='menu_cart')],
        [InlineKeyboardButton("سفارش‌ها", callback_data='menu_orders')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🎉 به فروشگاه خوش اومدی! یکی از گزینه‌ها رو انتخاب کن:", reply_markup=reply_markup)

# هندلر دکمه‌های منو
async def start_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    fake_update = Update(update.update_id, message=query.message)
    if data == 'menu_login':
        await login(fake_update, context)
    elif data == 'menu_categories':
        await categories_command(fake_update, context)
    elif data == 'menu_search':
        await query.message.reply_text("🔍 دستور جستجو:\n`/search گوشی`")
    elif data == 'menu_cart':
        await show_cart(fake_update, context)
    elif data == 'menu_orders':
        await show_orders(fake_update, context)

# ⏬ راه‌اندازی نهایی ربات و تعریف تمام هندلرها
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(start_menu_handler, pattern="^menu_"))
app.add_handler(CommandHandler("login", login))
app.add_handler(CommandHandler("categories", categories_command))
app.add_handler(CommandHandler("search", search_products))
app.add_handler(CommandHandler("cart", show_cart))
app.add_handler(CommandHandler("orders", show_orders))

app.add_handler(CallbackQueryHandler(show_products, pattern="^categoryid_"))
app.add_handler(CallbackQueryHandler(pagination_handler, pattern="^(next_page|prev_page)$"))
app.add_handler(CallbackQueryHandler(add_bookmark_handler, pattern="^bookmark_"))
app.add_handler(CallbackQueryHandler(add_to_cart_handler, pattern="^addcart_"))
app.add_handler(CallbackQueryHandler(remove_from_cart_handler, pattern="^remove_cart_"))  # 👈 این خط باید باشه
app.add_handler(CallbackQueryHandler(pay_cart_handler, pattern="^pay_cart$"))

app.add_handler(CallbackQueryHandler(orders_pagination_handler, pattern="^orders_(next_page|prev_page)$"))
app.add_handler(CallbackQueryHandler(order_images_handler, pattern="^orderimgs_"))
app.add_handler(CallbackQueryHandler(button_click))  # هندلر ثبت‌نام و ورود
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))


# ✳️ ساخت Flask اپ
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "✅ Bot is running."

@flask_app.route(f'/{TOKEN}', methods=["POST"])
async def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.update_queue.put(update)
    return "ok"

# ✳️ تنظیم Webhook روی Telegram
async def set_webhook():
    if RENDER_URL:
        webhook_url = f"{RENDER_URL}/{TOKEN}"
        await application.bot.set_webhook(url=webhook_url)
        logging.info(f"Webhook set to: {webhook_url}")
    else:
        logging.warning("RENDER_URL not set.")

# ✳️ اجرای نهایی
if __name__ == '__main__':
    import asyncio
    asyncio.run(set_webhook())
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))








