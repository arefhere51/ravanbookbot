# ######################################################################
# ############# نسخه کامل و نهایی ربات کتابخانه (v6.3) ##############
# ######################################################################

import asyncio
import html
import logging
import os
import re
import sqlite3
import textwrap
from datetime import datetime, time

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
)
from telegram.constants import ParseMode
from telegram.error import Forbidden, TelegramError, BadRequest

# --- راه‌اندازی لاگ‌گیری ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- اطلاعات ربات و ادمین ---
TOKEN = "7344675872:AAHNOpVI_83wVqMT1koXz9m1NG5vV4jKRkM"  # ! توکن خود را جایگزین کنید
CHANNEL_ID = -1002849839756  # ! شناسه کانال خود را جایگزین کنید
ADMIN_USER_IDS = [149772217, 114724606]  # ! شناسه‌های کاربری ادمین‌ها

if not TOKEN or "YOUR_TOKEN" in TOKEN:
    logger.error("خطا: توکن ربات تلگرام تنظیم نشده است.")
    exit(1)

# --- کلیدهای ثابت و وضعیت‌های مکالمه ---
BACK_BUTTON, MAIN_MENU_BUTTON, SEARCH_BUTTON, CONTACT_ADMIN_BUTTON, CANCEL_BUTTON = "🔙 بازگشت", "🏠 منوی اصلی", "🔍 جستجو", "📨 ارتباط با ادمین", "❌ لغو"
DOWNLOAD_PREFIX, CONFIRM_DELETE_PREFIX, CANCEL_ACTION, BROADCAST_CONFIRM, BROADCAST_CANCEL = "dl_", "confirm_del_item_", "cancel_action", "broadcast_confirm", "broadcast_cancel"
GET_REFERRAL_CODE_CALLBACK = "get_my_referral_code"
RESET_REFERRALS_CONFIRM, RESET_REFERRALS_CANCEL = "reset_ref_confirm", "reset_ref_cancel"

# [MODIFIED] - بازبینی وضعیت‌های مکالمه
(CHOOSE_TYPE, GET_TITLE, GET_DESCRIPTION, CHOOSE_CATEGORIES, GET_TAGS, AWAIT_FILES, AWAIT_REQUIRES_INVITE) = range(7)
(LIST_BUTTONS, ACTION_CHOICE, GET_NEW_LABEL, GET_NEW_MESSAGE, GET_EDIT_LABEL, GET_EDIT_MESSAGE, CONFIRM_DELETE) = range(7, 14)
CONFIRM_DELETE_CAT_PREFIX = "confirm_del_cat_"
(SEARCH_ITEM_TO_EDIT, SELECT_ITEM_TO_EDIT, AWAIT_NEW_TITLE, AWAIT_NEW_DESCRIPTION, AWAIT_NEW_CATEGORIES, EDIT_ITEM_OPTIONS, AWAIT_NEW_TAGS) = range(14, 21)
(REQUEST_BUTTON_MENU, AWAIT_NEW_REQUEST_LABEL) = range(21, 23)
(MANAGE_JOIN_MENU, AWAIT_CHANNEL_ID, AWAIT_CHANNEL_LINK, AWAIT_CHANNEL_TO_REMOVE) = range(23, 27)
(SEARCH_ITEM_TO_DELETE, SELECT_ITEM_TO_DELETE) = range(27, 29)
(AWAIT_CAPTION_TEXT,) = range(29, 30)
(MANAGE_MESSAGES_MENU, AWAIT_WELCOME_MESSAGE, AWAIT_MAIN_MENU_MESSAGE) = range(30, 33)
(SEARCH_ITEM_TO_ARCHIVE, SELECT_ITEM_TO_ARCHIVE, AWAIT_ARCHIVE_REASON) = range(33, 36)
(SEARCH_ITEM_TO_UNARCHIVE, SELECT_ITEM_TO_UNARCHIVE) = range(36, 38)
(AWAIT_NEW_FILES_FOR_EDIT,) = range(38, 39)
(STATS_MENU,) = range(50, 51)
(CONFIRM_RESET_REFERRALS,) = range(51, 52)

# --- مسیردهی و اتصال به دیتابیس ---
script_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(script_dir, "pdf_library.db")

def get_db_connection():
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY,
                type TEXT NOT NULL,
                title TEXT NOT NULL UNIQUE,
                description TEXT,
                requires_invite INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                archive_reason TEXT
            )
        """)
        cursor.execute("""CREATE TABLE IF NOT EXISTS item_files (id INTEGER PRIMARY KEY, item_id INTEGER, part_order INTEGER, channel_message_id INTEGER NOT NULL, file_id TEXT NOT NULL, file_unique_id TEXT NOT NULL, FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT NOT NULL, parent_id INTEGER, FOREIGN KEY (parent_id) REFERENCES categories(id) ON DELETE CASCADE, UNIQUE(name, parent_id))""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS tags (id INTEGER PRIMARY KEY, tag_name TEXT NOT NULL UNIQUE)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS item_categories (item_id INTEGER, category_id INTEGER, PRIMARY KEY (item_id, category_id), FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE, FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS item_tags (item_id INTEGER, tag_id INTEGER, PRIMARY KEY (item_id, tag_id), FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE, FOREIGN KEY (tag_id) REFERENCES tags(id))""")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                successful_invites INTEGER NOT NULL DEFAULT 0,
                has_special_access INTEGER NOT NULL DEFAULT 0
            )
        """)
        cursor.execute("""CREATE TABLE IF NOT EXISTS broadcast_queue (id INTEGER PRIMARY KEY, broadcast_id INTEGER NOT NULL, admin_id INTEGER NOT NULL, admin_message_id INTEGER NOT NULL, from_chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, status TEXT DEFAULT 'pending')""")
        cursor.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(title, description, tags, tokenize = 'porter unicode61')""")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dynamic_buttons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                button_label TEXT NOT NULL,
                message_text TEXT NOT NULL,
                category_id INTEGER,
                FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE CASCADE,
                UNIQUE(button_label, category_id)
            )
        """)
        cursor.execute("""CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS force_join_channels (chat_id INTEGER PRIMARY KEY, chat_link TEXT NOT NULL UNIQUE, title TEXT)""")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS download_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS search_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                query_text TEXT NOT NULL,
                was_successful BOOLEAN NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL, 
                referred_id INTEGER NOT NULL UNIQUE, 
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (referrer_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (referred_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)
        cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", ('force_join_enabled', '0'))
        cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", ('request_button_label', 'درخواست محتوا'))
        cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", ('request_button_visible', '1'))
        cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", ('global_caption_text', ''))
        cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", ('welcome_message', 'سلام {user_name}! به ربات کتابخانه خوش آمدید.'))
        cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", ('main_menu_message', 'یک دسته‌بندی را انتخاب کنید:'))
        cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", ('referral_threshold', '3'))
        conn.commit()
    logger.info("ساختار اولیه دیتابیس (v6.3) بررسی شد.")

def update_db_schema():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(items)")
            columns = [info['name'] for info in cursor.fetchall()]
            if 'status' not in columns:
                cursor.execute("ALTER TABLE items ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
            if 'archive_reason' not in columns:
                cursor.execute("ALTER TABLE items ADD COLUMN archive_reason TEXT")
            if 'requires_invite' not in columns:
                cursor.execute("ALTER TABLE items ADD COLUMN requires_invite INTEGER NOT NULL DEFAULT 0")
            cursor.execute("PRAGMA table_info(users)")
            columns = [info['name'] for info in cursor.fetchall()]
            if 'successful_invites' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN successful_invites INTEGER NOT NULL DEFAULT 0")
            if 'has_special_access' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN has_special_access INTEGER NOT NULL DEFAULT 0")
            cursor.execute("PRAGMA table_info(dynamic_buttons)")
            columns_buttons = [info['name'] for info in cursor.fetchall()]
            if 'category_id' not in columns_buttons:
                cursor.execute("ALTER TABLE dynamic_buttons ADD COLUMN category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL")
            conn.commit()
            logger.info("Database schema is up-to-date for v6.3.")
    except sqlite3.Error as e:
        logger.error(f"Failed to update database schema: {e}")

def build_keyboard(buttons: list, columns: int = 2) -> ReplyKeyboardMarkup:
    menu = [buttons[i: i + columns] for i in range(0, len(buttons), columns)]
    return ReplyKeyboardMarkup(menu, resize_keyboard=True, one_time_keyboard=False)

def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_USER_IDS

def is_descendant(conn, child_id, parent_id_to_check):
    current_id = child_id
    while current_id is not None:
        row = conn.execute("SELECT parent_id FROM categories WHERE id = ?", (current_id,)).fetchone()
        if not row: return False
        parent_id = row['parent_id']
        if parent_id == parent_id_to_check: return True
        current_id = parent_id
    return False

async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    if _is_admin(user_id):
        return True
    with get_db_connection() as conn:
        is_enabled = conn.execute("SELECT value FROM config WHERE key = 'force_join_enabled'").fetchone()
        if not is_enabled or is_enabled['value'] == '0':
            return True
        channels = conn.execute("SELECT chat_id, chat_link, title FROM force_join_channels").fetchall()
        if not channels:
            return True
    unjoined_channels = []
    for channel in channels:
        try:
            member = await context.bot.get_chat_member(chat_id=channel['chat_id'], user_id=user_id)
            if member.status not in ['creator', 'administrator', 'member']:
                unjoined_channels.append(channel)
        except (BadRequest, TelegramError) as e:
            logger.error(f"Error checking membership for user {user_id} in chat {channel['chat_id']}: {e}")
            continue
    if unjoined_channels:
        message_text = "کاربر گرامی، برای استفاده از ربات لازم است ابتدا در کانال(های) زیر عضو شوید:"
        keyboard = [[InlineKeyboardButton(f"عضویت در کانال «{ch['title']}»", url=ch['chat_link'])] for ch in unjoined_channels]
        keyboard.append([InlineKeyboardButton("✅ عضو شدم، بررسی مجدد", callback_data="check_join_status_again")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.callback_query:
            await update.callback_query.answer()
            await update.effective_message.reply_text(message_text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(message_text, reply_markup=reply_markup)
        return False
    return True

async def recheck_membership_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("در حال بررسی وضعیت عضویت شما...")
    if await check_membership(update, context):
        await query.message.delete()
        await query.message.reply_text("✅ عضویت شما تایید شد. اکنون می‌توانید از ربات استفاده کنید.")
        await start(update, context)

async def master_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text: return
    if not await check_membership(update, context):
        return
    user_id = update.effective_user.id
    text = update.message.text
    state = context.user_data.get("state")
    if _is_admin(user_id) and update.message.reply_to_message:
        if await handle_admin_reply(update, context):
            return

    with get_db_connection() as conn:
        current_category_id = context.user_data.get("path", [0])[-1]
        button_query = "SELECT message_text FROM dynamic_buttons WHERE button_label = ? AND "
        params = [text]
        if current_category_id == 0:
            button_query += "category_id IS NULL"
        else:
            button_query += "category_id = ?"
            params.append(current_category_id)
        button_message = conn.execute(button_query, tuple(params)).fetchone()
        if button_message:
            await update.message.reply_html(button_message["message_text"])
            return
        config = {row['key']: row['value'] for row in conn.execute("SELECT key, value FROM config WHERE key LIKE 'request_button_%'").fetchall()}
        request_button_label = config.get('request_button_label', 'درخواست محتوا')
        is_visible = config.get('request_button_visible', '0')
        if text == request_button_label and is_visible == '1' and current_category_id == 0:
            await handle_content_request_command(update, context)
            return

    if state == 'awaiting_broadcast_message':
        await handle_broadcast_content(update, context); return
    logger.info(f"Master handler processing text: '{text}' from user {user_id} with state: {state}")
    
    if text == MAIN_MENU_BUTTON:
        await show_main_menu(update, context); return
    if text == BACK_BUTTON:
        if state in ['awaiting_search', 'awaiting_contact_message', 'awaiting_content_request']:
            await show_main_menu(update, context)
        else:
            path = context.user_data.get("path", [0]);
            if len(path) > 1: path.pop()
            await display_categories_or_items(update, context, path[-1])
        return
    if state == "awaiting_search":
        await search_items_fts(update, context); return
    if state == "awaiting_contact_message":
        await handle_user_contact_message(update, context); return
    if state == "awaiting_content_request":
        await handle_user_content_request_message(update, context); return
    if state and (state.startswith("awaiting_new_category_name_") or state.startswith("awaiting_edited_category_name_")):
        await handle_manage_category_text_input(update, context); return
    if text == SEARCH_BUTTON:
        context.user_data["state"] = "awaiting_search"; await update.message.reply_text("لطفا عبارت مورد نظر برای جستجو را وارد کنید:", reply_markup=build_keyboard([BACK_BUTTON, MAIN_MENU_BUTTON])); return
    if text == CONTACT_ADMIN_BUTTON:
        await contact_command(update, context); return
    with get_db_connection() as conn:
        current_parent_id = context.user_data.get("path", [0])[-1]
        query, params = ("SELECT id FROM categories WHERE name = ? AND parent_id IS NULL", (text,)) if current_parent_id == 0 else ("SELECT id FROM categories WHERE name = ? AND parent_id = ?", (text, current_parent_id))
        category = conn.execute(query, params).fetchone()
        if category:
            await display_categories_or_items(update, context, category["id"])
        else:
            await update.message.reply_text("دستور شما نامشخص است یا دسته‌بندی انتخاب شده یافت نشد.")

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Displaying main menu for user {update.effective_user.id}.")
    context.user_data.clear()
    context.user_data["path"] = [0]
    await display_categories_or_items(update, context, 0)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    if not await check_membership(update, context):
        return
    with get_db_connection() as conn:
        existing_user = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)).fetchone()
        is_new_user = not existing_user
        if is_new_user:
            conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
            conn.commit()
            logger.info(f"New user {user_id} ({user.full_name}) joined.")
        if context.args and context.args[0].startswith("ref_"):
            if is_new_user:
                try:
                    referrer_id = int(context.args[0].split('_')[1])
                    if referrer_id != user_id:
                        conn.execute("INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)", (referrer_id, user_id))
                        conn.execute("UPDATE users SET successful_invites = successful_invites + 1 WHERE user_id = ?", (referrer_id,))
                        conn.commit()
                        logger.info(f"User {user_id} was referred by {referrer_id}.")
                        referrer = conn.execute("SELECT successful_invites, has_special_access FROM users WHERE user_id = ?", (referrer_id,)).fetchone()
                        threshold = int(conn.execute("SELECT value FROM config WHERE key = 'referral_threshold'").fetchone()['value'])
                        if referrer and referrer['successful_invites'] >= threshold and not referrer['has_special_access']:
                            conn.execute("UPDATE users SET has_special_access = 1 WHERE user_id = ?", (referrer_id,))
                            conn.commit()
                            await context.bot.send_message(
                                chat_id=referrer_id,
                                text="🎉 **تبریک!** شما به حد نصاب دعوت رسیدید.\nاز این پس به تمام محتواهای ویژه ربات دسترسی دائمی دارید."
                            )
                        else:
                             await context.bot.send_message(
                                chat_id=referrer_id,
                                text="✅ یک کاربر جدید با لینک شما به ربات پیوست."
                            )
                except sqlite3.IntegrityError:
                     logger.warning(f"User {user_id} tried to use a referral link but was already referred.")
                except Exception as e:
                    logger.error(f"Error processing referral for user {user_id} from referrer in link {context.args[0]}: {e}")
    if context.args and context.args[0].startswith("dl_"):
        try:
            item_id = int(context.args[0].split("_")[1])
            logger.info(f"User {user_id} ({user.full_name}) used deep link for item ID: {item_id}")
            await send_item_files(update, context, item_id)
            await show_main_menu(update, context)
            return
        except (ValueError, IndexError):
            logger.warning(f"User {user_id} used an invalid deep link payload: {context.args[0]}")
            await update.message.reply_text("لینک دانلود نامعتبر است.")
        except Exception as e:
            logger.error(f"Error processing deep link for item ID from payload {context.args[0]}: {e}", exc_info=True)
            await update.message.reply_text("خطایی در پردازش لینک رخ داد. لطفاً مطمئن شوید لینک معتبر است.")
            await show_main_menu(update, context)
            return
    logger.info(f"User {user.id} ({user.full_name}) used /start command.")
    with get_db_connection() as conn:
        welcome_message_row = conn.execute("SELECT value FROM config WHERE key = 'welcome_message'").fetchone()
        welcome_text = welcome_message_row['value'] if welcome_message_row else "به ربات کتابخانه خوش آمدید."
    personalized_welcome = welcome_text.replace('{user_name}', user.mention_html())
    await update.message.reply_html(personalized_welcome)
    await show_main_menu(update, context)

async def display_categories_or_items(update: Update, context: ContextTypes.DEFAULT_TYPE, parent_id: int):
    chat = update.effective_chat or (update.callback_query.message.chat if update.callback_query else None)
    if not chat:
        logger.warning("Could not determine chat in display_categories_or_items"); return
    sub_categories, items, dynamic_buttons, is_request_button_visible, request_button_label = [], [], [], False, ""
    main_menu_text = ""
    with get_db_connection() as conn:
        if parent_id == 0:
            sub_categories = conn.execute("SELECT name, id FROM categories WHERE parent_id IS NULL ORDER BY name").fetchall()
            items = conn.execute("""SELECT i.id, i.title, i.type, i.requires_invite FROM items i LEFT JOIN item_categories ic ON i.id = ic.item_id WHERE ic.category_id IS NULL AND i.status = 'active' ORDER BY i.title""").fetchall()
            dynamic_buttons = conn.execute("SELECT button_label FROM dynamic_buttons WHERE category_id IS NULL ORDER BY id ASC").fetchall()
            config_rows = conn.execute("SELECT key, value FROM config WHERE key IN ('request_button_label', 'request_button_visible', 'main_menu_message')").fetchall()
            config = {row['key']: row['value'] for row in config_rows}
            main_menu_text = config.get('main_menu_message', 'یک دسته‌بندی را انتخاب کنید:')
            request_button_label = config.get('request_button_label')
            is_request_button_visible = config.get('request_button_visible') == '1'
        else:
            sub_categories = conn.execute("SELECT name, id FROM categories WHERE parent_id = ? ORDER BY name", (parent_id,)).fetchall()
            items = conn.execute("SELECT id, title, type, requires_invite FROM items WHERE id IN (SELECT item_id FROM item_categories WHERE category_id = ?) AND status = 'active' ORDER BY title", (parent_id,)).fetchall()
            dynamic_buttons = conn.execute("SELECT button_label FROM dynamic_buttons WHERE category_id = ? ORDER BY id ASC", (parent_id,)).fetchall()
    path_list = [0]
    if parent_id != 0:
        curr_id = parent_id; temp_path = []
        with get_db_connection() as conn:
            while curr_id is not None:
                cat_row = conn.execute("SELECT name, parent_id FROM categories WHERE id = ?", (curr_id,)).fetchone()
                if cat_row: temp_path.append(curr_id); curr_id = cat_row["parent_id"]
                else: curr_id = None
        path_list.extend(reversed(temp_path))
    context.user_data["path"] = path_list
    category_buttons_text = [cat["name"] for cat in sub_categories]
    dynamic_button_labels = [btn['button_label'] for btn in dynamic_buttons]
    if parent_id == 0:
        fixed_buttons = [SEARCH_BUTTON, CONTACT_ADMIN_BUTTON]
        special_buttons = [request_button_label] if is_request_button_visible and request_button_label else []
        all_buttons = category_buttons_text + dynamic_button_labels + fixed_buttons + special_buttons
    else:
        all_buttons = category_buttons_text + dynamic_button_labels + [BACK_BUTTON, MAIN_MENU_BUTTON]
    reply_markup = build_keyboard(all_buttons)
    if not sub_categories and not items and not dynamic_buttons and parent_id != 0:
        message_text = "این دسته‌بندی خالی است."
    elif parent_id == 0:
        message_text = main_menu_text
    else:
        message_text = "یک دسته‌بندی را انتخاب کنید یا از دکمه‌های موجود استفاده نمایید:"
    current_message_text = update.effective_message.text if update.effective_message else ""
    if update.callback_query and current_message_text == message_text:
        await update.callback_query.edit_message_reply_markup(reply_markup)
    elif update.callback_query:
        try:
            await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        except BadRequest:
             await context.bot.send_message(chat.id, message_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    if items:
        emoji_map = {"book": "📚", "video": "🎬", "audio": "🎵"}
        lock_emoji = "🔒"
        inline_keyboard_buttons = []
        for item in items:
            title_prefix = f"{lock_emoji} " if item['requires_invite'] else ""
            button_text = f"{title_prefix}{emoji_map.get(item['type'], '📁')} {item['title']}"
            inline_keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=f"{DOWNLOAD_PREFIX}{item['id']}")])
        items_header = "موارد دانلودی این دسته‌بندی:"
        await context.bot.send_message(chat.id, items_header, reply_markup=InlineKeyboardMarkup(inline_keyboard_buttons))

async def search_items_fts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    user_id = update.effective_user.id
    if not query:
        await update.message.reply_text("لطفا عبارت مورد نظر برای جستجو را وارد کنید.", reply_markup=build_keyboard([BACK_BUTTON, MAIN_MENU_BUTTON])); return
    with get_db_connection() as conn:
        fts_query = " OR ".join(query.split())
        items = conn.execute("""SELECT i.id, i.title, i.type, i.requires_invite FROM items i JOIN items_fts fts ON i.id = fts.rowid WHERE items_fts MATCH ? AND i.status = 'active' ORDER BY rank""", (fts_query,)).fetchall()
        was_successful = True if items else False
        conn.execute("INSERT INTO search_log (user_id, query_text, was_successful) VALUES (?, ?, ?)", (user_id, query, was_successful))
        conn.commit()
    if not items:
        await update.message.reply_text(f"موردی برای '{html.escape(query)}' یافت نشد.", reply_markup=build_keyboard([BACK_BUTTON, MAIN_MENU_BUTTON]))
    else:
        emoji_map = {"book": "📚", "video": "🎬", "audio": "🎵"}
        lock_emoji = "🔒"
        keyboard_buttons = []
        for item in items:
            title_prefix = f"{lock_emoji} " if item['requires_invite'] else ""
            button_text = f"{title_prefix}{emoji_map.get(item['type'], '📁')} {item['title']}"
            keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=f"{DOWNLOAD_PREFIX}{item['id']}")])
        await update.message.reply_text(f"نتایج یافت‌شده برای '{html.escape(query)}':", reply_markup=InlineKeyboardMarkup(keyboard_buttons))
        await update.message.reply_text("می‌توانید عبارت دیگری را جستجو کنید یا از دکمه‌های زیر برای بازگشت استفاده نمایید:", reply_markup=build_keyboard([BACK_BUTTON, MAIN_MENU_BUTTON]))

