#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
پنل مدیریت وب ربات کتابخانه تلگرام (ravanbookbot)
پورت پیش‌فرض: 13423
"""

from __future__ import annotations

import os
import sqlite3
import secrets
import shutil
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
    send_file,
    abort,
)
from werkzeug.security import generate_password_hash, check_password_hash

# ---------------------------------------------------------------------------
# پیکربندی
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("ADMIN_PANEL_SECRET", secrets.token_hex(32))
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)

SCRIPT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("DB_PATH", str(SCRIPT_DIR / "pdf_library.db")))
ADMIN_PASSWORD = os.getenv("ADMIN_PANEL_PASSWORD", "admin123")
# هش پسورد در استارت (برای مقایسه امن)
_PASSWORD_HASH = generate_password_hash(ADMIN_PASSWORD)

HOST = os.getenv("ADMIN_PANEL_HOST", "0.0.0.0")
PORT = int(os.getenv("ADMIN_PANEL_PORT", "13423"))


# ---------------------------------------------------------------------------
# دیتابیس
# ---------------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def query_all(sql: str, args=()):
    with get_db() as conn:
        return conn.execute(sql, args).fetchall()


def query_one(sql: str, args=()):
    with get_db() as conn:
        return conn.execute(sql, args).fetchone()


def execute(sql: str, args=()):
    with get_db() as conn:
        conn.execute(sql, args)
        conn.commit()


def execute_many(sql: str, args_list):
    with get_db() as conn:
        conn.executemany(sql, args_list)
        conn.commit()


# ---------------------------------------------------------------------------
# احراز هویت
# ---------------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)

    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if check_password_hash(_PASSWORD_HASH, password):
            session["logged_in"] = True
            session.permanent = True
            next_url = request.args.get("next") or url_for("dashboard")
            return redirect(next_url)
        error = "رمز عبور اشتباه است."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    flash("با موفقیت خارج شدید.", "info")
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# داشبورد و آمار
# ---------------------------------------------------------------------------
@app.route("/")
@login_required
def dashboard():
    stats = {}
    with get_db() as conn:
        stats["total_items"] = conn.execute(
            "SELECT COUNT(*) FROM items"
        ).fetchone()[0]
        stats["active_items"] = conn.execute(
            "SELECT COUNT(*) FROM items WHERE status = 'active'"
        ).fetchone()[0]
        stats["archived_items"] = conn.execute(
            "SELECT COUNT(*) FROM items WHERE status = 'archived'"
        ).fetchone()[0]
        stats["total_users"] = conn.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]
        stats["special_users"] = conn.execute(
            "SELECT COUNT(*) FROM users WHERE has_special_access = 1"
        ).fetchone()[0]
        stats["total_downloads"] = conn.execute(
            "SELECT COUNT(*) FROM download_log"
        ).fetchone()[0]
        stats["total_searches"] = conn.execute(
            "SELECT COUNT(*) FROM search_log"
        ).fetchone()[0]
        stats["successful_searches"] = conn.execute(
            "SELECT COUNT(*) FROM search_log WHERE was_successful = 1"
        ).fetchone()[0]
        stats["total_categories"] = conn.execute(
            "SELECT COUNT(*) FROM categories"
        ).fetchone()[0]
        stats["total_tags"] = conn.execute(
            "SELECT COUNT(*) FROM tags"
        ).fetchone()[0]
        stats["total_referrals"] = conn.execute(
            "SELECT COUNT(*) FROM referrals"
        ).fetchone()[0]
        stats["force_join_enabled"] = (
            conn.execute(
                "SELECT value FROM config WHERE key = 'force_join_enabled'"
            ).fetchone()
            or {"value": "0"}
        )["value"] == "1"
        stats["force_join_channels"] = conn.execute(
            "SELECT COUNT(*) FROM force_join_channels"
        ).fetchone()[0]

        # دانلودهای ۲۴ ساعت اخیر
        stats["downloads_24h"] = conn.execute(
            "SELECT COUNT(*) FROM download_log WHERE timestamp >= datetime('now', '-1 day')"
        ).fetchone()[0]
        stats["searches_24h"] = conn.execute(
            "SELECT COUNT(*) FROM search_log WHERE timestamp >= datetime('now', '-1 day')"
        ).fetchone()[0]
        stats["new_users_7d"] = conn.execute(
            """
            SELECT COUNT(DISTINCT user_id) FROM (
                SELECT user_id FROM download_log WHERE timestamp >= datetime('now', '-7 day')
                UNION
                SELECT user_id FROM search_log WHERE timestamp >= datetime('now', '-7 day')
            )
            """
        ).fetchone()[0]

        # برترین آیتم‌ها
        top_items = conn.execute(
            """
            SELECT i.id, i.title, i.type, COUNT(d.id) AS dl_count
            FROM items i
            LEFT JOIN download_log d ON d.item_id = i.id
            GROUP BY i.id
            ORDER BY dl_count DESC
            LIMIT 10
            """
        ).fetchall()

        # آخرین دانلودها
        recent_downloads = conn.execute(
            """
            SELECT d.timestamp, d.user_id, i.title, i.id AS item_id
            FROM download_log d
            JOIN items i ON i.id = d.item_id
            ORDER BY d.timestamp DESC
            LIMIT 15
            """
        ).fetchall()

        # آخرین جستجوها
        recent_searches = conn.execute(
            """
            SELECT query_text, was_successful, timestamp, user_id
            FROM search_log
            ORDER BY timestamp DESC
            LIMIT 15
            """
        ).fetchall()

        # کاربران با بیشترین دعوت
        top_referrers = conn.execute(
            """
            SELECT u.user_id, u.successful_invites, u.has_special_access
            FROM users u
            WHERE u.successful_invites > 0
            ORDER BY u.successful_invites DESC
            LIMIT 10
            """
        ).fetchall()

        # دانلود روزانه ۷ روز اخیر
        daily_downloads = conn.execute(
            """
            SELECT date(timestamp) AS day, COUNT(*) AS cnt
            FROM download_log
            WHERE timestamp >= datetime('now', '-7 day')
            GROUP BY date(timestamp)
            ORDER BY day
            """
        ).fetchall()

    return render_template(
        "dashboard.html",
        stats=stats,
        top_items=top_items,
        recent_downloads=recent_downloads,
        recent_searches=recent_searches,
        top_referrers=top_referrers,
        daily_downloads=daily_downloads,
    )


# ---------------------------------------------------------------------------
# مدیریت آیتم‌ها
# ---------------------------------------------------------------------------
@app.route("/items")
@login_required
def items_list():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "all")
    page = max(1, int(request.args.get("page", 1)))
    per_page = 30
    offset = (page - 1) * per_page

    where = ["1=1"]
    args = []
    if q:
        where.append("(title LIKE ? OR description LIKE ? OR CAST(id AS TEXT) = ?)")
        args.extend([f"%{q}%", f"%{q}%", q])
    if status in ("active", "archived"):
        where.append("status = ?")
        args.append(status)

    where_sql = " AND ".join(where)
    total = query_one(f"SELECT COUNT(*) AS c FROM items WHERE {where_sql}", args)["c"]
    items = query_all(
        f"""
        SELECT i.*,
               (SELECT COUNT(*) FROM item_files WHERE item_id = i.id) AS file_count,
               (SELECT COUNT(*) FROM download_log WHERE item_id = i.id) AS dl_count,
               (SELECT GROUP_CONCAT(c.name, ' › ') FROM categories c
                JOIN item_categories ic ON ic.category_id = c.id WHERE ic.item_id = i.id) AS cats
        FROM items i
        WHERE {where_sql}
        ORDER BY i.id DESC
        LIMIT ? OFFSET ?
        """,
        args + [per_page, offset],
    )
    total_pages = max(1, (total + per_page - 1) // per_page)
    return render_template(
        "items.html",
        items=items,
        q=q,
        status=status,
        page=page,
        total_pages=total_pages,
        total=total,
    )


@app.route("/items/<int:item_id>")
@login_required
def item_detail(item_id):
    item = query_one("SELECT * FROM items WHERE id = ?", (item_id,))
    if not item:
        abort(404)
    files = query_all(
        "SELECT * FROM item_files WHERE item_id = ? ORDER BY part_order", (item_id,)
    )
    categories = query_all(
        """
        SELECT c.* FROM categories c
        JOIN item_categories ic ON ic.category_id = c.id
        WHERE ic.item_id = ?
        """,
        (item_id,),
    )
    tags = query_all(
        """
        SELECT t.* FROM tags t
        JOIN item_tags it ON it.tag_id = t.id
        WHERE it.item_id = ?
        """,
        (item_id,),
    )
    all_categories = query_all("SELECT * FROM categories ORDER BY name")
    dl_count = query_one(
        "SELECT COUNT(*) AS c FROM download_log WHERE item_id = ?", (item_id,)
    )["c"]
    recent_dls = query_all(
        """
        SELECT user_id, timestamp FROM download_log
        WHERE item_id = ? ORDER BY timestamp DESC LIMIT 20
        """,
        (item_id,),
    )
    return render_template(
        "item_detail.html",
        item=item,
        files=files,
        categories=categories,
        tags=tags,
        all_categories=all_categories,
        dl_count=dl_count,
        recent_dls=recent_dls,
    )


@app.route("/items/<int:item_id>/edit", methods=["POST"])
@login_required
def item_edit(item_id):
    item = query_one("SELECT id FROM items WHERE id = ?", (item_id,))
    if not item:
        abort(404)
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    requires_invite = 1 if request.form.get("requires_invite") == "1" else 0
    status = request.form.get("status", "active")
    if status not in ("active", "archived"):
        status = "active"
    archive_reason = request.form.get("archive_reason", "").strip() or None
    if not title:
        flash("عنوان نمی‌تواند خالی باشد.", "danger")
        return redirect(url_for("item_detail", item_id=item_id))
    try:
        with get_db() as conn:
            conn.execute(
                """
                UPDATE items SET title=?, description=?, requires_invite=?, status=?, archive_reason=?
                WHERE id=?
                """,
                (title, description, requires_invite, status, archive_reason, item_id),
            )
            # دسته‌ها
            conn.execute("DELETE FROM item_categories WHERE item_id = ?", (item_id,))
            cat_ids = request.form.getlist("category_ids")
            for cid in cat_ids:
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO item_categories (item_id, category_id) VALUES (?, ?)",
                        (item_id, int(cid)),
                    )
                except ValueError:
                    pass
            # تگ‌ها
            tags_raw = request.form.get("tags", "").strip()
            conn.execute("DELETE FROM item_tags WHERE item_id = ?", (item_id,))
            if tags_raw:
                for tag_name in [t.strip() for t in tags_raw.replace("،", ",").split(",") if t.strip()]:
                    row = conn.execute(
                        "SELECT id FROM tags WHERE tag_name = ?", (tag_name,)
                    ).fetchone()
                    if row:
                        tid = row["id"]
                    else:
                        cur = conn.execute(
                            "INSERT INTO tags (tag_name) VALUES (?)", (tag_name,)
                        )
                        tid = cur.lastrowid
                    conn.execute(
                        "INSERT OR IGNORE INTO item_tags (item_id, tag_id) VALUES (?, ?)",
                        (item_id, tid),
                    )
            # به‌روزرسانی FTS
            try:
                tags_str = " ".join(
                    r["tag_name"]
                    for r in conn.execute(
                        """
                        SELECT t.tag_name FROM tags t
                        JOIN item_tags it ON it.tag_id = t.id WHERE it.item_id = ?
                        """,
                        (item_id,),
                    ).fetchall()
                )
                conn.execute("DELETE FROM items_fts WHERE rowid = ?", (item_id,))
                conn.execute(
                    "INSERT INTO items_fts (rowid, title, description, tags) VALUES (?, ?, ?, ?)",
                    (item_id, title, description, tags_str),
                )
            except sqlite3.Error:
                pass
            conn.commit()
        flash("آیتم با موفقیت به‌روزرسانی شد.", "success")
    except sqlite3.IntegrityError:
        flash("عنوان تکراری است. عنوان دیگری انتخاب کنید.", "danger")
    return redirect(url_for("item_detail", item_id=item_id))


@app.route("/items/<int:item_id>/delete", methods=["POST"])
@login_required
def item_delete(item_id):
    execute("DELETE FROM items WHERE id = ?", (item_id,))
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM items_fts WHERE rowid = ?", (item_id,))
            conn.commit()
    except sqlite3.Error:
        pass
    flash("آیتم حذف شد.", "success")
    return redirect(url_for("items_list"))


@app.route("/items/<int:item_id>/archive", methods=["POST"])
@login_required
def item_archive(item_id):
    reason = request.form.get("reason", "").strip() or "بایگانی از پنل وب"
    execute(
        "UPDATE items SET status='archived', archive_reason=? WHERE id=?",
        (reason, item_id),
    )
    flash("آیتم بایگانی شد.", "success")
    return redirect(url_for("item_detail", item_id=item_id))


@app.route("/items/<int:item_id>/unarchive", methods=["POST"])
@login_required
def item_unarchive(item_id):
    execute(
        "UPDATE items SET status='active', archive_reason=NULL WHERE id=?",
        (item_id,),
    )
    flash("آیتم از بایگانی خارج شد.", "success")
    return redirect(url_for("item_detail", item_id=item_id))


# ---------------------------------------------------------------------------
# دسته‌بندی‌ها
# ---------------------------------------------------------------------------
@app.route("/categories")
@login_required
def categories_list():
    cats = query_all(
        """
        SELECT c.*,
               p.name AS parent_name,
               (SELECT COUNT(*) FROM item_categories WHERE category_id = c.id) AS item_count,
               (SELECT COUNT(*) FROM categories WHERE parent_id = c.id) AS child_count
        FROM categories c
        LEFT JOIN categories p ON p.id = c.parent_id
        ORDER BY COALESCE(c.parent_id, c.id), c.name
        """
    )
    all_cats = query_all("SELECT id, name, parent_id FROM categories ORDER BY name")
    return render_template("categories.html", cats=cats, all_cats=all_cats)


@app.route("/categories/add", methods=["POST"])
@login_required
def category_add():
    name = request.form.get("name", "").strip()
    parent_id = request.form.get("parent_id") or None
    if parent_id:
        try:
            parent_id = int(parent_id)
        except ValueError:
            parent_id = None
    if not name:
        flash("نام دسته الزامی است.", "danger")
        return redirect(url_for("categories_list"))
    try:
        execute(
            "INSERT INTO categories (name, parent_id) VALUES (?, ?)",
            (name, parent_id),
        )
        flash("دسته اضافه شد.", "success")
    except sqlite3.IntegrityError:
        flash("این نام در همین سطح والد تکراری است.", "danger")
    return redirect(url_for("categories_list"))


@app.route("/categories/<int:cat_id>/edit", methods=["POST"])
@login_required
def category_edit(cat_id):
    name = request.form.get("name", "").strip()
    parent_id = request.form.get("parent_id") or None
    if parent_id:
        try:
            parent_id = int(parent_id)
            if parent_id == cat_id:
                flash("دسته نمی‌تواند والد خودش باشد.", "danger")
                return redirect(url_for("categories_list"))
        except ValueError:
            parent_id = None
    if not name:
        flash("نام الزامی است.", "danger")
        return redirect(url_for("categories_list"))
    try:
        execute(
            "UPDATE categories SET name=?, parent_id=? WHERE id=?",
            (name, parent_id, cat_id),
        )
        flash("دسته به‌روزرسانی شد.", "success")
    except sqlite3.IntegrityError:
        flash("نام تکراری است.", "danger")
    return redirect(url_for("categories_list"))


@app.route("/categories/<int:cat_id>/delete", methods=["POST"])
@login_required
def category_delete(cat_id):
    execute("DELETE FROM categories WHERE id = ?", (cat_id,))
    flash("دسته حذف شد.", "success")
    return redirect(url_for("categories_list"))


# ---------------------------------------------------------------------------
# کاربران و دعوت‌ها
# ---------------------------------------------------------------------------
@app.route("/users")
@login_required
def users_list():
    q = request.args.get("q", "").strip()
    filter_special = request.args.get("special", "")
    page = max(1, int(request.args.get("page", 1)))
    per_page = 40
    offset = (page - 1) * per_page

    where = ["1=1"]
    args = []
    if q:
        where.append("CAST(user_id AS TEXT) LIKE ?")
        args.append(f"%{q}%")
    if filter_special == "1":
        where.append("has_special_access = 1")
    elif filter_special == "0":
        where.append("has_special_access = 0")

    where_sql = " AND ".join(where)
    total = query_one(f"SELECT COUNT(*) AS c FROM users WHERE {where_sql}", args)["c"]
    users = query_all(
        f"""
        SELECT u.*,
               (SELECT COUNT(*) FROM download_log WHERE user_id = u.user_id) AS dl_count,
               (SELECT COUNT(*) FROM search_log WHERE user_id = u.user_id) AS search_count,
               (SELECT COUNT(*) FROM referrals WHERE referrer_id = u.user_id) AS ref_count
        FROM users u
        WHERE {where_sql}
        ORDER BY u.successful_invites DESC, u.user_id DESC
        LIMIT ? OFFSET ?
        """,
        args + [per_page, offset],
    )
    total_pages = max(1, (total + per_page - 1) // per_page)
    threshold = (
        query_one("SELECT value FROM config WHERE key = 'referral_threshold'")
        or {"value": "3"}
    )["value"]
    return render_template(
        "users.html",
        users=users,
        q=q,
        special=filter_special,
        page=page,
        total_pages=total_pages,
        total=total,
        threshold=threshold,
    )


@app.route("/users/<int:user_id>/toggle_special", methods=["POST"])
@login_required
def user_toggle_special(user_id):
    row = query_one("SELECT has_special_access FROM users WHERE user_id = ?", (user_id,))
    if not row:
        # اگر کاربر وجود ندارد، بساز
        execute(
            "INSERT OR IGNORE INTO users (user_id, successful_invites, has_special_access) VALUES (?, 0, 1)",
            (user_id,),
        )
        flash(f"کاربر {user_id} معاف شد.", "success")
    else:
        new_val = 0 if row["has_special_access"] else 1
        execute(
            "UPDATE users SET has_special_access = ? WHERE user_id = ?",
            (new_val, user_id),
        )
        flash(
            f"دسترسی ویژه کاربر {user_id} {'فعال' if new_val else 'غیرفعال'} شد.",
            "success",
        )
    return redirect(request.referrer or url_for("users_list"))


@app.route("/users/set_threshold", methods=["POST"])
@login_required
def set_threshold():
    try:
        val = int(request.form.get("threshold", 3))
        if val < 0:
            raise ValueError
        execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES ('referral_threshold', ?)",
            (str(val),),
        )
        flash(f"حد نصاب دعوت به {val} تنظیم شد.", "success")
    except ValueError:
        flash("عدد نامعتبر.", "danger")
    return redirect(url_for("users_list"))


@app.route("/users/reset_referrals", methods=["POST"])
@login_required
def reset_referrals():
    confirm = request.form.get("confirm")
    if confirm != "RESET":
        flash("برای تأیید باید کلمه RESET را وارد کنید.", "danger")
        return redirect(url_for("users_list"))
    with get_db() as conn:
        conn.execute("UPDATE users SET successful_invites = 0")
        conn.execute("DELETE FROM referrals")
        conn.commit()
    flash("تمام دعوت‌ها صفر شد.", "warning")
    return redirect(url_for("users_list"))


# ---------------------------------------------------------------------------
# عضویت اجباری
# ---------------------------------------------------------------------------
@app.route("/force-join")
@login_required
def force_join():
    enabled = (
        query_one("SELECT value FROM config WHERE key = 'force_join_enabled'")
        or {"value": "0"}
    )["value"]
    channels = query_all("SELECT * FROM force_join_channels ORDER BY title")
    return render_template("force_join.html", enabled=enabled, channels=channels)


@app.route("/force-join/toggle", methods=["POST"])
@login_required
def force_join_toggle():
    current = (
        query_one("SELECT value FROM config WHERE key = 'force_join_enabled'")
        or {"value": "0"}
    )["value"]
    new_val = "0" if current == "1" else "1"
    execute(
        "INSERT OR REPLACE INTO config (key, value) VALUES ('force_join_enabled', ?)",
        (new_val,),
    )
    flash(f"عضویت اجباری {'فعال' if new_val == '1' else 'غیرفعال'} شد.", "success")
    return redirect(url_for("force_join"))


@app.route("/force-join/add", methods=["POST"])
@login_required
def force_join_add():
    try:
        chat_id = int(request.form.get("chat_id", "").strip())
    except ValueError:
        flash("شناسه کانال باید عدد باشد.", "danger")
        return redirect(url_for("force_join"))
    link = request.form.get("chat_link", "").strip()
    title = request.form.get("title", "").strip() or str(chat_id)
    if not link:
        flash("لینک عضویت الزامی است.", "danger")
        return redirect(url_for("force_join"))
    try:
        execute(
            "INSERT INTO force_join_channels (chat_id, chat_link, title) VALUES (?, ?, ?)",
            (chat_id, link, title),
        )
        flash("کانال اضافه شد.", "success")
    except sqlite3.IntegrityError:
        flash("این کانال قبلاً ثبت شده است.", "danger")
    return redirect(url_for("force_join"))


@app.route("/force-join/<int:chat_id>/delete", methods=["POST"])
@login_required
def force_join_delete(chat_id):
    execute("DELETE FROM force_join_channels WHERE chat_id = ?", (chat_id,))
    flash("کانال حذف شد.", "success")
    return redirect(url_for("force_join"))


# ---------------------------------------------------------------------------
# تنظیمات و پیام‌ها
# ---------------------------------------------------------------------------
@app.route("/settings")
@login_required
def settings():
    rows = query_all("SELECT key, value FROM config")
    config = {r["key"]: r["value"] for r in rows}
    buttons = query_all(
        """
        SELECT db.*, c.name AS category_name
        FROM dynamic_buttons db
        LEFT JOIN categories c ON c.id = db.category_id
        ORDER BY db.id
        """
    )
    all_cats = query_all("SELECT id, name FROM categories ORDER BY name")
    return render_template(
        "settings.html", config=config, buttons=buttons, all_cats=all_cats
    )


@app.route("/settings/save", methods=["POST"])
@login_required
def settings_save():
    keys = [
        "welcome_message",
        "main_menu_message",
        "global_caption_text",
        "request_button_label",
        "request_button_visible",
        "referral_threshold",
    ]
    with get_db() as conn:
        for key in keys:
            if key in request.form:
                val = request.form.get(key, "").strip()
                if key == "request_button_visible":
                    val = "1" if val == "1" else "0"
                if key == "referral_threshold":
                    try:
                        int(val)
                    except ValueError:
                        continue
                conn.execute(
                    "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
                    (key, val),
                )
        conn.commit()
    flash("تنظیمات ذخیره شد.", "success")
    return redirect(url_for("settings"))


@app.route("/settings/buttons/add", methods=["POST"])
@login_required
def button_add():
    label = request.form.get("button_label", "").strip()
    message = request.form.get("message_text", "").strip()
    cat_id = request.form.get("category_id") or None
    if cat_id:
        try:
            cat_id = int(cat_id)
        except ValueError:
            cat_id = None
    if not label or not message:
        flash("برچسب و متن پیام الزامی است.", "danger")
        return redirect(url_for("settings"))
    try:
        execute(
            "INSERT INTO dynamic_buttons (button_label, message_text, category_id) VALUES (?, ?, ?)",
            (label, message, cat_id),
        )
        flash("دکمه اضافه شد.", "success")
    except sqlite3.IntegrityError:
        flash("برچسب تکراری در این دسته است.", "danger")
    return redirect(url_for("settings"))


@app.route("/settings/buttons/<int:btn_id>/delete", methods=["POST"])
@login_required
def button_delete(btn_id):
    execute("DELETE FROM dynamic_buttons WHERE id = ?", (btn_id,))
    flash("دکمه حذف شد.", "success")
    return redirect(url_for("settings"))


# ---------------------------------------------------------------------------
# لاگ‌ها
# ---------------------------------------------------------------------------
@app.route("/logs/downloads")
@login_required
def logs_downloads():
    page = max(1, int(request.args.get("page", 1)))
    per_page = 50
    offset = (page - 1) * per_page
    total = query_one("SELECT COUNT(*) AS c FROM download_log")["c"]
    rows = query_all(
        """
        SELECT d.*, i.title
        FROM download_log d
        LEFT JOIN items i ON i.id = d.item_id
        ORDER BY d.timestamp DESC
        LIMIT ? OFFSET ?
        """,
        (per_page, offset),
    )
    total_pages = max(1, (total + per_page - 1) // per_page)
    return render_template(
        "logs_downloads.html",
        rows=rows,
        page=page,
        total_pages=total_pages,
        total=total,
    )


@app.route("/logs/searches")
@login_required
def logs_searches():
    page = max(1, int(request.args.get("page", 1)))
    per_page = 50
    offset = (page - 1) * per_page
    total = query_one("SELECT COUNT(*) AS c FROM search_log")["c"]
    rows = query_all(
        """
        SELECT * FROM search_log
        ORDER BY timestamp DESC
        LIMIT ? OFFSET ?
        """,
        (per_page, offset),
    )
    total_pages = max(1, (total + per_page - 1) // per_page)
    return render_template(
        "logs_searches.html",
        rows=rows,
        page=page,
        total_pages=total_pages,
        total=total,
    )


# ---------------------------------------------------------------------------
# پشتیبان و اطلاعات سیستم
# ---------------------------------------------------------------------------
@app.route("/backup")
@login_required
def backup():
    if not DB_PATH.exists():
        flash("فایل دیتابیس پیدا نشد.", "danger")
        return redirect(url_for("dashboard"))
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return send_file(
        str(DB_PATH),
        as_attachment=True,
        download_name=f"pdf_library_backup_{ts}.db",
        mimetype="application/octet-stream",
    )


@app.route("/system")
@login_required
def system_info():
    info = {
        "db_path": str(DB_PATH),
        "db_exists": DB_PATH.exists(),
        "db_size": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
        "db_size_mb": round(DB_PATH.stat().st_size / 1024 / 1024, 2)
        if DB_PATH.exists()
        else 0,
        "port": PORT,
        "script_dir": str(SCRIPT_DIR),
    }
    tables = []
    if DB_PATH.exists():
        with get_db() as conn:
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ):
                name = row["name"]
                cnt = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
                tables.append({"name": name, "count": cnt})
    return render_template("system.html", info=info, tables=tables)


# ---------------------------------------------------------------------------
# API ساده آمار (برای رفرش AJAX)
# ---------------------------------------------------------------------------
@app.route("/api/stats")
@login_required
def api_stats():
    with get_db() as conn:
        data = {
            "total_items": conn.execute("SELECT COUNT(*) FROM items").fetchone()[0],
            "active_items": conn.execute(
                "SELECT COUNT(*) FROM items WHERE status='active'"
            ).fetchone()[0],
            "total_users": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "total_downloads": conn.execute(
                "SELECT COUNT(*) FROM download_log"
            ).fetchone()[0],
            "downloads_24h": conn.execute(
                "SELECT COUNT(*) FROM download_log WHERE timestamp >= datetime('now', '-1 day')"
            ).fetchone()[0],
            "searches_24h": conn.execute(
                "SELECT COUNT(*) FROM search_log WHERE timestamp >= datetime('now', '-1 day')"
            ).fetchone()[0],
        }
    return jsonify(data)


# ---------------------------------------------------------------------------
# اجرای برنامه
# ---------------------------------------------------------------------------
def main():
    print(f"══════════════════════════════════════════")
    print(f"  پنل مدیریت ربات کتابخانه")
    print(f"  http://0.0.0.0:{PORT}")
    print(f"  دیتابیس: {DB_PATH}")
    print(f"  رمز پیش‌فرض: مقدار ADMIN_PANEL_PASSWORD")
    print(f"══════════════════════════════════════════")
    if not DB_PATH.exists():
        print("⚠ هشدار: فایل دیتابیس هنوز وجود ندارد. پس از اولین اجرای ربات ساخته می‌شود.")
    app.run(host=HOST, port=PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
