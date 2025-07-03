import os
import mysql.connector
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import bcrypt
import requests
import jdatetime
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration from environment variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_PORT=os.getenv("DB_PORT")
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "https://pcstore.liara.run/payment")

# Database connection
def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        port=DB_PORT,
    )

db = get_db_connection()
cursor = db.cursor()

# User states
STATES = {
    'AWAITING_EMAIL': 1,
    'AWAITING_PASSWORD': 2,
    'AWAITING_FIRST_NAME': 3,
    'AWAITING_LAST_NAME': 4,
    'AWAITING_PHONE': 5
}

# Helper functions
def refresh_db_connection():
    global db, cursor
    if db.is_connected():
        db.close()
    db = get_db_connection()
    cursor = db.cursor()

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def check_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

def format_price(price):
    return "{:,}".format(int(price))

# Telegram bot handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("ورود / ثبت‌نام", callback_data='menu_login')],
        [InlineKeyboardButton("دسته‌بندی محصولات", callback_data='menu_categories')],
        [InlineKeyboardButton("جستجوی محصول", callback_data='menu_search')],
        [InlineKeyboardButton("سبد خرید", callback_data='menu_cart')],
        [InlineKeyboardButton("سفارش‌ها", callback_data='menu_orders')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "به ربات فروشگاه خوش آمدید!\nیکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=reply_markup
    )

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("ورود", callback_data='login')],
        [InlineKeyboardButton("ثبت‌ نام", callback_data='register')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('لطفا انتخاب کنید:', reply_markup=reply_markup)

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'login':
        await query.message.reply_text('لطفا ایمیل خود را وارد کنید:')
        context.user_data['state'] = STATES['AWAITING_EMAIL']
        context.user_data['action'] = 'login'
    elif query.data == 'register':
        await query.message.reply_text('لطفا نام خود را وارد کنید:')
        context.user_data['state'] = STATES['AWAITING_FIRST_NAME']
        context.user_data['action'] = 'register'

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
            context.user_data['password'] = text
            email = context.user_data['email']
            password = context.user_data['password']

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

            try:
                cursor.execute(
                    "INSERT INTO users (first_name, last_name, email, password, phone) VALUES (%s, %s, %s, %s, %s)",
                    (first_name, last_name, email, password, phone)
                )
                db.commit()
                await update.message.reply_text('✅ ثبت‌نام موفقیت‌آمیز بود!')
            except mysql.connector.Error as err:
                await update.message.reply_text(f'❌ خطا در ثبت‌نام: {err}')
            context.user_data.clear()

async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
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
            await update.message.reply_text("📚 لطفاً یک دسته‌بندی را انتخاب کنید:", reply_markup=reply_markup)
        else:
            await update.message.reply_text("❌ هیچ دسته‌ای پیدا نشد.")
    except mysql.connector.Error as err:
        await update.message.reply_text(f"❌ خطا در دریافت دسته‌بندی‌ها: {err}")
        refresh_db_connection()

async def show_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        category_id = int(query.data.replace("categoryid_", ""))
        context.user_data['category_id'] = category_id
        context.user_data['product_offset'] = 0
        await send_product_page(update, context, page=0)
    except Exception as e:
        await query.message.reply_text(f"❌ خطا در نمایش محصولات: {e}")

async def send_product_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int):
    try:
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
                f"🛍 نام محصول: {name}\n📄مشخصات: {desc}\n💰 قیمت اصلی: {format_price(price)} تومان\n"
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
                        InlineKeyboardButton("⭐ افزودن به علاقه‌مندی‌ها", callback_data=f"bookmark_{prod_id}"),
                        InlineKeyboardButton("🛒 افزودن به سبد خرید", callback_data=f"addcart_{prod_id}")
                    ]
                ])

            try:
                if image_path.startswith('http'):
                    await update.effective_chat.send_photo(photo=image_path, caption=caption, reply_markup=product_buttons)
                else:
                    with open(f"public/{image_path}", 'rb') as img:
                        await update.effective_chat.send_photo(photo=img, caption=caption, reply_markup=product_buttons)
            except Exception as e:
                await update.effective_chat.send_message(f"🚫 خطا در نمایش تصویر: {e}\n{caption}", reply_markup=product_buttons)
        
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
    except Exception as e:
        await update.effective_chat.send_message(f"❌ خطا در نمایش محصولات: {e}")
        refresh_db_connection()

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