async def inline_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query; await query.answer()
    data = query.data
    logger.info(f"Callback query received: '{data}' from user {query.from_user.id}")
    if data == "check_join_status_again":
        await recheck_membership_callback(update, context)
        return
    if data.startswith(DOWNLOAD_PREFIX):
        await send_item_files(query, context, int(data.split("_")[-1]))
    elif data == CANCEL_ACTION:
        try:
            await query.edit_message_text("عملیات لغو شد.")
        except BadRequest:
            pass

async def send_item_files(requester: Update | CallbackQuery, context: ContextTypes.DEFAULT_TYPE, item_id: int):
    if isinstance(requester, CallbackQuery):
        user_id = requester.from_user.id
        chat_id = requester.message.chat.id
    else:
        user_id = requester.effective_user.id
        chat_id = requester.effective_chat.id
    with get_db_connection() as conn:
        item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if not item:
            await context.bot.send_message(chat_id=chat_id, text="این آیتم یافت نشد یا حذف شده است.")
            return
        if item['status'] != 'active':
            reason = item['archive_reason'] or "این آیتم به درخواست ناشر از دسترس خارج شده است."
            await context.bot.send_message(chat_id=chat_id, text=f"⚠️ {html.escape(reason)}")
            return
        if item['requires_invite'] == 1:
            user_data = conn.execute("SELECT has_special_access, successful_invites FROM users WHERE user_id = ?", (user_id,)).fetchone()
            is_exempt = _is_admin(user_id) or (user_data and user_data['has_special_access'] == 1)
            if not is_exempt:
                threshold = int(conn.execute("SELECT value FROM config WHERE key = 'referral_threshold'").fetchone()['value'])
                invites_done = user_data['successful_invites'] if user_data else 0
                message_text = (
                    f"🔒 **این یک آیتم ویژه است!**\n\n"
                    f"برای دسترسی دائمی به تمام محتواهای ویژه، باید **{threshold}** نفر را به ربات دعوت کنید.\n"
                    f"شما تاکنون **{invites_done}** نفر را با موفقیت دعوت کرده‌اید.\n\n"
                    f"برای دریافت لینک دعوت اختصاصی خود، روی دکمه زیر کلیک کنید."
                )
                keyboard = [[InlineKeyboardButton("🔗 دریافت کد دعوت من", callback_data=GET_REFERRAL_CODE_CALLBACK)]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await context.bot.send_message(chat_id=chat_id, text=message_text, reply_markup=reply_markup)
                return
        conn.execute("INSERT INTO download_log (item_id, user_id) VALUES (?, ?)", (item_id, user_id))
        conn.commit()
        files = conn.execute("SELECT * FROM item_files WHERE item_id = ? ORDER BY part_order ASC", (item_id,)).fetchall()
        global_caption_row = conn.execute("SELECT value FROM config WHERE key = 'global_caption_text'").fetchone()
        appendix = f"\n---\n{html.escape(global_caption_row['value'])}" if global_caption_row and global_caption_row['value'] else ""
    if not files:
        await context.bot.send_message(chat_id=chat_id, text="متاسفانه فایل‌های این مورد یافت نشد.")
        return
    caption = f"<b>{html.escape(item['title'])}</b>\n\n{html.escape(item['description'] or '')}{appendix}"
    await context.bot.send_message(chat_id=chat_id, text=f"⏳ در حال ارسال {len(files)} فایل برای «{item['title']}»...")
    for index, file in enumerate(files):
        part_caption = caption if index == 0 else f"<b>{html.escape(item['title'])}</b> - بخش {index + 1}{appendix}"
        try:
            await context.bot.copy_message(chat_id=chat_id, from_chat_id=CHANNEL_ID, message_id=file['channel_message_id'], caption=part_caption, parse_mode=ParseMode.HTML)
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Error sending file part {index + 1} for item {item_id}: {e}", exc_info=True)
            await context.bot.send_message(chat_id=chat_id, text=f"متاسفانه در ارسال بخش {index + 1} خطایی رخ داد.")

async def get_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("لطفاً بخشی از نام آیتم مورد نظر را بعد از دستور وارد کنید.\nمثال: `/getid کتاب`")
        return
    query = " ".join(context.args)
    with get_db_connection() as conn:
        items = conn.execute("SELECT id, title FROM items WHERE title LIKE ? ORDER BY title LIMIT 20", (f'%{query}%',)).fetchall()
    if not items:
        await update.message.reply_text(f"هیچ آیتمی با نام '{html.escape(query)}' یافت نشد.")
        return
    response_text = f"نتایج یافت شده برای '<b>{html.escape(query)}</b>':\n\n"
    for item in items:
        response_text += f"📝 <b>عنوان:</b> {html.escape(item['title'])}\n"
        response_text += f"🆔 <b>شناسه:</b> <code>{item['id']}</code>\n"
        response_text += "---\n"
    await update.message.reply_html(response_text)

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    logger.info(f"Admin {user_id} requested a database backup.")
    await update.message.reply_text("در حال آماده‌سازی فایل پشتیبان...")
    try:
        await update.message.reply_document(
            document=open(db_path, 'rb'),
            filename=f"backup_{os.path.basename(db_path)}_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.db",
            caption="فایل پشتیبان دیتابیس در این لحظه."
        )
    except Exception as e:
        logger.error(f"Failed to send backup to admin {user_id}: {e}")
        await update.message.reply_text(f"❌ خطایی در ارسال فایل پشتیبان رخ داد: {e}")

async def daily_backup_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("Running daily backup job...")
    try:
        caption = f"پشتیبان خودکار دیتابیس\nزمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        await context.bot.send_document(
            chat_id=CHANNEL_ID,
            document=open(db_path, 'rb'),
            filename=f"daily_backup_{os.path.basename(db_path)}_{datetime.now().strftime('%Y-%m-%d')}.db",
            caption=caption
        )
        logger.info(f"Daily backup successfully sent to channel {CHANNEL_ID}.")
    except Exception as e:
        logger.error(f"Failed to send daily backup to channel {CHANNEL_ID}: {e}")