async def search_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ لطفاً یک عبارت برای جستجو وارد کنید.\nمثال: `/search مادربرد`")
        return

    try:
        search_query = "%{}%".format(" ".join(context.args))

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
                f"🎯 تخفیف: {discount}%\n✅ قیمت نهایی: {format_price(final_price)} تومان"
            )

            buttons = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⭐ افزودن به علاقه‌مندی‌ها", callback_data=f"bookmark_{prod_id}"),
                    InlineKeyboardButton("🛒 افزودن به سبد خرید", callback_data=f"addcart_{prod_id}")
                ]
            ])

            try:
                if image_path.startswith('http'):
                    await update.message.reply_photo(photo=image_path, caption=caption, reply_markup=buttons)
                else:
                    with open(f"public/{image_path}", 'rb') as img:
                        await update.message.reply_photo(photo=img, caption=caption, reply_markup=buttons)
            except Exception as e:
                await update.message.reply_text(f"🚫 خطا در نمایش تصویر: {e}\n{caption}", reply_markup=buttons)
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در جستجو: {e}")
        refresh_db_connection()

async def add_bookmark_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not context.user_data.get('logged_in'):
        await query.message.reply_text("❗ برای افزودن به علاقه‌مندی‌ها باید ابتدا وارد شوید.")
        return

    try:
        prod_id = int(query.data.replace("bookmark_", ""))
        email = context.user_data.get('user_email')
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        if not user:
            await query.message.reply_text("❗ کاربر یافت نشد.")
            return
        user_id = user[0]

        cursor.execute("SELECT 1 FROM bookmarks WHERE user_id = %s AND product_id = %s", (user_id, prod_id))
        if cursor.fetchone():
            await query.message.reply_text("⭐ این محصول قبلاً به علاقه‌مندی‌های شما افزوده شده است.")
            return

        cursor.execute("INSERT INTO bookmarks (user_id, product_id) VALUES (%s, %s)", (user_id, prod_id))
        db.commit()
        await query.message.reply_text("⭐ محصول به علاقه‌مندی‌های شما افزوده شد.")
    except Exception as e:
        await query.message.reply_text(f"❌ خطا در افزودن به علاقه‌مندی‌ها: {e}")
        refresh_db_connection()

from datetime import datetime

async def add_to_cart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not context.user_data.get('logged_in'):
        await query.message.reply_text("❗ برای افزودن به سبد خرید باید ابتدا وارد شوید.")
        return

    try:
        # استخراج product_id از callback_data
        prod_id = int(query.data.replace("addcart_", ""))
        cart = context.user_data.get('cart', {})
        current_quantity = cart.get(prod_id, 0)

        # گرفتن محدودیت از دیتابیس
        cursor.execute("SELECT limited FROM products WHERE id = %s", (prod_id,))
        result = cursor.fetchone()

        if not result:
            await query.message.reply_text("❗ محصول یافت نشد.")
            return

        limit = result[0]
        if limit is not None and current_quantity + 1 > limit:
            await query.message.reply_text(f"🚫 حداکثر تعداد مجاز برای این محصول: {limit} عدد است.")
            return

        # افزودن به سبد خرید
        new_quantity = current_quantity + 1
        cart[prod_id] = new_quantity
        context.user_data['cart'] = cart
        await query.message.reply_text("🛒 محصول به سبد خرید شما افزوده شد.")

        # رزرو محصول در جدول reservations
        cursor.execute("SELECT id FROM users WHERE email = %s", (context.user_data.get('user_email'),))
        user_row = cursor.fetchone()

        if user_row:
            user_id = user_row[0]
            now = datetime.now()

            # بررسی وجود رزرو قبلی
            cursor.execute("""
                SELECT id FROM reservations
                WHERE user_id = %s AND product_id = %s
            """, (user_id, prod_id))
            existing = cursor.fetchone()

            if existing:
                # بروزرسانی رزرو قبلی
                cursor.execute("""
                    UPDATE reservations
                    SET quantity = %s, reserved_at = %s
                    WHERE user_id = %s AND product_id = %s
                """, (new_quantity, now, user_id, prod_id))
            else:
                # درج رزرو جدید
                cursor.execute("""
                    INSERT INTO reservations (user_id, product_id, quantity, reserved_at)
                    VALUES (%s, %s, %s, %s)
                """, (user_id, prod_id, new_quantity, now))

            db.commit()

    except Exception as e:
        await query.message.reply_text(f"❌ خطا در افزودن به سبد خرید: {e}")