async def non_admin_access_denied(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.warning(f"Non-admin user {update.effective_user.id} tried to use admin command: {update.message.text}")
    await update.message.reply_text("❌ شما اجازه دسترسی به این دستور را ندارید.")

async def contact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['state'] = 'awaiting_contact_message'; await update.message.reply_text("لطفا پیام خود را برای ارسال به ادمین بنویسید.", reply_markup=build_keyboard([BACK_BUTTON, MAIN_MENU_BUTTON]))

async def handle_user_contact_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    message_for_admin = (
        f"✉️ **پیام جدید از کاربر**\n\n"
        f"👤 **نام:** {html.escape(user.full_name)}\n"
        f"🆔 **شناسه:** <a href='tg://user?id={user.id}'>{user.id}</a>\n"
        f"----\n\n"
        f"{html.escape(text)}"
    )
    for admin_id in ADMIN_USER_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=message_for_admin, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Failed to send contact message to admin {admin_id}: {e}")
    await update.message.reply_text("✅ پیام شما با موفقیت به ادمین ارسال شد.")
    await show_main_menu(update, context)

async def handle_content_request_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['state'] = 'awaiting_content_request'
    await update.message.reply_text("لطفاً محتوای درخواستی خود را (مثلاً نام کتاب یا دوره) بنویسید و ارسال کنید.", reply_markup=build_keyboard([BACK_BUTTON, MAIN_MENU_BUTTON]))

async def handle_user_content_request_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    message_for_admin = (
        f"📥 **درخواست محتوای جدید از کاربر**\n\n"
        f"👤 **نام:** {html.escape(user.full_name)}\n"
        f"🆔 **شناسه:** <a href='tg://user?id={user.id}'>{user.id}</a>\n"
        f"----\n\n"
        f"**متن درخواست:**\n{html.escape(text)}"
    )
    for admin_id in ADMIN_USER_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=message_for_admin, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Failed to send content request to admin {admin_id}: {e}")
    await update.message.reply_text("✅ درخواست شما با موفقیت برای ادمین ارسال شد.")
    await show_main_menu(update, context)

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    original_message = update.message.reply_to_message
    if not original_message or original_message.from_user.id != context.bot.id:
        return False
        
    # [FIXED] - استفاده از یک Regex پایدارتر برای یافتن شناسه کاربر از روی لینک
    match = re.search(r"tg://user\?id=(\d+)", original_message.text_html or "")
    if not match:
        logger.warning(f"Admin reply failed: Could not find user ID in message. HTML: {original_message.text_html}")
        # اگر در این پیام شناسه نبود، ممکن است پیام دیگری باشد. پس به سایر بخش‌های ربات اجازه پردازش می‌دهیم.
        return False
    
    original_user_id = int(match.group(1))
    admin_reply_text = update.message.text
    try:
        await context.bot.send_message(
            chat_id=original_user_id, 
            text=f"✉️ **پاسخی از طرف ادمین برای شما ارسال شد:**\n\n---\n\n{html.escape(admin_reply_text)}", 
            parse_mode=ParseMode.HTML
        )
        await update.message.reply_text("✅ پاسخ شما برای کاربر ارسال شد.")
        return True
    except Exception as e:
        logger.error(f"Failed to send admin reply to user {original_user_id}: {e}")
        await update.message.reply_text(f"❌ خطا در ارسال پیام به کاربر: {e}")
        return True

async def admin_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = """
    <b>راهنمای دستورات ادمین (نسخه 6.3)</b>
    /add - افزودن آیتم جدید (با قابلیت ویژه کردن)
    /edit_item - ویرایش آیتم (عنوان، توضیحات، دسته، هشتگ و...)
    /delete - حذف دائمی یک آیتم
    /archive - بایگانی کردن یک آیتم
    /unarchive - بازگردانی یک آیتم از بایگانی
    /manage_categories - مدیریت دسته‌بندی‌ها
    /manage_button - مدیریت دکمه‌های داینامیک
    /manage_request_button - مدیریت دکمه "درخواست محتوا"
    /manage_join - مدیریت عضویت اجباری
    /manage_messages - مدیریت پیام‌های کلیدی ربات
    /broadcast - ارسال پیام همگانی
    /stats - نمایش پنل آمار پیشرفته
    /getid &lt;نام&gt; - دریافت شناسه آیتم
    /set_caption - تنظیم پاورقی سراسری فایل‌ها
    /backup - دریافت فایل پشتیبان دیتابیس
    
    <b>--- دستورات سیستم دعوت ---</b>
    /set_threshold &lt;عدد&gt; - تنظیم حد نصاب دعوت لازم برای دسترسی ویژه
    /exempt &lt;شناسه کاربر&gt; - معاف کردن کاربر از نیاز به دعوت
    /unexempt &lt;شناسه کاربر&gt; - لغو معافیت کاربر
    /reset_referrals - صفر کردن دعوت‌های تمام کاربران (با تاییدیه)
    
    /admin - نمایش همین راهنما
    
    <b>لینک مستقیم:</b>
    <code>https://t.me/BOT_USERNAME?start=dl_ITEM_ID</code>
    """
    bot_username = (await context.bot.get_me()).username
    help_text = help_text.replace("BOT_USERNAME", bot_username)
    await update.message.reply_html(textwrap.dedent(help_text))

async def manage_messages_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await _send_message_management_menu(update, context)
    return MANAGE_MESSAGES_MENU

async def _send_message_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str = ""):
    query = update.callback_query
    message = update.effective_message
    with get_db_connection() as conn:
        config_rows = conn.execute("SELECT key, value FROM config WHERE key IN ('welcome_message', 'main_menu_message')").fetchall()
        config = {row['key']: row['value'] for row in config_rows}
    welcome_msg = config.get('welcome_message', '<i>(تنظیم نشده)</i>')
    main_menu_msg = config.get('main_menu_message', '<i>(تنظیم نشده)</i>')
    text = (f"{message_text}\n\n" if message_text else "") + textwrap.dedent(f"""
    ⚙️ **پنل مدیریت پیام‌ها**
    1️⃣ **پیام خوشامدگویی (/start):**
    `{html.escape(welcome_msg)}`
    2️⃣ **پیام منوی اصلی:**
    `{html.escape(main_menu_msg)}`
    ---
    برای ویرایش، روی دکمه مربوطه کلیک کنید.
    می‌توانید از `{{user_name}}` در متن پیام خوشامدگویی برای نمایش نام کاربر استفاده کنید.
    """)
    keyboard = [
        [InlineKeyboardButton("✏️ ویرایش پیام خوشامدگویی", callback_data="edit_msg_welcome")],
        [InlineKeyboardButton("✏️ ویرایش پیام منوی اصلی", callback_data="edit_msg_main")],
        [InlineKeyboardButton("🚪 خروج", callback_data="edit_msg_exit")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if query:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        await message.reply_html(text, reply_markup=reply_markup)

async def manage_messages_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = query.data
    if action == "edit_msg_welcome":
        await query.edit_message_text("لطفاً متن جدید برای **پیام خوشامدگویی (/start)** را ارسال کنید.")
        return AWAIT_WELCOME_MESSAGE
    elif action == "edit_msg_main":
        await query.edit_message_text("لطفاً متن جدید برای **پیام منوی اصلی** را ارسال کنید.")
        return AWAIT_MAIN_MENU_MESSAGE
    elif action == "edit_msg_exit":
        await query.edit_message_text("✅ خروج از پنل.")
        context.user_data.clear()
        await show_main_menu(update, context) 
        return ConversationHandler.END

async def get_new_welcome_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_text = update.message.text
    with get_db_connection() as conn:
        conn.execute("UPDATE config SET value = ? WHERE key = 'welcome_message'", (new_text,))
        conn.commit()
    await update.message.reply_text("✅ پیام خوشامدگویی با موفقیت به‌روز شد.")
    await _send_message_management_menu(update, context)
    return MANAGE_MESSAGES_MENU

async def get_new_main_menu_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_text = update.message.text
    with get_db_connection() as conn:
        conn.execute("UPDATE config SET value = ? WHERE key = 'main_menu_message'", (new_text,))
        conn.commit()
    await update.message.reply_text("✅ پیام منوی اصلی با موفقیت به‌روز شد.")
    await _send_message_management_menu(update, context)
    return MANAGE_MESSAGES_MENU

async def manage_button_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    context.user_data['button_category_id'] = None 
    await _send_button_list_menu(update, context)
    return LIST_BUTTONS

async def manage_buttons_for_category_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    category_id = int(query.data.split('_')[-1])
    context.user_data['button_category_id'] = category_id
    context.user_data['entry_from_cat_management'] = True
    await _send_button_list_menu(update, context)
    return LIST_BUTTONS

async def _send_button_list_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str = ""):
    query, message = update.callback_query, update.effective_message
    category_id = context.user_data.get('button_category_id')
    with get_db_connection() as conn:
        if category_id is None:
            buttons = conn.execute("SELECT id, button_label FROM dynamic_buttons WHERE category_id IS NULL ORDER BY id ASC").fetchall()
            cat_name = "منوی اصلی"
        else:
            buttons = conn.execute("SELECT id, button_label FROM dynamic_buttons WHERE category_id = ? ORDER BY id ASC", (category_id,)).fetchall()
            cat_name_row = conn.execute("SELECT name FROM categories WHERE id = ?", (category_id,)).fetchone()
            cat_name = cat_name_row['name'] if cat_name_row else "نامشخص"
    keyboard = [[InlineKeyboardButton(f"🔘 {html.escape(btn['button_label'])}", callback_data=f"db_select_{btn['id']}")] for btn in buttons]
    if context.user_data.get('entry_from_cat_management'):
        exit_callback = "db_exit_to_cat_manage"
        exit_text = "🔙 بازگشت به مدیریت دسته‌بندی"
    else:
        exit_callback = "db_exit"
        exit_text = "🚪 خروج"
    keyboard += [[InlineKeyboardButton("➕ افزودن دکمه جدید", callback_data="db_add_new")], [InlineKeyboardButton(exit_text, callback_data=exit_callback)]]
    status = "برای مدیریت یک دکمه، روی آن کلیک کنید." if buttons else "هیچ دکمه‌ای برای این بخش تعریف نشده است."
    final_text = (f"{message_text}\n\n" if message_text else "") + f"⚙️ <b>پنل دکمه‌های داینامیک</b>\n📍 مکان: <b>{html.escape(cat_name)}</b>\n\n{status}"
    if query: 
        try:
            await query.edit_message_text(final_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        except BadRequest:
             await message.reply_html(final_text, reply_markup=InlineKeyboardMarkup(keyboard))
    else: 
        await message.reply_html(final_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def list_buttons_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer(); data = query.data
    if data.startswith("db_select_"):
        button_id = int(data.split('_')[-1]); context.user_data['selected_button_id'] = button_id
        with get_db_connection() as conn: button = conn.execute("SELECT button_label FROM dynamic_buttons WHERE id = ?", (button_id,)).fetchone()
        kbd = [[InlineKeyboardButton("✏️ ویرایش پیام", callback_data="db_action_edit_msg")], [InlineKeyboardButton("🗑 حذف", callback_data="db_action_delete")], [InlineKeyboardButton("🔙 بازگشت", callback_data="db_action_back")]]
        await query.edit_message_text(f"دکمه: <b>{html.escape(button['button_label'])}</b>\nچه عملیاتی انجام می‌دهید؟", reply_markup=InlineKeyboardMarkup(kbd), parse_mode=ParseMode.HTML); return ACTION_CHOICE
    elif data == "db_add_new": 
        await query.edit_message_text("لطفا عنوان (برچسب) دکمه جدید را ارسال کنید:")
        return GET_NEW_LABEL
    elif data == "db_exit": 
        await query.edit_message_text("✅ خروج از پنل."); 
        return await end_conversation_and_start(update, context)
    elif data == "db_exit_to_cat_manage":
        await query.edit_message_text("بازگشت به پنل مدیریت دسته‌بندی‌ها...")
        await manage_categories_command(update, context)
        return ConversationHandler.END

async def action_choice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer(); action = query.data
    if action == "db_action_edit_msg": 
        await query.edit_message_text("لطفا متن پیام جدید برای این دکمه را ارسال کنید:"); 
        return GET_EDIT_MESSAGE
    elif action == "db_action_delete":
        button_id = context.user_data['selected_button_id']
        with get_db_connection() as conn: button = conn.execute("SELECT button_label FROM dynamic_buttons WHERE id = ?", (button_id,)).fetchone()
        kbd = [[InlineKeyboardButton("✅ بله، حذف کن", callback_data=f"db_confirm_delete_{button_id}")], [InlineKeyboardButton("❌ خیر", callback_data="db_action_back")]]
        await query.edit_message_text(f"آیا از حذف دکمه <b>{html.escape(button['button_label'])}</b> مطمئن هستید؟", reply_markup=InlineKeyboardMarkup(kbd), parse_mode=ParseMode.HTML); return CONFIRM_DELETE
    elif action == "db_action_back": 
        await _send_button_list_menu(update, context); 
        return LIST_BUTTONS

async def confirm_delete_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer(); button_id = int(query.data.split('_')[-1])
    with get_db_connection() as conn: conn.execute("DELETE FROM dynamic_buttons WHERE id = ?", (button_id,)); conn.commit()
    await _send_button_list_menu(update, context, "✅ دکمه با موفقیت حذف شد."); return LIST_BUTTONS

async def get_new_label_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_button_label'] = update.message.text
    await update.message.reply_html(f"عنوان دکمه: <code>{html.escape(update.message.text)}</code>\n\nاکنون، **پیام کامل** این دکمه را ارسال کنید. این پیام با فرمت HTML ارسال خواهد شد."); return GET_NEW_MESSAGE

async def get_new_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message_text = update.message.text_html
    button_label = context.user_data.pop('new_button_label')
    category_id = context.user_data.get('button_category_id')
    try:
        with get_db_connection() as conn: 
            conn.execute("INSERT INTO dynamic_buttons (button_label, message_text, category_id) VALUES (?, ?, ?)", (button_label, message_text, category_id))
            conn.commit()
        await _send_button_list_menu(update, context, "✅ دکمه جدید با موفقیت ایجاد شد.")
    except sqlite3.IntegrityError: 
        await update.message.reply_text("❌ خطا: دکمه‌ای با این عنوان در این بخش از قبل وجود دارد.")
        await _send_button_list_menu(update, context)
    return LIST_BUTTONS

async def get_edit_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message_text = update.message.text_html
    button_id = context.user_data.get('selected_button_id')
    try:
        with get_db_connection() as conn: 
            conn.execute("UPDATE dynamic_buttons SET message_text = ? WHERE id = ?", (message_text, button_id))
            conn.commit()
        await _send_button_list_menu(update, context, "✅ پیام دکمه با موفقیت ویرایش شد.")
    except Exception as e:
        logger.error(f"Failed to edit button message: {e}")
        await update.message.reply_text("❌ خطایی در ویرایش پیام دکمه رخ داد.")
        await _send_button_list_menu(update, context)
    return LIST_BUTTONS

async def manage_request_button_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear(); await _send_request_button_menu(update, context); return REQUEST_BUTTON_MENU

async def _send_request_button_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, query = update.effective_message, update.callback_query
    with get_db_connection() as conn: config = {r['key']: r['value'] for r in conn.execute("SELECT key, value FROM config WHERE key LIKE 'request_button_%'").fetchall()}
    label, is_visible = config.get('request_button_label', 'N/A'), config.get('request_button_visible') == '1'
    status, toggle_text = ("🟢 فعال", "🔴 غیرفعال کردن") if is_visible else ("🔴 غیرفعال", "🟢 فعال کردن")
    kbd = [[InlineKeyboardButton("✏️ تغییر نام", callback_data="req_btn_rename")], [InlineKeyboardButton(toggle_text, callback_data="req_btn_toggle")], [InlineKeyboardButton("🚪 خروج", callback_data="req_btn_exit")]]
    text = f"⚙️ **مدیریت دکمه \"درخواست محتوا\"**\n\n**نام فعلی:** `{label}`\n**وضعیت:** {status}"
    if query: await query.edit_message_text(textwrap.dedent(text), reply_markup=InlineKeyboardMarkup(kbd), parse_mode=ParseMode.MARKDOWN)
    else: await message.reply_text(textwrap.dedent(text), reply_markup=InlineKeyboardMarkup(kbd), parse_mode=ParseMode.MARKDOWN)

async def request_button_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer(); action = query.data
    if action == "req_btn_rename": await query.edit_message_text("نام جدید دکمه:"); return AWAIT_NEW_REQUEST_LABEL
    elif action == "req_btn_toggle":
        with get_db_connection() as conn:
            new_visibility = '0' if conn.execute("SELECT value FROM config WHERE key = 'request_button_visible'").fetchone()[0] == '1' else '1'
            conn.execute("UPDATE config SET value = ? WHERE key = 'request_button_visible'", (new_visibility,)); conn.commit()
        await _send_request_button_menu(update, context); return REQUEST_BUTTON_MENU
    elif action == "req_btn_exit": await query.edit_message_text("✅ خروج از پنل."); return await end_conversation_and_start(update, context)

async def get_new_request_label_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_label = update.message.text.strip()
    with get_db_connection() as conn: conn.execute("UPDATE config SET value = ? WHERE key = 'request_button_label'", (new_label,)); conn.commit()
    await update.message.reply_text(f"✅ نام به '{new_label}' تغییر یافت."); await _send_request_button_menu(update, context); return REQUEST_BUTTON_MENU

async def manage_join_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await _send_join_menu(update, context)
    return MANAGE_JOIN_MENU

async def _send_join_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, query = update.effective_message, update.callback_query
    with get_db_connection() as conn:
        is_enabled = conn.execute("SELECT value FROM config WHERE key = 'force_join_enabled'").fetchone()['value'] == '1'
        channels = conn.execute("SELECT chat_id, title FROM force_join_channels").fetchall()
    status, toggle_text = ("🟢 فعال", "🔴 غیرفعال کردن") if is_enabled else ("🔴 غیرفعال", "🟢 فعال کردن")
    text = f"⚙️ **مدیریت عضویت اجباری**\n\n**وضعیت سیستم:** {status}\n\n"
    if channels:
        text += "کانال‌های ثبت‌شده:\n"
        for ch in channels:
            text += f"- {html.escape(ch['title'])} (<code>{ch['chat_id']}</code>)\n"
    else:
        text += "هیچ کانالی برای عضویت اجباری ثبت نشده است."
    keyboard = [
        [InlineKeyboardButton("➕ افزودن کانال", callback_data="join_add")],
        [InlineKeyboardButton("➖ حذف کانال", callback_data="join_remove")],
        [InlineKeyboardButton(toggle_text, callback_data="join_toggle")],
        [InlineKeyboardButton("🚪 خروج", callback_data="join_exit")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if query:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        await message.reply_html(text, reply_markup=reply_markup)

async def manage_join_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer(); action = query.data
    if action == "join_toggle":
        with get_db_connection() as conn:
            current_status = conn.execute("SELECT value FROM config WHERE key = 'force_join_enabled'").fetchone()['value']
            new_status = '0' if current_status == '1' else '1'
            conn.execute("UPDATE config SET value = ? WHERE key = 'force_join_enabled'", (new_status,)); conn.commit()
        await _send_join_menu(update, context)
        return MANAGE_JOIN_MENU
    elif action == "join_add":
        await query.edit_message_text("لطفاً شناسه عددی کانال یا یوزرنیم آن (با @) را ارسال کنید.")
        return AWAIT_CHANNEL_ID
    elif action == "join_remove":
        with get_db_connection() as conn:
            channels = conn.execute("SELECT chat_id, title FROM force_join_channels").fetchall()
        if not channels:
            await query.answer("کانالی برای حذف وجود ندارد.", show_alert=True)
            return MANAGE_JOIN_MENU
        keyboard = [[InlineKeyboardButton(f"🗑 {ch['title']}", callback_data=f"join_rem_{ch['chat_id']}")] for ch in channels]
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="join_back_to_menu")])
        await query.edit_message_text("کدام کانال حذف شود؟", reply_markup=InlineKeyboardMarkup(keyboard))
        return AWAIT_CHANNEL_TO_REMOVE
    elif action == "join_exit":
        await query.edit_message_text("✅ خروج از پنل."); return await end_conversation_and_start(update, context)

async def get_channel_id_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id_str = update.message.text.strip()
    context.user_data['new_channel_id'] = chat_id_str
    try:
        chat = await context.bot.get_chat(chat_id=chat_id_str)
        context.user_data['new_channel_title'] = chat.title
        await update.message.reply_html(f"کانال «<b>{html.escape(chat.title)}</b>» یافت شد.\n\nاکنون لینک عضویت/عمومی کانال را ارسال کنید (مثال: https://t.me/YourChannel)")
        return AWAIT_CHANNEL_LINK
    except Exception as e:
        await update.message.reply_html(f"❌ خطا در یافتن کانال: {e}\n\nلطفاً مطمئن شوید ربات در کانال مورد نظر ادمین است و شناسه را درست وارد کرده‌اید. دوباره تلاش کنید.")
        return AWAIT_CHANNEL_ID

async def get_channel_link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    link = update.message.text.strip()
    if not link.startswith("http"):
        await update.message.reply_text("❌ لینک نامعتبر است. لطفاً لینک کامل را ارسال کنید.")
        return AWAIT_CHANNEL_LINK
    chat_id = context.user_data['new_channel_id']
    title = context.user_data['new_channel_title']
    try:
        with get_db_connection() as conn:
            conn.execute("INSERT INTO force_join_channels (chat_id, chat_link, title) VALUES (?, ?, ?)", (chat_id, link, title)); conn.commit()
        await update.message.reply_text("✅ کانال با موفقیت اضافه شد.")
    except sqlite3.IntegrityError:
        await update.message.reply_text("❌ این کانال یا لینک قبلاً ثبت شده است.")
    except Exception as e:
        await update.message.reply_text(f"❌ خطای دیتابیس: {e}")
    await _send_join_menu(update, context)
    return MANAGE_JOIN_MENU

async def remove_channel_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer(); action = query.data
    if action == "join_back_to_menu":
        await _send_join_menu(update, context)
        return MANAGE_JOIN_MENU
    elif action.startswith("join_rem_"):
        chat_id = int(action.split('_')[-1])
        with get_db_connection() as conn:
            conn.execute("DELETE FROM force_join_channels WHERE chat_id = ?", (chat_id,)); conn.commit()
        await query.answer("✅ کانال حذف شد.", show_alert=True)
        await _send_join_menu(update, context)
        return MANAGE_JOIN_MENU

async def end_conversation_and_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        logger.info(f"User {update.effective_user.id} ended a conversation.")
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text("عملیات لغو شد و به منوی اصلی بازگشتید.")
        except BadRequest:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="عملیات لغو شد.")
    await show_main_menu(update, context)
    return ConversationHandler.END

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear(); context.user_data['new_item'] = {}
    keyboard = [[InlineKeyboardButton("📚 کتاب", callback_data="add_type_book"), InlineKeyboardButton("🎬 ویدئو", callback_data="add_type_video"), InlineKeyboardButton("🎵 صوت", callback_data="add_type_audio")], [InlineKeyboardButton(CANCEL_BUTTON, callback_data="cancel_add")]]
    await update.message.reply_text("مرحله ۱ از ۶: لطفاً نوع محتوای جدید را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSE_TYPE

async def add_choice_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    item_type = query.data.split('_')[-1]
    context.user_data['new_item']['type'] = item_type
    type_map = {'book': 'کتاب', 'video': 'ویدئو', 'audio': 'صوت'}
    await query.edit_message_text(f"نوع: {type_map[item_type]}\n\nمرحله ۲ از ۶: لطفاً **عنوان** را ارسال کنید.")
    return GET_TITLE

async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_item']['title'] = update.message.text
    await update.message.reply_text(f"عنوان: {update.message.text}\n\nمرحله ۳ از ۶: لطفاً **توضیحات** را ارسال کنید (اختیاری، /skip).")
    return GET_DESCRIPTION
    
async def get_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_item']['description'] = update.message.text
    await update.message.reply_text('توضیحات ثبت شد.\n\nمرحله ۴ از ۶: **دسته‌بندی‌ها** را با # جدا کنید.\n' 'مثال: #رفرنس > آسیب شناسی روانی')
    return CHOOSE_CATEGORIES

async def skip_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_item']['description'] = None
    await update.message.reply_text('توضیحات رد شد.\n\nمرحله ۴ از ۶: **دسته‌بندی‌ها** را با # جدا کنید.\n' 'مثال: #رفرنس > آسیب شناسی روانی')
    return CHOOSE_CATEGORIES

async def get_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    categories = [c.strip() for c in update.message.text.split('#') if c.strip()]
    if not categories:
        await update.message.reply_text("خطا: حداقل یک دسته‌بندی باید وارد شود."); return CHOOSE_CATEGORIES
    context.user_data['new_item']['categories'] = categories
    await update.message.reply_text(f"دسته‌بندی‌ها: {', '.join(categories)}\n\nمرحله ۵ از ۶: **هشتگ‌ها** را با # جدا کنید (اختیاری، /skip).")
    return GET_TAGS

async def get_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_item']['tags'] = [t.strip() for t in update.message.text.split('#') if t.strip()]
    await ask_requires_invite(update, context)
    return AWAIT_REQUIRES_INVITE

async def skip_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_item']['tags'] = []
    await ask_requires_invite(update, context)
    return AWAIT_REQUIRES_INVITE

async def ask_requires_invite(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [[InlineKeyboardButton("✅ بله (ویژه باشد)", callback_data="set_invite_1")], [InlineKeyboardButton(" خیر (عمومی باشد)", callback_data="set_invite_0")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("مرحله ۶ از ۶: آیا این آیتم ویژه باشد و برای دسترسی به آن نیاز به دعوت باشد؟", reply_markup=reply_markup)
    return AWAIT_REQUIRES_INVITE

async def set_requires_invite_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    requires_invite = int(query.data.split('_')[-1])
    context.user_data['new_item']['requires_invite'] = requires_invite
    status_text = "ویژه" if requires_invite == 1 else "عمومی"
    await query.edit_message_text(f"وضعیت آیتم: **{status_text}**")
    return await save_item_and_request_files(update, context)

async def save_item_and_request_files(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    item_data = context.user_data['new_item']
    conn = get_db_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO items (type, title, description, requires_invite) VALUES (?, ?, ?, ?)", (item_data['type'], item_data['title'], item_data.get('description'), item_data.get('requires_invite', 0)))
            item_id = cursor.lastrowid
            context.user_data['new_item']['id'] = item_id
            if item_data.get('categories'):
                for cat_path_str in item_data['categories']:
                    path_parts = [part.strip() for part in cat_path_str.split('>') if part.strip()]
                    if not path_parts: continue
                    current_parent_id = None
                    final_category_id = None
                    for part in path_parts:
                        query = "SELECT id FROM categories WHERE name = ? AND "
                        params = [part]
                        if current_parent_id is None:
                            query += "parent_id IS NULL"
                        else:
                            query += "parent_id = ?"
                            params.append(current_parent_id)
                        cursor.execute(query, tuple(params))
                        cat_row = cursor.fetchone()
                        if cat_row:
                            final_category_id = cat_row['id']
                        else:
                            cursor.execute("INSERT INTO categories (name, parent_id) VALUES (?, ?)", (part, current_parent_id))
                            final_category_id = cursor.lastrowid
                        current_parent_id = final_category_id
                    if final_category_id:
                        cursor.execute("INSERT OR IGNORE INTO item_categories (item_id, category_id) VALUES (?, ?)", (item_id, final_category_id))
            tags_list = item_data.get('tags', [])
            if tags_list:
                for tag_name in tags_list:
                    cursor.execute("INSERT OR IGNORE INTO tags (tag_name) VALUES (?)", (tag_name.lower(),))
                    tag_id = cursor.execute("SELECT id FROM tags WHERE tag_name = ?", (tag_name.lower(),)).fetchone()['id']
                    cursor.execute("INSERT INTO item_tags (item_id, tag_id) VALUES (?, ?)", (item_id, tag_id))
            tags_str = ' '.join(tags_list)
            cursor.execute("INSERT INTO items_fts (rowid, title, description, tags) VALUES (?, ?, ?, ?)", (item_id, item_data['title'], item_data.get('description'), tags_str))
        context.user_data['part_counter'] = 1
        effective_message = update.callback_query.message if update.callback_query else update.message
        await effective_message.reply_text(f"✅ آیتم '{item_data['title']}' ایجاد شد.\nشناسه آیتم: `{item_id}`\n\nاکنون فایل(ها) را ارسال کنید و در انتها /done را بزنید.", parse_mode=ParseMode.MARKDOWN)
        return AWAIT_FILES
    except sqlite3.IntegrityError as e:
        effective_message = update.callback_query.message if update.callback_query else update.message
        if 'items.title' in str(e):
            await effective_message.reply_text(f"❌ خطا: آیتمی با عنوان '{item_data['title']}' از قبل وجود دارد. لطفاً عنوان دیگری انتخاب کنید یا فرآیند را لغو نمایید (/cancel).")
            await effective_message.reply_text("لطفاً **عنوان جدید** را ارسال کنید:")
            return GET_TITLE
        else:
            logger.error(f"Error saving item (IntegrityError): {e}", exc_info=True)
            await effective_message.reply_text(f"❌ خطای یکپارچگی دیتابیس: {e}")
            return await end_conversation_and_start(update, context)
    except Exception as e:
        logger.error(f"Error saving item: {e}", exc_info=True)
        effective_message = update.callback_query.message if update.callback_query else update.message
        await effective_message.reply_text(f"❌ خطای ناشناخته: {e}")
        return await end_conversation_and_start(update, context)
    finally:
        if conn:
            conn.close()

async def admin_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'new_item' not in context.user_data or 'id' not in context.user_data['new_item']: return
    item_id, part_order = context.user_data['new_item']['id'], context.user_data.get('part_counter', 1)
    attachment = update.message.document or update.message.video or update.message.audio or (update.message.photo[-1] if update.message.photo else None)
    if not attachment: return
    try:
        sent_message = await update.message.forward(chat_id=CHANNEL_ID)
        with get_db_connection() as conn:
            conn.execute("INSERT INTO item_files (item_id, part_order, channel_message_id, file_id, file_unique_id) VALUES (?, ?, ?, ?, ?)", (item_id, part_order, sent_message.message_id, attachment.file_id, attachment.file_unique_id)); conn.commit()
        await update.message.reply_text(f"فایل بخش {part_order} اضافه شد. فایل بعدی یا /done.")
        context.user_data['part_counter'] += 1
    except sqlite3.IntegrityError:
        await update.message.reply_text(f"❌ خطا در افزودن فایل. این فایل ممکن است به این آیتم قبلاً اضافه شده باشد.")
    except Exception as e:
        logger.error(f"Error adding file for item {item_id}: {e}", exc_info=True); await update.message.reply_text(f"خطا در ذخیره فایل: {e}")

async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("✅ فرآیند با موفقیت تکمیل شد.", reply_markup=ReplyKeyboardRemove()); return await end_conversation_and_start(update, context)

async def cancel_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if 'new_item' in context.user_data and 'id' in context.user_data['new_item']:
        with get_db_connection() as conn:
            conn.execute("DELETE FROM items WHERE id = ?", (context.user_data['new_item']['id'],));
            conn.commit()
            logger.info(f"Item with id {context.user_data['new_item']['id']} was deleted due to cancellation.")
    return await end_conversation_and_start(update, context)

async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("برای یافتن آیتم جهت حذف، نام آن را وارد کنید:", reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True))
    return SEARCH_ITEM_TO_DELETE

async def find_item_to_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.message.text.strip()
    with get_db_connection() as conn:
        items = conn.execute("SELECT id, title, type FROM items WHERE title LIKE ? ORDER BY title LIMIT 20", (f'%{query}%',)).fetchall()
    if not items:
        await update.message.reply_text(f"موردی با نام '{html.escape(query)}' یافت نشد. می‌توانید نام دیگری را جستجو کنید یا عملیات را لغو نمایید.")
        return SEARCH_ITEM_TO_DELETE
    keyboard = [[InlineKeyboardButton(f"🗑 {item['type']}: {item['title']}", callback_data=f"{CONFIRM_DELETE_PREFIX}{item['id']}")] for item in items]
    keyboard.append([InlineKeyboardButton("❌ لغو", callback_data="cancel_delete")])
    await update.message.reply_text("کدام مورد به صورت دائمی حذف شود؟", reply_markup=InlineKeyboardMarkup(keyboard))
    await update.message.reply_text("برای جستجوی مجدد، نام دیگری را وارد کنید.", reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True))
    return SELECT_ITEM_TO_DELETE

async def confirm_delete_item_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    item_id = int(query.data.split('_')[-1])
    with get_db_connection() as conn:
        item = conn.execute("SELECT title FROM items WHERE id = ?", (item_id,)).fetchone()
        if not item:
            await query.edit_message_text("این آیتم دیگر وجود ندارد."); return SELECT_ITEM_TO_DELETE
    kbd = [[InlineKeyboardButton("✅ بله، حذف کن", callback_data=f"final_delete_{item_id}")], [InlineKeyboardButton("❌ خیر، بازگرد", callback_data="cancel_delete")]]
    await query.edit_message_text(f"⚠️ **اخطار!**\nآیا از حذف دائمی آیتم «<b>{html.escape(item['title'])}</b>» اطمینان دارید؟\nاین عمل غیرقابل بازگشت است.", reply_markup=InlineKeyboardMarkup(kbd), parse_mode=ParseMode.HTML)
    return SELECT_ITEM_TO_DELETE

async def final_delete_item_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    item_id = int(query.data.split('_')[-1])
    with get_db_connection() as conn:
        item = conn.execute("SELECT title FROM items WHERE id = ?", (item_id,)).fetchone()
        if not item:
            await query.edit_message_text("این آیتم قبلا حذف شده است.")
        else:
            conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
            conn.execute("DELETE FROM items_fts WHERE rowid = ?", (item_id,))
            conn.commit()
            await query.edit_message_text(f"✅ آیتم '{html.escape(item['title'])}' با موفقیت برای همیشه حذف شد.")
    await show_main_menu(update, context)
    return ConversationHandler.END

async def cancel_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.edit_message_text("عملیات حذف لغو شد.")
    return await end_conversation_and_start(update, context)

async def edit_item_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("لطفاً بخشی از نام آیتمی که می‌خواهید ویرایش کنید را وارد نمایید:", reply_markup=ReplyKeyboardRemove()); return SEARCH_ITEM_TO_EDIT

async def search_item_to_edit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.message.text.strip()
    fts_query = " OR ".join(query.split())
    with get_db_connection() as conn:
        items = conn.execute("""
            SELECT i.id, i.title, i.type 
            FROM items i JOIN items_fts fts ON i.id = fts.rowid 
            WHERE items_fts MATCH ? 
            ORDER BY rank 
            LIMIT 20
        """, (fts_query,)).fetchall()

    if not items:
        await update.message.reply_text(
            f"هیچ آیتمی با نام '{html.escape(query)}' یافت نشد. لطفاً عبارت دیگری را امتحان کنید یا عملیات را لغو نمایید."
        )
        return SEARCH_ITEM_TO_EDIT

    keyboard = [[InlineKeyboardButton(f"✏️ {item['type']}: {item['title']}", callback_data=f"select_edit_{item['id']}")] for item in items] + [[InlineKeyboardButton("❌ لغو", callback_data="cancel_edit")]]
    await update.message.reply_text("کدام آیتم ویرایش شود؟", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_ITEM_TO_EDIT

async def select_item_to_edit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, from_sub_handler: bool = False) -> int:
    query = update.callback_query
    if from_sub_handler:
        message = update.message
        item_id = context.user_data['edit_item_id']
    else:
        await query.answer()
        message = query.message
        if query.data.startswith('select_edit_'):
            item_id = int(query.data.split('_')[-1])
            context.user_data['edit_item_id'] = item_id
        else:
            return await edit_item_options_handler(update, context)
    with get_db_connection() as conn: 
        item = conn.execute("SELECT title, requires_invite FROM items WHERE id = ?", (item_id,)).fetchone()
    status_text = "ویژه (نیاز به دعوت)" if item['requires_invite'] else "عمومی"
    toggle_text = "تغییر به عمومی" if item['requires_invite'] else "تغییر به ویژه"
    keyboard = [
        [InlineKeyboardButton("✏️ ویرایش عنوان", callback_data="edit_opt_title")],
        [InlineKeyboardButton("✏️ ویرایش توضیحات", callback_data="edit_opt_desc")],
        [InlineKeyboardButton("✏️ ویرایش دسته‌بندی‌ها", callback_data="edit_opt_cats")],
        [InlineKeyboardButton("✏️ ویرایش هشتگ‌ها", callback_data="edit_opt_tags")],
        [InlineKeyboardButton("✏️ ویرایش فایل‌ها", callback_data="edit_opt_files")],
        [InlineKeyboardButton(f"🔄 {toggle_text}", callback_data=f"edit_opt_toggle_invite_{item_id}")],
        [InlineKeyboardButton("🚪 خروج از ویرایش", callback_data="cancel_edit")]
    ]
    text = f"آیتم: <b>{item['title']}</b>\nوضعیت دعوت: <b>{status_text}</b>\n\nکدام بخش ویرایش شود؟"
    if from_sub_handler:
        await message.reply_html(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return EDIT_ITEM_OPTIONS

async def edit_item_options_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = query.data
    item_id = context.user_data['edit_item_id']
    if action == "edit_opt_title":
        await query.message.reply_text("عنوان جدید را ارسال کنید (برای رد شدن /skip):")
        return AWAIT_NEW_TITLE
    elif action == "edit_opt_desc":
        await query.message.reply_text("توضیحات جدید را ارسال کنید (برای رد شدن /skip):")
        return AWAIT_NEW_DESCRIPTION
    elif action == "edit_opt_cats":
        with get_db_connection() as conn:
            cat_rows = conn.execute("SELECT c.name FROM categories c JOIN item_categories ic ON c.id = ic.category_id WHERE ic.item_id = ?", (item_id,)).fetchall()
            current_cats = ", ".join([f"#{c['name']}" for c in cat_rows]) if cat_rows else "<i>(بدون دسته‌بندی)</i>"
        await query.message.reply_html(f"دسته‌بندی(های) فعلی: {current_cats}\n\nاکنون **لیست کامل و جدید دسته‌بندی‌ها** را ارسال کنید. برای رد شدن /skip بفرستید.")
        return AWAIT_NEW_CATEGORIES
    elif action == "edit_opt_tags":
        with get_db_connection() as conn:
            tag_rows = conn.execute("SELECT t.tag_name FROM tags t JOIN item_tags it ON t.id = it.tag_id WHERE it.item_id = ?", (item_id,)).fetchall()
            current_tags = " ".join([f"#{t['tag_name']}" for t in tag_rows]) if tag_rows else "<i>(بدون هشتگ)</i>"
        await query.message.reply_html(f"هشتگ(های) فعلی: {current_tags}\n\nاکنون **لیست کامل و جدید هشتگ‌ها** را با # ارسال کنید. برای رد شدن /skip بفرستید.")
        return AWAIT_NEW_TAGS
    elif action == "edit_opt_files":
        await query.message.reply_text("فایل(های) جدید را برای جایگزینی ارسال کنید و در انتها /done را بزنید.\nبرای لغو /cancel را بفرستید.")
        return AWAIT_NEW_FILES_FOR_EDIT
    elif action.startswith("edit_opt_toggle_invite_"):
        with get_db_connection() as conn:
            current_status = conn.execute("SELECT requires_invite FROM items WHERE id = ?", (item_id,)).fetchone()['requires_invite']
            new_status = 0 if current_status == 1 else 1
            conn.execute("UPDATE items SET requires_invite = ? WHERE id = ?", (new_status, item_id))
            conn.commit()
        await query.edit_message_text("✅ وضعیت ویژه بودن آیتم با موفقیت تغییر کرد.")
        await asyncio.sleep(1)
        await select_item_to_edit_handler(update, context)
        return EDIT_ITEM_OPTIONS

async def get_new_item_title_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    item_id = context.user_data['edit_item_id']
    if update.message.text.strip().lower() == '/skip':
        await update.message.reply_text("عنوان تغییر نکرد.")
    else:
        new_title = update.message.text
        with get_db_connection() as conn:
            conn.execute("UPDATE items SET title = ? WHERE id = ?", (new_title, item_id))
            conn.execute("UPDATE items_fts SET title = ? WHERE rowid = ?", (new_title, item_id))
            conn.commit()
        await update.message.reply_text("✅ عنوان با موفقیت ویرایش شد.")
    await select_item_to_edit_handler(update, context, from_sub_handler=True)
    return EDIT_ITEM_OPTIONS

async def get_new_item_description_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    item_id = context.user_data['edit_item_id']
    if update.message.text.strip().lower() == '/skip':
        await update.message.reply_text("توضیحات تغییر نکرد.")
    else:
        new_description = update.message.text
        with get_db_connection() as conn:
            conn.execute("UPDATE items SET description = ? WHERE id = ?", (new_description, item_id))
            conn.execute("UPDATE items_fts SET description = ? WHERE rowid = ?", (new_description, item_id))
            conn.commit()
        await update.message.reply_text("✅ توضیحات با موفقیت ویرایش شد.")
    await select_item_to_edit_handler(update, context, from_sub_handler=True)
    return EDIT_ITEM_OPTIONS

async def get_new_item_categories_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    item_id = context.user_data['edit_item_id']
    if update.message.text.strip().lower() == '/skip':
        await update.message.reply_text("دسته‌بندی‌ها تغییر نکردند.")
    else:
        new_categories_text = update.message.text
        new_categories = [c.strip() for c in new_categories_text.split('#') if c.strip()]
        if not new_categories:
            await update.message.reply_text("خطا: حداقل یک دسته‌بندی باید وارد شود.")
        else:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM item_categories WHERE item_id = ?", (item_id,))
                for cat_path_str in new_categories:
                    path_parts = [part.strip() for part in cat_path_str.split('>') if part.strip()]
                    if not path_parts: continue
                    current_parent_id = None
                    final_category_id = None
                    for part in path_parts:
                        query = "SELECT id FROM categories WHERE name = ? AND " + ("parent_id IS NULL" if current_parent_id is None else "parent_id = ?")
                        params = (part,) if current_parent_id is None else (part, current_parent_id)
                        cat_row = cursor.execute(query, params).fetchone()
                        if cat_row:
                            final_category_id = cat_row['id']
                        else:
                            cursor.execute("INSERT INTO categories (name, parent_id) VALUES (?, ?)", (part, current_parent_id))
                            final_category_id = cursor.lastrowid
                        current_parent_id = final_category_id
                    if final_category_id:
                        cursor.execute("INSERT OR IGNORE INTO item_categories (item_id, category_id) VALUES (?, ?)", (item_id, final_category_id))
                conn.commit()
            await update.message.reply_text("✅ دسته‌بندی‌ها با موفقیت ویرایش شدند.")
    await select_item_to_edit_handler(update, context, from_sub_handler=True)
    return EDIT_ITEM_OPTIONS

async def get_new_item_tags_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    item_id = context.user_data['edit_item_id']
    if update.message.text.strip().lower() == '/skip':
        await update.message.reply_text("هشتگ‌ها تغییر نکردند.")
    else:
        tags_list = [t.strip().lower() for t in update.message.text.split('#') if t.strip()]
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM item_tags WHERE item_id = ?", (item_id,))
            for tag_name in tags_list:
                cursor.execute("INSERT OR IGNORE INTO tags (tag_name) VALUES (?)", (tag_name,))
                tag_id = cursor.execute("SELECT id FROM tags WHERE tag_name = ?", (tag_name,)).fetchone()['id']
                cursor.execute("INSERT INTO item_tags (item_id, tag_id) VALUES (?, ?)", (item_id, tag_id))
            item_data = cursor.execute("SELECT title, description FROM items WHERE id = ?", (item_id,)).fetchone()
            tags_str = ' '.join(tags_list)
            cursor.execute("INSERT OR REPLACE INTO items_fts (rowid, title, description, tags) VALUES (?, ?, ?, ?)",
                           (item_id, item_data['title'], item_data['description'], tags_str))
            conn.commit()
        await update.message.reply_text("✅ هشتگ‌ها با موفقیت ویرایش شدند.")
    await select_item_to_edit_handler(update, context, from_sub_handler=True)
    return EDIT_ITEM_OPTIONS

async def skip_file_edit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("✅ فایل‌ها تغییری نکردند. فرآیند ویرایش با موفقیت تکمیل شد.")
    return await end_conversation_and_start(update, context)

async def edit_item_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    item_id = context.user_data['edit_item_id']
    if not context.user_data.get('edit_files_cleared', False):
        with get_db_connection() as conn:
            conn.execute("DELETE FROM item_files WHERE item_id = ?", (item_id,))
            conn.commit()
        context.user_data['edit_files_cleared'] = True
        context.user_data['edit_part_counter'] = 1
        await update.message.reply_text("🗑 فایل‌های قدیمی حذف شدند. در حال افزودن فایل‌های جدید...")
    part_order = context.user_data.get('edit_part_counter', 1)
    attachment = update.message.document or update.message.video or update.message.audio or (update.message.photo[-1] if update.message.photo else None)
    if not attachment: return
    try:
        sent_message = await update.message.forward(chat_id=CHANNEL_ID)
        with get_db_connection() as conn:
            conn.execute("INSERT INTO item_files (item_id, part_order, channel_message_id, file_id, file_unique_id) VALUES (?, ?, ?, ?, ?)",
                         (item_id, part_order, sent_message.message_id, attachment.file_id, attachment.file_unique_id))
            conn.commit()
        await update.message.reply_text(f"فایل بخش {part_order} اضافه شد. فایل بعدی یا /done.")
        context.user_data['edit_part_counter'] += 1
    except Exception as e:
        logger.error(f"Error adding new file for item {item_id}: {e}", exc_info=True)
        await update.message.reply_text(f"خطا در ذخیره فایل جدید: {e}")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['state'] = 'awaiting_broadcast_message'; await update.message.reply_text("محتوای broadcast را ارسال کنید (/cancel_broadcast برای لغو).")

async def handle_broadcast_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['broadcast_message_id'] = update.message.message_id; context.user_data['broadcast_chat_id'] = update.message.chat_id
    with get_db_connection() as conn: user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    keyboard = [[InlineKeyboardButton("✅ بله، ارسال کن", callback_data=BROADCAST_CONFIRM)], [InlineKeyboardButton("❌ خیر، لغو کن", callback_data=BROADCAST_CANCEL)]]
    await update.message.reply_text(f"این پیام برای **{user_count}** کاربر ارسال خواهد شد. مطمئن هستید؟", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    context.user_data['state'] = 'awaiting_broadcast_confirmation'

async def broadcast_confirmation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer(); action = query.data
    if action == BROADCAST_CANCEL: context.user_data.clear(); await query.edit_message_text("ارسال همگانی لغو شد."); return
    if action == BROADCAST_CONFIRM:
        message_id, from_chat_id, admin_id = context.user_data.get('broadcast_message_id'), context.user_data.get('broadcast_chat_id'), query.from_user.id
        if not message_id or not from_chat_id: await query.edit_message_text("خطا: پیام اصلی یافت نشد."); return
        broadcast_id = query.message.message_id
        with get_db_connection() as conn:
            users = conn.execute("SELECT user_id FROM users").fetchall()
            broadcast_data = [(broadcast_id, admin_id, message_id, from_chat_id, user['user_id']) for user in users]
            conn.executemany("INSERT INTO broadcast_queue (broadcast_id, admin_id, admin_message_id, from_chat_id, user_id) VALUES (?, ?, ?, ?, ?)", broadcast_data); conn.commit()
        context.user_data.clear(); await query.edit_message_text(f"✅ تایید شد. ارسال برای {len(users)} کاربر آغاز شد.")

async def process_broadcast_queue(context: ContextTypes.DEFAULT_TYPE):
    with get_db_connection() as conn:
        pending_messages = conn.execute("SELECT * FROM broadcast_queue WHERE status = 'pending' LIMIT 30").fetchall()
        if pending_messages:
            sent, blocked, failed = 0, 0, 0
            for msg in pending_messages:
                status = 'sent'
                try: await context.bot.copy_message(chat_id=msg['user_id'], from_chat_id=msg['from_chat_id'], message_id=msg['admin_message_id']); sent += 1
                except Forbidden: status = 'blocked'; blocked += 1
                except TelegramError as e: status = 'failed'; failed += 1; logger.error(f"Broadcast fail to {msg['user_id']}: {e}")
                conn.execute("UPDATE broadcast_queue SET status = ? WHERE id = ?", (status, msg['id'])); await asyncio.sleep(0.05)
            conn.commit(); logger.info(f"Broadcast batch: {sent} sent, {blocked} blocked, {failed} failed.")
        completed_broadcasts = conn.execute("SELECT broadcast_id, admin_id FROM broadcast_queue WHERE broadcast_id NOT IN (SELECT DISTINCT broadcast_id FROM broadcast_queue WHERE status = 'pending') GROUP BY broadcast_id").fetchall()
        for completed in completed_broadcasts:
            b_id, admin_id = completed['broadcast_id'], completed['admin_id']
            stats = conn.execute("SELECT status, COUNT(*) as count FROM broadcast_queue WHERE broadcast_id = ? GROUP BY status", (b_id,)).fetchall()
            total, sent, blocked, failed = 0, 0, 0, 0
            for row in stats:
                count = row['count']; total += count
                if row['status'] == 'sent': sent = count
                elif row['status'] == 'blocked': blocked = count
                elif row['status'] == 'failed': failed = count
            report = f"📣 گزارش ارسال همگانی (ID: {b_id}):\n\n👥 کل: {total}\n✅ موفق: {sent}\n🚫 بلاک: {blocked}\n❌ ناموفق: {failed}"
            try: await context.bot.send_message(chat_id=admin_id, text=report)
            except Exception as e: logger.error(f"Fail to send report to admin {admin_id}: {e}")
            conn.execute("DELETE FROM broadcast_queue WHERE broadcast_id = ?", (b_id,)); conn.commit()

async def cancel_broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear(); await update.message.reply_text("عملیات ارسال همگانی لغو شد.");
    await show_main_menu(update, context)

async def manage_categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data['state'] = 'managing_categories'
    context.user_data['manage_cat_path'] = [0]
    await send_category_management_menu(update, context, new_message=True)
    return 'managing_categories'

async def send_category_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, new_message: bool = False):
    parent_id = context.user_data.get('manage_cat_path', [0])[-1]; chat = update.effective_chat; move_mode = context.user_data.get('move_mode', False)
    with get_db_connection() as conn:
        sub_cats_q = "SELECT id, name FROM categories WHERE parent_id " + ("=?" if parent_id != 0 else "IS NULL") + " ORDER BY name"
        sub_cats = conn.execute(sub_cats_q, (parent_id,) if parent_id != 0 else ()).fetchall()
        curr_name = conn.execute("SELECT name FROM categories WHERE id = ?", (parent_id,)).fetchone()['name'] if parent_id != 0 else "ریشه (منوی اصلی)"
    keyboard = [[InlineKeyboardButton(f"📁 {cat['name']}", callback_data=f"cat_manage_{cat['id']}")] for cat in sub_cats]
    nav_btns = [InlineKeyboardButton("🔙 بازگشت", callback_data="manage_back")] if parent_id != 0 else []
    keyboard.append(nav_btns + [InlineKeyboardButton("🚪 خروج", callback_data="manage_exit")])
    if move_mode:
        text = f"جابجایی: <b>{context.user_data.get('category_to_move_name', '')}</b>\nمقصد را برای انتقال انتخاب کنید:"
        if parent_id != context.user_data.get('category_to_move_id'):
            keyboard.append([InlineKeyboardButton(f"📍 انتقال به اینجا ({html.escape(curr_name)})", callback_data=f"move_here_{parent_id}")])
        keyboard.append([InlineKeyboardButton("📤 انتقال به ریشه", callback_data="move_to_root"), InlineKeyboardButton("❌ لغو جابجایی", callback_data="cancel_move")])
    else:
        text = f"پنل مدیریت - در شاخه: <b>{html.escape(curr_name)}</b>"
        action_buttons = [InlineKeyboardButton("➕ افزودن زیرشاخه", callback_data=f"add_sub_cat_{parent_id}")]
        if parent_id != 0: 
            action_buttons += [
                InlineKeyboardButton("✏️ ویرایش نام", callback_data=f"edit_cat_{parent_id}"), 
                InlineKeyboardButton("❌ حذف شاخه", callback_data=f"delete_cat_{parent_id}"), 
                InlineKeyboardButton("↔️ جابجایی", callback_data=f"move_cat_{parent_id}")
            ]
        keyboard.append(action_buttons)
        keyboard.append([InlineKeyboardButton("⚙️ مدیریت دکمه‌های این بخش", callback_data=f"manage_buttons_for_cat_{parent_id}")])
    reply_markup=InlineKeyboardMarkup(keyboard)
    if new_message: await chat.send_message(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    elif update.callback_query: await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def manage_categories_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer(); data = query.data; path = context.user_data.get('manage_cat_path', [0])
    if data.startswith("cat_manage_"): path.append(int(data.split('_')[-1])); await send_category_management_menu(update, context)
    elif data == "manage_back":
        if len(path) > 1: path.pop()
        await send_category_management_menu(update, context)
    elif data == "manage_exit": await query.edit_message_text("خروج از مدیریت."); context.user_data.clear(); await show_main_menu(update, context); return ConversationHandler.END
    elif data.startswith("add_sub_cat_"): parent_id = int(data.split('_')[-1]); context.user_data['state'] = f"awaiting_new_category_name_{parent_id}"; await query.edit_message_text("نام دسته‌بندی جدید:")
    elif data.startswith("edit_cat_"): cat_id = int(data.split('_')[-1]); context.user_data['state'] = f"awaiting_edited_category_name_{cat_id}"; await query.edit_message_text("نام جدید:")
    elif data.startswith("delete_cat_"):
        cat_id = int(data.split('_')[-1])
        with get_db_connection() as conn: cat = conn.execute("SELECT name FROM categories WHERE id = ?", (cat_id,)).fetchone()
        if cat:
            kbd = [[InlineKeyboardButton("✅ بله، حذف کن", callback_data=f"{CONFIRM_DELETE_CAT_PREFIX}{cat_id}")], [InlineKeyboardButton("❌ لغو", callback_data=CANCEL_ACTION)]]
            await query.edit_message_text(f"⚠️ از حذف دسته‌بندی «{html.escape(cat['name'])}» و تمام زیرشاخه‌های آن مطمئنید؟ این عمل دائمی است.", reply_markup=InlineKeyboardMarkup(kbd))
    elif data.startswith(CONFIRM_DELETE_CAT_PREFIX):
        cat_id = int(data.split('_')[-1])
        with get_db_connection() as conn:
            conn.execute("DELETE FROM categories WHERE id = ?", (cat_id,)); conn.commit()
        await query.edit_message_text("دسته‌بندی با موفقیت حذف شد.")
        await asyncio.sleep(1)
        await send_category_management_menu(update, context)
    elif data.startswith("move_cat_"):
        cat_id = int(data.split('_')[-1])
        with get_db_connection() as conn: cat_name = conn.execute("SELECT name FROM categories WHERE id=?", (cat_id,)).fetchone()['name']
        context.user_data.update({'move_mode': True, 'category_to_move_id': cat_id, 'category_to_move_name': cat_name}); await send_category_management_menu(update, context)
    elif data.startswith("move_here_") or data == "move_to_root":
        src_id, dest_id = context.user_data.get('category_to_move_id'), int(data.split('_')[-1]) if data.startswith("move_here_") else None
        with get_db_connection() as conn:
            if dest_id and (src_id == dest_id or is_descendant(conn, dest_id, src_id)): await query.answer("❌ انتقال غیرمجاز.", show_alert=True); return
            try: conn.execute("UPDATE categories SET parent_id = ? WHERE id = ?", (dest_id, src_id)); conn.commit(); await query.answer("✅ جابجا شد.")
            except sqlite3.IntegrityError: await query.answer("❌ نام تکراری در مقصد.", show_alert=True)
        context.user_data.pop('move_mode', None); await send_category_management_menu(update, context)
    elif data == "cancel_move": context.user_data.pop('move_mode', None); await send_category_management_menu(update, context)

async def handle_manage_category_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip(); state = context.user_data.get('state', '')
    id_part = int(re.search(r'\d+$', state).group())
    try:
        with get_db_connection() as conn:
            if state.startswith("awaiting_new_category_name_"): conn.execute("INSERT INTO categories (name, parent_id) VALUES (?, ?)", (text, id_part if id_part != 0 else None)); await update.message.reply_text(f"دسته‌بندی '{text}' اضافه شد.")
            elif state.startswith("awaiting_edited_category_name_"): conn.execute("UPDATE categories SET name = ? WHERE id = ?", (text, id_part)); await update.message.reply_text("نام ویرایش شد.")
            conn.commit()
    except sqlite3.IntegrityError: await update.message.reply_text("خطا: نام تکراری.")
    context.user_data['state'] = 'managing_categories'; await send_category_management_menu(update, context, new_message=True)

async def set_caption_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    with get_db_connection() as conn:
        current_caption = conn.execute("SELECT value FROM config WHERE key = 'global_caption_text'").fetchone()
    current_text = current_caption['value'] if current_caption and current_caption['value'] else "<i>(تنظیم نشده)</i>"
    await update.message.reply_html(
        f"⚙️ **تنظیم پاورقی سراسری**\n\n"
        f"<b>پاورقی فعلی:</b>\n{current_text}\n\n"
        f"لطفاً متن جدید را ارسال کنید. برای حذف پاورقی فعلی، دستور /clear_caption را بفرستید.",
        reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True)
    )
    return AWAIT_CAPTION_TEXT

async def get_new_caption_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_caption = update.message.text
    with get_db_connection() as conn:
        conn.execute("UPDATE config SET value = ? WHERE key = 'global_caption_text'", (new_caption,))
        conn.commit()
    await update.message.reply_html(f"✅ پاورقی سراسری با موفقیت به متن زیر تغییر یافت:\n\n{html.escape(new_caption)}")
    return await end_conversation_and_start(update, context)

async def clear_caption_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    with get_db_connection() as conn:
        conn.execute("UPDATE config SET value = '' WHERE key = 'global_caption_text'")
        conn.commit()
    await update.message.reply_text("✅ پاورقی سراسری با موفقیت حذف شد.")
    return await end_conversation_and_start(update, context)

async def cancel_set_caption(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("عملیات تنظیم پاورقی لغو شد.", reply_markup=ReplyKeyboardRemove())
    return await end_conversation_and_start(update, context)

async def archive_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("برای یافتن آیتم جهت بایگانی، نام آن را وارد کنید (فقط موارد فعال نمایش داده می‌شوند):", reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True))
    return SEARCH_ITEM_TO_ARCHIVE

async def find_item_to_archive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.message.text.strip()
    with get_db_connection() as conn:
        items = conn.execute("SELECT id, title, type FROM items WHERE title LIKE ? AND status = 'active' ORDER BY title LIMIT 20", (f'%{query}%',)).fetchall()
    if not items:
        await update.message.reply_text(f"مورد فعالی با نام '{html.escape(query)}' یافت نشد.")
        return SEARCH_ITEM_TO_ARCHIVE
    keyboard = [[InlineKeyboardButton(f"🗄️ {item['type']}: {item['title']}", callback_data=f"archive_select_{item['id']}")] for item in items]
    keyboard.append([InlineKeyboardButton("❌ لغو", callback_data="cancel_archive")])
    await update.message.reply_text("کدام مورد بایگانی شود؟", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_ITEM_TO_ARCHIVE

async def select_item_to_archive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    item_id = int(query.data.split('_')[-1])
    context.user_data['item_to_archive_id'] = item_id
    with get_db_connection() as conn:
        item = conn.execute("SELECT title FROM items WHERE id = ?", (item_id,)).fetchone()
    await query.edit_message_text(f"آیتم: {item['title']}\n\nلطفاً دلیل بایگانی شدن را بنویسید. این پیام به کاربران نمایش داده خواهد شد.")
    return AWAIT_ARCHIVE_REASON

async def get_archive_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reason = update.message.text
    item_id = context.user_data['item_to_archive_id']
    with get_db_connection() as conn:
        conn.execute("UPDATE items SET status = 'archived', archive_reason = ? WHERE id = ?", (reason, item_id))
        conn.commit()
    await update.message.reply_text("✅ آیتم با موفقیت بایگانی شد و دیگر برای کاربران قابل دانلود نیست.")
    return await end_conversation_and_start(update, context)

async def unarchive_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("برای یافتن آیتم جهت بازگردانی، نام آن را وارد کنید (فقط موارد بایگانی شده نمایش داده می‌شوند):", reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True))
    return SEARCH_ITEM_TO_UNARCHIVE

async def find_item_to_unarchive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.message.text.strip()
    with get_db_connection() as conn:
        items = conn.execute("SELECT id, title, type FROM items WHERE title LIKE ? AND status = 'archived' ORDER BY title LIMIT 20", (f'%{query}%',)).fetchall()
    if not items:
        await update.message.reply_text(f"مورد بایگانی شده‌ای با نام '{html.escape(query)}' یافت نشد.")
        return SEARCH_ITEM_TO_UNARCHIVE
    keyboard = [[InlineKeyboardButton(f"🔄 {item['type']}: {item['title']}", callback_data=f"unarchive_select_{item['id']}")] for item in items]
    keyboard.append([InlineKeyboardButton("❌ لغو", callback_data="cancel_archive")])
    await update.message.reply_text("کدام مورد به حالت فعال بازگردانده شود؟", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_ITEM_TO_UNARCHIVE

async def do_unarchive_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    item_id = int(query.data.split('_')[-1])
    with get_db_connection() as conn:
        conn.execute("UPDATE items SET status = 'active', archive_reason = NULL WHERE id = ?", (item_id,))
        conn.commit()
    await query.edit_message_text("✅ آیتم با موفقیت به حالت فعال بازگردانده شد و برای کاربران قابل دسترس است.")
    await show_main_menu(update, context)
    return ConversationHandler.END

async def stats_command_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    with get_db_connection() as conn:
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        total_categories = conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
    simple_stats_text = (
        f"📊 **آمار کلی ربات**\n"
        f"👥 تعداد کل کاربران: {total_users}\n"
        f"📚 تعداد کل آیتم‌ها: {total_items}\n"
        f"📁 تعداد کل دسته‌بندی‌ها: {total_categories}\n"
    )
    advanced_panel_text = "<b>⚙️ پنل آمار پیشرفته</b>\nلطفا گزارش مورد نظر خود را انتخاب کنید:"
    final_text = simple_stats_text + advanced_panel_text
    keyboard = [
        [InlineKeyboardButton("📊 محبوب‌ترین آیتم‌ها", callback_data="stats_popular_items")],
        [InlineKeyboardButton("👥 فعال‌ترین کاربران", callback_data="stats_active_users")],
        [InlineKeyboardButton("🔍 جستجوهای ناموفق", callback_data="stats_failed_searches")],
        [InlineKeyboardButton("🚪 خروج", callback_data="stats_exit")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_html(final_text, reply_markup=reply_markup)
    return STATS_MENU

async def stats_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = query.data
    text = ""
    if action == "stats_popular_items":
        with get_db_connection() as conn:
            rows = conn.execute("""
                SELECT i.title, COUNT(d.item_id) as count
                FROM download_log d
                JOIN items i ON d.item_id = i.id
                GROUP BY d.item_id
                ORDER BY count DESC
                LIMIT 10
            """).fetchall()
        text = "<b>📊 10 آیتم محبوب بر اساس تعداد دانلود:</b>\n\n"
        if not rows:
            text += "<i>هنوز هیچ دانلودی ثبت نشده است.</i>"
        else:
            for i, row in enumerate(rows):
                text += f"{i+1}. {html.escape(row['title'])} (تعداد دانلود: {row['count']})\n"
    elif action == "stats_active_users":
        text = "<b>👥 10 کاربر فعال بر اساس تعداد دانلود:</b>\n\n"
        with get_db_connection() as conn:
            rows = conn.execute("""
                SELECT user_id, COUNT(user_id) as count
                FROM download_log
                GROUP BY user_id
                ORDER BY count DESC
                LIMIT 10
            """).fetchall()
        if not rows:
            text += "<i>هنوز هیچ دانلودی ثبت نشده است.</i>"
        else:
            for i, row in enumerate(rows):
                user_id = row['user_id']
                text += f"{i+1}. کاربر <a href='tg://user?id={user_id}'>{user_id}</a> (تعداد دانلود: {row['count']})\n"
    elif action == "stats_failed_searches":
        text = "<b>🔍 20 جستجوی ناموفق پرتکرار:</b>\n\n"
        with get_db_connection() as conn:
            rows = conn.execute("""
                SELECT query_text, COUNT(query_text) as count
                FROM search_log
                WHERE was_successful = 0
                GROUP BY query_text
                ORDER BY count DESC
                LIMIT 20
            """).fetchall()
        if not rows:
            text += "<i>هیچ جستجوی ناموفقی ثبت نشده است.</i>"
        else:
            for i, row in enumerate(rows):
                text += f"{i+1}. \"{html.escape(row['query_text'])}\" (تکرار: {row['count']})\n"
    elif action == "stats_exit":
        await query.edit_message_text("✅ از پنل آمار خارج شدید.")
        return ConversationHandler.END
    keyboard = [[InlineKeyboardButton("🔙 بازگشت به منوی آمار", callback_data="stats_back_to_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return STATS_MENU

async def stats_back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("📊 محبوب‌ترین آیتم‌ها", callback_data="stats_popular_items")],
        [InlineKeyboardButton("👥 فعال‌ترین کاربران", callback_data="stats_active_users")],
        [InlineKeyboardButton("🔍 جستجوهای ناموفق", callback_data="stats_failed_searches")],
        [InlineKeyboardButton("🚪 خروج", callback_data="stats_exit")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("<b>⚙️ پنل آمار پیشرفته</b>\n\nلطفا گزارش مورد نظر خود را انتخاب کنید:", reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    return STATS_MENU

async def set_threshold_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("لطفاً تعداد دعوت لازم را بعد از دستور وارد کنید.\nمثال: `/set_threshold 5`")
        return
    try:
        new_threshold = int(context.args[0])
        if new_threshold < 1:
            await update.message.reply_text("❌ عدد باید بزرگتر از صفر باشد.")
            return
        with get_db_connection() as conn:
            conn.execute("UPDATE config SET value = ? WHERE key = 'referral_threshold'", (str(new_threshold),))
            conn.commit()
        await update.message.reply_text(f"✅ حد نصاب دعوت برای دسترسی ویژه با موفقیت به **{new_threshold}** تغییر یافت.")
    except (ValueError, IndexError):
        await update.message.reply_text("❌ ورودی نامعتبر است. لطفاً یک عدد صحیح وارد کنید.")
    except Exception as e:
        logger.error(f"Error in set_threshold_command: {e}")
        await update.message.reply_text(f"❌ خطایی رخ داد: {e}")

async def exempt_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("لطفاً شناسه عددی کاربر را برای معاف کردن وارد کنید.\nمثال: `/exempt 12345678`")
        return
    try:
        user_id_to_exempt = int(context.args[0])
        with get_db_connection() as conn:
            user = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id_to_exempt,)).fetchone()
            if not user:
                conn.execute("INSERT INTO users (user_id, has_special_access) VALUES (?, 1)", (user_id_to_exempt,))
            else:
                conn.execute("UPDATE users SET has_special_access = 1 WHERE user_id = ?", (user_id_to_exempt,))
            conn.commit()
        await update.message.reply_text(f"✅ کاربر با شناسه `{user_id_to_exempt}` از نیاز به دعوت معاف شد و به محتوای ویژه دسترسی دارد.")
    except (ValueError, IndexError):
        await update.message.reply_text("❌ شناسه کاربر باید یک عدد صحیح باشد.")

async def unexempt_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("لطفاً شناسه عددی کاربر را برای لغو معافیت وارد کنید.\nمثال: `/unexempt 12345678`")
        return
    try:
        user_id_to_unexempt = int(context.args[0])
        with get_db_connection() as conn:
            conn.execute("UPDATE users SET has_special_access = 0 WHERE user_id = ?", (user_id_to_unexempt,))
            conn.commit()
        await update.message.reply_text(f"✅ معافیت کاربر با شناسه `{user_id_to_unexempt}` لغو شد.")
    except (ValueError, IndexError):
        await update.message.reply_text("❌ شناسه کاربر باید یک عدد صحیح باشد.")

async def reset_referrals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [[InlineKeyboardButton("✅ بله، مطمئنم و پاک کن", callback_data=RESET_REFERRALS_CONFIRM)], [InlineKeyboardButton("❌ خیر، لغو کن", callback_data=RESET_REFERRALS_CANCEL)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_html(
        "⚠️ **اخطار بسیار مهم!** ⚠️\n\n"
        "آیا از صفر کردن آمار دعوت تمام کاربران و پاک کردن تاریخچه دعوت‌ها مطمئن هستید؟\n\n"
        "با این کار، دسترسی ویژه تمام کاربرانی که از طریق دعوت به آن رسیده بودند لغو شده و باید دوباره دعوت را از صفر شروع کنند. **این عمل غیرقابل بازگشت است.**",
        reply_markup=reply_markup
    )
    return CONFIRM_RESET_REFERRALS

async def reset_referrals_confirmation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = query.data
    if action == RESET_REFERRALS_CANCEL:
        await query.edit_message_text("✅ عملیات پاکسازی لغو شد.")
        return ConversationHandler.END
    if action == RESET_REFERRALS_CONFIRM:
        try:
            with get_db_connection() as conn:
                conn.execute("UPDATE users SET successful_invites = 0, has_special_access = 0")
                conn.execute("DELETE FROM referrals")
                conn.commit()
            logger.warning(f"Admin {query.from_user.id} has reset all referral stats.")
            await query.edit_message_text("✅ سیستم دعوت با موفقیت پاکسازی و ریست شد.")
        except Exception as e:
            logger.error(f"Failed to reset referrals: {e}")
            await query.edit_message_text(f"❌ خطایی در هنگام پاکسازی رخ داد: {e}")
        return ConversationHandler.END
        
async def get_my_referral_code_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    bot_username = (await context.bot.get_me()).username
    my_referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    message_text = (
        "🔗 **لینک دعوت اختصاصی شما:**\n\n"
        f"`{my_referral_link}`\n\n"
        "این لینک را برای دوستان خود بفرستید. با عضویت هر نفر از طریق این لینک، یک قدم به باز کردن قفل تمام فایل‌های ویژه نزدیک‌تر می‌شوید."
    )
    await query.message.reply_text(message_text, parse_mode=ParseMode.MARKDOWN)

async def my_code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bot_username = (await context.bot.get_me()).username
    my_referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    message_text = (
        "🔗 **لینک دعوت اختصاصی شما:**\n\n"
        f"`{my_referral_link}`\n\n"
        "این لینک را برای دوستان خود بفرستید. با عضویت هر نفر از طریق این لینک، یک قدم به باز کردن قفل تمام فایل‌های ویژه نزدیک‌تر می‌شوید."
    )
    await update.message.reply_text(message_text, parse_mode=ParseMode.MARKDOWN)

def main() -> None:
    update_db_schema()
    init_db()
    application = Application.builder().token(TOKEN).build()
    admin_filter = filters.User(user_id=ADMIN_USER_IDS)
    shared_fallbacks = [
        CommandHandler("start", start),
        MessageHandler(filters.Text([MAIN_MENU_BUTTON, CANCEL_BUTTON]), end_conversation_and_start),
    ]
    reset_referrals_conv = ConversationHandler(
        entry_points=[CommandHandler("reset_referrals", reset_referrals_command, filters=admin_filter)],
        states={CONFIRM_RESET_REFERRALS: [CallbackQueryHandler(reset_referrals_confirmation_handler, pattern=f"^({RESET_REFERRALS_CONFIRM}|{RESET_REFERRALS_CANCEL})$")]},
        fallbacks=[CommandHandler("cancel", end_conversation_and_start)],
        conversation_timeout=300
    )
    add_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_command, filters=admin_filter)],
        states={
            CHOOSE_TYPE: [CallbackQueryHandler(add_choice_type, pattern="^add_type_")],
            GET_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_title)],
            GET_DESCRIPTION: [CommandHandler('skip', skip_description), MessageHandler(filters.TEXT & ~filters.COMMAND, get_description)],
            CHOOSE_CATEGORIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_categories)],
            GET_TAGS: [CommandHandler('skip', skip_tags), MessageHandler(filters.TEXT & ~filters.COMMAND, get_tags)],
            AWAIT_REQUIRES_INVITE: [CallbackQueryHandler(set_requires_invite_callback, pattern="^set_invite_")],
            AWAIT_FILES: [CommandHandler('done', done_command), MessageHandler(filters.ATTACHMENT & admin_filter, admin_file_handler)]
        },
        fallbacks=[CallbackQueryHandler(cancel_add, pattern="^cancel_add$"), CommandHandler("cancel", cancel_add)] + shared_fallbacks,
        per_message=False, conversation_timeout=1800, allow_reentry=True
    )
    edit_item_conv = ConversationHandler(
        entry_points=[CommandHandler("edit_item", edit_item_command, filters=admin_filter)],
        states={
            SEARCH_ITEM_TO_EDIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_item_to_edit_handler)],
            SELECT_ITEM_TO_EDIT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_item_to_edit_handler),
                CallbackQueryHandler(select_item_to_edit_handler, pattern="^select_edit_")
            ],
            EDIT_ITEM_OPTIONS: [CallbackQueryHandler(edit_item_options_handler, pattern="^edit_opt_")],
            AWAIT_NEW_TITLE: [CommandHandler("skip", get_new_item_title_handler), MessageHandler(filters.TEXT & ~filters.COMMAND, get_new_item_title_handler)],
            AWAIT_NEW_DESCRIPTION: [CommandHandler("skip", get_new_item_description_handler), MessageHandler(filters.TEXT & ~filters.COMMAND, get_new_item_description_handler)],
            AWAIT_NEW_CATEGORIES: [CommandHandler("skip", get_new_item_categories_handler), MessageHandler(filters.TEXT & ~filters.COMMAND, get_new_item_categories_handler)],
            AWAIT_NEW_TAGS: [CommandHandler("skip", get_new_item_tags_handler), MessageHandler(filters.TEXT & ~filters.COMMAND, get_new_item_tags_handler)],
            AWAIT_NEW_FILES_FOR_EDIT: [CommandHandler("done", done_command), CommandHandler("cancel", end_conversation_and_start), MessageHandler(filters.ATTACHMENT & admin_filter, edit_item_file_handler)],
        },
        fallbacks=[CallbackQueryHandler(end_conversation_and_start, pattern="^cancel_edit$"), CommandHandler("cancel", end_conversation_and_start)] + shared_fallbacks,
        per_message=False, conversation_timeout=1800, allow_reentry=True
    )
    stats_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("stats", stats_command_panel, filters=admin_filter)],
        states={STATS_MENU: [CommandHandler("stats", stats_command_panel, filters=admin_filter), CallbackQueryHandler(stats_menu_handler, pattern="^stats_(popular_items|active_users|failed_searches|exit)$"), CallbackQueryHandler(stats_back_to_menu, pattern="^stats_back_to_menu$")]},
        fallbacks=[CommandHandler("cancel", end_conversation_and_start)],
        per_message=False, conversation_timeout=600
    )
    manage_buttons_conv = ConversationHandler(
        entry_points=[CommandHandler("manage_button", manage_button_command, filters=admin_filter), CallbackQueryHandler(manage_buttons_for_category_entry, pattern="^manage_buttons_for_cat_")],
        states={
            LIST_BUTTONS: [CallbackQueryHandler(list_buttons_handler, pattern="^db_")],
            ACTION_CHOICE: [CallbackQueryHandler(action_choice_handler, pattern="^db_action_")],
            CONFIRM_DELETE: [CallbackQueryHandler(confirm_delete_handler, pattern="^db_confirm_delete_")],
            GET_NEW_LABEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_new_label_handler)],
            GET_NEW_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_new_message_handler)],
            GET_EDIT_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_edit_message_handler)],
        },
        fallbacks=[CommandHandler("cancel", end_conversation_and_start)] + shared_fallbacks,
        per_message=False, conversation_timeout=600, allow_reentry=True
    )
    manage_categories_conv = ConversationHandler(
        entry_points=[CommandHandler("manage_categories", manage_categories_command, filters=admin_filter)],
        states={'managing_categories': [CallbackQueryHandler(manage_categories_callback_handler, pattern=r"^(cat_manage_|manage_back|manage_exit|add_sub_cat_|edit_cat_|delete_cat_|confirm_del_cat_|move_cat_|move_here_|move_to_root|cancel_move)")]},
        fallbacks=[CommandHandler("cancel", end_conversation_and_start)] + shared_fallbacks,
        per_message=False, conversation_timeout=600, allow_reentry=True
    )
    conv_handlers = [
        add_conv_handler, edit_item_conv, reset_referrals_conv, stats_conv_handler, manage_buttons_conv, manage_categories_conv,
        ConversationHandler(entry_points=[CommandHandler("delete", delete_command, filters=admin_filter)], states={SEARCH_ITEM_TO_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, find_item_to_delete)], SELECT_ITEM_TO_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, find_item_to_delete), CallbackQueryHandler(confirm_delete_item_callback, pattern=f"^{CONFIRM_DELETE_PREFIX}"), CallbackQueryHandler(final_delete_item_callback, pattern=r"^final_delete_"), CallbackQueryHandler(cancel_delete_callback, pattern=r"^cancel_delete$"),]}, fallbacks=[CommandHandler("cancel", end_conversation_and_start)] + shared_fallbacks, per_message=False, conversation_timeout=600, allow_reentry=True),
        ConversationHandler(entry_points=[CommandHandler("manage_request_button", manage_request_button_command, filters=admin_filter)], states={REQUEST_BUTTON_MENU: [CallbackQueryHandler(request_button_menu_handler, pattern="^req_btn_")], AWAIT_NEW_REQUEST_LABEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_new_request_label_handler)]}, fallbacks=[CommandHandler("cancel", end_conversation_and_start)] + shared_fallbacks, per_message=False, conversation_timeout=600, allow_reentry=True),
        ConversationHandler(entry_points=[CommandHandler("manage_join", manage_join_command, filters=admin_filter)], states={MANAGE_JOIN_MENU: [CallbackQueryHandler(manage_join_callback_handler, pattern="^join_")], AWAIT_CHANNEL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_channel_id_handler)], AWAIT_CHANNEL_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_channel_link_handler)], AWAIT_CHANNEL_TO_REMOVE: [CallbackQueryHandler(remove_channel_callback_handler, pattern="^join_")]}, fallbacks=[CommandHandler("cancel", end_conversation_and_start)] + shared_fallbacks, per_message=False, conversation_timeout=600, allow_reentry=True),
        ConversationHandler(entry_points=[CommandHandler("set_caption", set_caption_command, filters=admin_filter)], states={AWAIT_CAPTION_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_new_caption_text), CommandHandler("clear_caption", clear_caption_text)]}, fallbacks=[CommandHandler("cancel", cancel_set_caption), MessageHandler(filters.Text([CANCEL_BUTTON]), cancel_set_caption)], per_message=False, conversation_timeout=300, allow_reentry=True),
        ConversationHandler(entry_points=[CommandHandler("manage_messages", manage_messages_command, filters=admin_filter)], states={MANAGE_MESSAGES_MENU: [CallbackQueryHandler(manage_messages_callback_handler, pattern="^edit_msg_")], AWAIT_WELCOME_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_new_welcome_message_handler)], AWAIT_MAIN_MENU_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_new_main_menu_message_handler)]}, fallbacks=[CommandHandler("cancel", end_conversation_and_start)] + shared_fallbacks, per_message=False, conversation_timeout=600, allow_reentry=True),
        ConversationHandler(entry_points=[CommandHandler("archive", archive_command, filters=admin_filter)], states={SEARCH_ITEM_TO_ARCHIVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, find_item_to_archive)], SELECT_ITEM_TO_ARCHIVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, find_item_to_archive), CallbackQueryHandler(select_item_to_archive, pattern="^archive_select_")], AWAIT_ARCHIVE_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_archive_reason)]}, fallbacks=[CallbackQueryHandler(end_conversation_and_start, pattern="^cancel_archive$"), CommandHandler("cancel", end_conversation_and_start)] + shared_fallbacks, per_message=False, conversation_timeout=600),
        ConversationHandler(entry_points=[CommandHandler("unarchive", unarchive_command, filters=admin_filter)], states={SEARCH_ITEM_TO_UNARCHIVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, find_item_to_unarchive)], SELECT_ITEM_TO_UNARCHIVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, find_item_to_unarchive), CallbackQueryHandler(do_unarchive_item, pattern="^unarchive_select_")]}, fallbacks=[CallbackQueryHandler(end_conversation_and_start, pattern="^cancel_archive$"), CommandHandler("cancel", end_conversation_and_start)] + shared_fallbacks, per_message=False, conversation_timeout=600),
    ]
    application.add_handlers(conv_handlers)
    admin_cmds = [
        "add", "delete", "manage_button", "manage_categories", "archive", "unarchive", "broadcast", "admin", "stats", 
        "edit_item", "manage_request_button", "manage_join", "set_caption", "backup", "manage_messages", "getid",
        "set_threshold", "exempt", "unexempt", "reset_referrals"
    ]
    application.add_handler(CommandHandler(admin_cmds, non_admin_access_denied, filters=~admin_filter))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler(["admin", "help"], admin_help_command, filters=admin_filter))
    application.add_handler(CommandHandler("broadcast", broadcast_command, filters=admin_filter))
    application.add_handler(CommandHandler("cancel_broadcast", cancel_broadcast_command, filters=admin_filter))
    application.add_handler(CommandHandler("backup", backup_command, filters=admin_filter))
    application.add_handler(CommandHandler("getid", get_id_command, filters=admin_filter))
    application.add_handler(CommandHandler("set_threshold", set_threshold_command, filters=admin_filter))
    application.add_handler(CommandHandler("exempt", exempt_command, filters=admin_filter))
    application.add_handler(CommandHandler("unexempt", unexempt_command, filters=admin_filter))
    application.add_handler(CommandHandler("mycode", my_code_command))
    application.add_handler(CallbackQueryHandler(broadcast_confirmation_handler, pattern=f"^({BROADCAST_CONFIRM}|{BROADCAST_CANCEL})$"))
    application.add_handler(CallbackQueryHandler(get_my_referral_code_callback, pattern=f"^{GET_REFERRAL_CODE_CALLBACK}$"))
    application.add_handler(CallbackQueryHandler(inline_button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, master_message_handler))
    application.job_queue.run_repeating(process_broadcast_queue, interval=15, first=10)
    application.job_queue.run_daily(daily_backup_job, time=time(hour=3, minute=30), job_kwargs={'misfire_grace_time': 3600})
    logger.info("ربات در حال اجراست...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()