async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('logged_in'):
        await update.message.reply_text("❗ برای مشاهده سبد خرید باید ابتدا وارد شوید.")
        return

    cart = context.user_data.get('cart', {})
    if not cart:
        await update.message.reply_text("🛒 سبد خرید شما خالی است.")
        return

    try:
        total = 0
        for prod_id, quantity in cart.items():
            cursor.execute("SELECT name, price, discount, image_path FROM products WHERE id = %s", (prod_id,))
            row = cursor.fetchone()
            if not row:
                continue
            name, price, discount, image_path = row
            final_price = int(price * (1 - discount / 100))
            line_total = final_price * quantity
            total += line_total
            caption = (
                f"🛒 {name}\n"
                f"تعداد: {quantity}\n"
                f"قیمت واحد: {format_price(final_price)} تومان\n"
                f"جمع: {format_price(line_total)} تومان"
            )
            
            remove_button = InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ حذف", callback_data=f"remove_cart_{prod_id}")]
            ])

            try:
                if image_path.startswith('http'):
                    await update.message.reply_photo(photo=image_path, caption=caption, reply_markup=remove_button)
                else:
                    with open(f"public/{image_path}", 'rb') as img:
                        await update.message.reply_photo(photo=img, caption=caption, reply_markup=remove_button)
            except Exception as e:
                await update.message.reply_text(f"{caption}\n🚫 خطا در نمایش تصویر: {e}", reply_markup=remove_button)

        pay_button = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 پرداخت", callback_data="pay_cart")]
        ])
        await update.message.reply_text(f"\n💵 مجموع کل: {format_price(total)} تومان", reply_markup=pay_button)
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در نمایش سبد خرید: {e}")
        refresh_db_connection()

async def remove_from_cart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not context.user_data.get('logged_in'):
        await query.message.reply_text("❗ برای حذف از سبد خرید باید ابتدا وارد شوید.")
        return

    try:
        prod_id = int(query.data.replace("remove_cart_", ""))
        cart = context.user_data.get('cart', {})

        if prod_id in cart:
            cart.pop(prod_id)
            context.user_data['cart'] = cart
            success = True
        else:
            await query.message.reply_text("❗ این محصول در سبد خرید شما نیست.")
            success = False
    except Exception as e:
        await query.message.reply_text(f"❌ خطا در حذف از سبد خرید: {e}")
        return

    if success:
        
            await query.message.reply_text("✅ محصول از سبد خرید حذف شد.")
            await show_cart(update, context)
        


async def pay_cart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not context.user_data.get('logged_in'):
        await query.message.reply_text("❗ برای پرداخت باید ابتدا وارد شوید.")
        return

    cart = context.user_data.get('cart', {})
    if not cart:
        await query.message.reply_text("🛒 سبد خرید شما خالی است.")
        return

    
    products = []
    subtotal = 0
    email = context.user_data.get('user_email')

    
    cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
    user_result = cursor.fetchone()
    if not user_result:
        await query.message.reply_text("❌ خطا در دریافت اطلاعات کاربر!")
        return

    user_id = user_result[0]

    for prod_id, quantity in cart.items():
        cursor.execute("SELECT id, price, discount FROM products WHERE id = %s", (prod_id,))
        product_data = cursor.fetchone()
        if not product_data:
            continue

        product_id, price, discount = product_data
        final_price = int(price * (1 - discount / 100))
        subtotal += final_price * quantity

        products.append({
            "product_id": product_id,
            "price": int(price),
            "discount": int(discount),
            "quantity": int(quantity)
        })
    chat_id = query.message.chat_id
    # ساخت داده‌های JSON
    payment_data = {
        "user_id": user_id,
        "subtotal": int(subtotal),
        "products": products,
        "chat_id": chat_id,
    }

    try:
       
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        response = requests.post(
            "https://pcstore.liara.run/api/payment",
            json=payment_data,
            headers=headers
        )
        
        response_data = response.json()
        
        if response.status_code == 200 and response_data.get('success'):
            payment_url = response_data.get('payment_url')
            keyboard = [
                [InlineKeyboardButton("🔗 رفتن به صفحه پرداخت", url=payment_url)]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
           
            
            if 'cart' in context.user_data:
                del context.user_data['cart']
                
            
            await query.message.reply_text("برای پرداخت روی دکمه زیر کلیک کنید:", reply_markup=reply_markup)
        else:
            error_msg = response_data.get('error', 'خطای ناشناخته')
            await query.message.reply_text(f"❌ خطا در ایجاد لینک پرداخت! {error_msg}")
        
    except Exception as e:
        await query.message.reply_text(f"❌ خطا در ارتباط با سرور پرداخت: {str(e)}")
    refresh_db_connection()

async def show_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('logged_in'):
        await update.message.reply_text("❗ برای مشاهده سفارش‌ها باید ابتدا وارد شوید.")
        return
    
    context.user_data['orders_page'] = 0
    await send_orders_page(update, context, page=0)

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
        await update.message.reply_text("📦 شما هیچ سفارشی ثبت نکرده‌اید.")
        return

    page_size = 4
    start = page * page_size
    end = start + page_size
    orders_page = orders[start:end]

    if not orders_page:
        if hasattr(update, "callback_query") and update.callback_query:
            await update.callback_query.message.reply_text("📦 سفارش بیشتری وجود ندارد.")
        else:
            await update.message.reply_text("📦 سفارش بیشتری وجود ندارد.")
        return

    status_map = {
        "processing": "در حال پردازش",
        "shipped": "در حال ارسال",
        "delivered": "تحویل داده شده",
        "returned": "مرجوع شده",
        "return_requested": "درخواست بازگشت",
        "return_in_progress":  "درحال بازگشت",
        "returned": "مرجوع شده",
        "return_rejected": "رد درخواست مرجوعی",
    }

    for order_id, status, created_at in orders_page:
        status_fa = status_map.get(str(status).lower(), str(status))
        shamsi_date = jdatetime.date.fromgregorian(date=created_at.date()).strftime('%Y/%m/%d')
        msg = (
            f"🧾 سفارش شماره: {order_id}\n"
            f"تاریخ ثبت: {shamsi_date}\n"
            f"وضعیت: {status_fa}\n"
        )
        cursor.execute("""
            SELECT od.product_id,od.discount od.quantity, od.price, p.name, p.image_path
            FROM order_details od
            JOIN products p ON od.product_id = p.id
            WHERE od.order_id = %s
        """, (order_id,))
        details = cursor.fetchall()
        if not details:
            msg += "بدون محصول.\n"
            await update.effective_chat.send_message(msg)
            continue

        total = 0
        product_lines = []
        image_ids = []
        for prod_id, qty, price, name, discount, image_path in details:
            final_price = int(price * (1 - discount / 100))
            line_total = final_price * qty
            total += line_total

            product_text = (
             f"🔸 {name}\n"
             f"تعداد: {qty}\n"
             f"قیمت واحد: {format_price(price)} تومان\n"
            )

            if discount > 0:
                product_text += (
                    f"🔻 تخفیف: {discount}%\n"
                    f"💸 قیمت با تخفیف: {format_price(final_price)} تومان\n"
                )
            else:
                product_text += f"💸 قیمت نهایی: {format_price(final_price)} تومان\n"

            product_text += f"جمع: {format_price(line_total)} تومان\n"

            product_lines.append(product_text)
            
            image_ids.append({"prod_id": prod_id, "name": name, "image_path": image_path})
        msg += "\n".join(product_lines)
        msg += f"\n💵 جمع کل سفارش: {format_price(total)} تومان"

       
        images_button = InlineKeyboardMarkup([
            [InlineKeyboardButton("📷 نمایش تصاویر محصولات", callback_data=f"orderimgs_{order_id}")]
        ])
        await update.effective_chat.send_message(msg, reply_markup=images_button)

        
        if 'order_images' not in context.user_data:
            context.user_data['order_images'] = {}
       
        context.user_data['order_images'][str(order_id)] = image_ids

    nav_buttons = []
    if end < len(orders):
        nav_buttons.append(InlineKeyboardButton("بعدی ⏩", callback_data="orders_next_page"))
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⏪ قبلی", callback_data="orders_prev_page"))
    if nav_buttons:
        reply_markup = InlineKeyboardMarkup([nav_buttons])
        await update.effective_chat.send_message("صفحه سفارش‌ها:", reply_markup=reply_markup)

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

async def order_images_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        _, order_id = query.data.split("_")
        order_images = context.user_data.get('order_images', {}).get(order_id)
        if not order_images:
            await query.message.reply_text("تصاویر محصولات این سفارش موجود نیست.")
            return

        for item in order_images:
            name = item["name"]
            image_path = item["image_path"]
            try:
                if image_path.startswith('http'):
                    await query.message.reply_photo(photo=image_path, caption=name)
                else:
                    with open(f"public/{image_path}", 'rb') as img:
                        await query.message.reply_photo(photo=img, caption=name)
            except Exception as e:
                await query.message.reply_text(f"{name}\n🚫 خطا در نمایش تصویر: {e}")
    except Exception as e:
        await query.message.reply_text(f"❌ خطا در نمایش تصاویر: {e}")

async def start_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'menu_login':
        fake_update = Update(update.update_id, message=query.message)
        await login(fake_update, context)
    elif data == 'menu_categories':
        fake_update = Update(update.update_id, message=query.message)
        await categories_command(fake_update, context)
    elif data == 'menu_search':
        await query.message.reply_text("برای جستجو، دستور زیر را ارسال کنید:\n/search [عبارت مورد نظر]")
    elif data == 'menu_cart':
        class DummyMessage:
            def __init__(self, chat, from_user):
                self.chat = chat
                self.from_user = from_user
            async def reply_text(self, *args, **kwargs):
                await query.message.reply_text(*args, **kwargs)
            async def reply_photo(self, *args, **kwargs):
                await query.message.reply_photo(*args, **kwargs)
        dummy_update = Update(
            update.update_id,
            message=DummyMessage(query.message.chat, query.from_user)
        )
        await show_cart(dummy_update, context)
    elif data == 'menu_orders':
        class DummyMessage:
            def __init__(self, chat, from_user):
                self.chat = chat
                self.from_user = from_user
            async def reply_text(self, *args, **kwargs):
                await query.message.reply_text(*args, **kwargs)
        dummy_update = Update(
            update.update_id,
            message=DummyMessage(query.message.chat, query.from_user)
        )
        await show_orders(dummy_update, context)


PORT = int(os.environ.get('PORT', 8443))  # پورت پیش‌فرض 8443 برای webhook

# Initialize bot
app = ApplicationBuilder().token(TOKEN).build()

# Add handlers
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(start_menu_handler, pattern="^menu_"))
app.add_handler(CommandHandler("login", login))
app.add_handler(CommandHandler("categories", categories_command))
app.add_handler(CallbackQueryHandler(show_products, pattern="^categoryid_"))
app.add_handler(CallbackQueryHandler(pagination_handler, pattern="^(next_page|prev_page)$"))
app.add_handler(CommandHandler("search", search_products))
app.add_handler(CallbackQueryHandler(add_bookmark_handler, pattern="^bookmark_"))
app.add_handler(CallbackQueryHandler(add_to_cart_handler, pattern="^addcart_"))
app.add_handler(CommandHandler("cart", show_cart))
app.add_handler(CallbackQueryHandler(pay_cart_handler, pattern="^pay_cart$"))
app.add_handler(CallbackQueryHandler(remove_from_cart_handler, pattern="^remove_cart_"))
app.add_handler(CommandHandler("orders", show_orders))
app.add_handler(CallbackQueryHandler(orders_pagination_handler, pattern="^orders_(next_page|prev_page)$"))
app.add_handler(CallbackQueryHandler(order_images_handler, pattern="^orderimgs_"))
app.add_handler(CallbackQueryHandler(button_click))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Run bot
# Run bot
if __name__ == "__main__":
    # در Render از webhook استفاده می‌کنیم
    if os.environ.get('RENDER'):
        # تنظیمات webhook
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TOKEN,
            webhook_url=f"https://{os.environ.get('RENDER_SERVICE_NAME')}.onrender.com/{TOKEN}",
            cert=None,  # برای توسعه، نیاز به SSL نداریم
            drop_pending_updates=True
        )
    else:
        # برای توسعه محلی از polling استفاده می‌کنیم
        app.run_polling()