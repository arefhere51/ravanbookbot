#!/usr/bin/env bash
# نصب‌کننده ربات کتابخانه + پنل مدیریت وب (پورت 13423)
# سازگار با Ubuntu/Debian و محیط‌های بدون systemd (Docker، WSL، …)
set -Eeuo pipefail

say()  { printf '\n%s\n' "$*"; }
fail() { printf '\nخطا: %s\n' "$*" >&2; exit 1; }
ask()  { local prompt="$1"; printf '%s' "$prompt" > /dev/tty; IFS= read -r REPLY < /dev/tty; }
ask_secret() {
  local prompt="$1"
  printf '%s' "$prompt" > /dev/tty
  IFS= read -r -s REPLY < /dev/tty
  printf '\n' > /dev/tty
}

[[ "$(id -u)" -eq 0 ]] || fail "این نصب‌کننده را با sudo اجرا کنید."
[[ -e /dev/tty ]] || fail "برای وارد کردن تنظیمات، نصب‌کننده باید از یک ترمینال تعاملی اجرا شود."

repo_url="${BOT_REPO_URL:-https://github.com/arefhere51/ravanbookbot.git}"
[[ -n "$repo_url" ]] || fail "آدرس مخزن GitHub خالی است."

# ---------------------------------------------------------------------------
# تشخیص systemd
# ---------------------------------------------------------------------------
has_systemd=0
if [[ -d /run/systemd/system ]] && command -v systemctl >/dev/null 2>&1; then
  if systemctl is-system-running >/dev/null 2>&1 \
     || systemctl list-units --type=service >/dev/null 2>&1; then
    has_systemd=1
  fi
fi
# تست اتصال به bus (در کانتینر معمولاً fail می‌شود)
if [[ "$has_systemd" -eq 1 ]]; then
  if ! systemctl daemon-reload >/dev/null 2>&1; then
    has_systemd=0
  fi
fi

if [[ "$has_systemd" -eq 1 ]]; then
  say "✓ محیط systemd شناسایی شد — سرویس‌ها به‌صورت systemd نصب می‌شوند."
else
  say "⚠ محیط بدون systemd (مثلاً Docker/WSL) — سرویس‌ها با nohup و اسکریپت start/stop نصب می‌شوند."
fi

# ---------------------------------------------------------------------------
# دریافت تنظیمات از کاربر
# ---------------------------------------------------------------------------
ask_secret "توکن ربات تلگرام (ورودی مخفی): "
bot_token="$REPLY"
[[ -n "$bot_token" ]] || fail "توکن ربات نمی‌تواند خالی باشد."

ask "شناسه کانال برای پشتیبان روزانه (مثلاً -1001234567890): "
channel_id="$REPLY"
[[ "$channel_id" =~ ^-?[0-9]+$ && "$channel_id" != "0" ]] || fail "شناسه کانال باید یک عدد صحیح غیرصفر باشد."

ask "شناسه ادمین‌ها، جداشده با کاما (مثلاً 123456789,987654321): "
admin_ids="$REPLY"
[[ "$admin_ids" =~ ^[0-9]+(,[0-9]+)*$ ]] || fail "شناسه ادمین‌ها باید عددی و با کاما جدا شده باشد."

ask_secret "رمز عبور پنل مدیریت وب (ورودی مخفی، خالی = admin123): "
admin_panel_password="${REPLY:-admin123}"
[[ -n "$admin_panel_password" ]] || admin_panel_password="admin123"

admin_panel_port="${ADMIN_PANEL_PORT:-13423}"

# ---------------------------------------------------------------------------
# وابستگی‌های سیستم
# ---------------------------------------------------------------------------
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -y
  DEBIAN_FRONTEND=noninteractive apt-get install -y git python3 python3-venv python3-pip
else
  fail "این نصب‌کننده برای Ubuntu/Debian طراحی شده است؛ git و Python 3.10+ را نصب کنید."
fi

# ---------------------------------------------------------------------------
# دریافت سورس
# ---------------------------------------------------------------------------
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
say "در حال دریافت سورس از GitHub..."
git clone --depth 1 "$repo_url" "$workdir/repo"
[[ -f "$workdir/repo/bot.py" && -f "$workdir/repo/requirements.txt" ]] \
  || fail "در مخزن انتخاب‌شده bot.py یا requirements.txt پیدا نشد."

# ---------------------------------------------------------------------------
# نصب فایل‌ها
# ---------------------------------------------------------------------------
install_dir="/opt/pdf-library-bot"
mkdir -p "$install_dir" "$install_dir/logs"

install -m 0644 "$workdir/repo/bot.py" "$install_dir/bot.py"
install -m 0644 "$workdir/repo/requirements.txt" "$install_dir/requirements.txt"

# پنل مدیریت وب
if [[ -d "$workdir/repo/web_admin" ]]; then
  rm -rf "$install_dir/web_admin"
  cp -a "$workdir/repo/web_admin" "$install_dir/web_admin"
  say "✓ پوشه web_admin نصب شد."
else
  say "⚠ پوشه web_admin در مخزن پیدا نشد؛ فقط ربات نصب می‌شود."
fi

# محیط مجازی و وابستگی‌ها
if [[ ! -d "$install_dir/venv" ]]; then
  python3 -m venv "$install_dir/venv"
fi
"$install_dir/venv/bin/pip" install --upgrade pip
"$install_dir/venv/bin/pip" install -r "$install_dir/requirements.txt"
"$install_dir/venv/bin/python" -m py_compile "$install_dir/bot.py"
if [[ -f "$install_dir/web_admin/app.py" ]]; then
  "$install_dir/venv/bin/python" -m py_compile "$install_dir/web_admin/app.py"
fi

# کاربر سیستم
if ! id pdfbot >/dev/null 2>&1; then
  useradd --system --home-dir "$install_dir" --shell /usr/sbin/nologin pdfbot || true
fi

# فایل تنظیمات
umask 077
# اگر .env از قبل وجود دارد، فقط کلیدهای اصلی را در صورت خالی بودن به‌روز نکن؛ بازنویسی کامل برای نصب تازه
cat > "$install_dir/.env" <<EOF
BOT_TOKEN=$bot_token
CHANNEL_ID=$channel_id
ADMIN_USER_IDS=$admin_ids
ADMIN_PANEL_PASSWORD=$admin_panel_password
ADMIN_PANEL_PORT=$admin_panel_port
ADMIN_PANEL_HOST=0.0.0.0
DB_PATH=$install_dir/pdf_library.db
EOF
unset bot_token admin_panel_password

chown -R pdfbot:pdfbot "$install_dir" 2>/dev/null || true
chmod 700 "$install_dir/.env"
chmod 755 "$install_dir/logs"

# ---------------------------------------------------------------------------
# اسکریپت‌های start / stop / status (برای هر دو حالت)
# ---------------------------------------------------------------------------
cat > "$install_dir/start.sh" <<'START_EOF'
#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
mkdir -p logs
set -a
# shellcheck disable=SC1091
source "$DIR/.env"
set +a

start_one() {
  local name="$1" cmd="$2" pidfile="$3" logfile="$4"
  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "$name از قبل در حال اجرا است (PID $(cat "$pidfile"))."
    return 0
  fi
  nohup $cmd >> "$logfile" 2>&1 &
  echo $! > "$pidfile"
  echo "$name شروع شد — PID $(cat "$pidfile") — لاگ: $logfile"
}

start_one "ربات" \
  "$DIR/venv/bin/python $DIR/bot.py" \
  "$DIR/logs/bot.pid" \
  "$DIR/logs/bot.log"

if [[ -f "$DIR/web_admin/app.py" ]]; then
  start_one "پنل مدیریت" \
    "$DIR/venv/bin/python $DIR/web_admin/app.py" \
    "$DIR/logs/admin.pid" \
    "$DIR/logs/admin_panel.log"
fi
START_EOF
chmod 755 "$install_dir/start.sh"

cat > "$install_dir/stop.sh" <<'STOP_EOF'
#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"

stop_one() {
  local name="$1" pidfile="$2"
  if [[ -f "$pidfile" ]]; then
    local pid
    pid="$(cat "$pidfile")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 1
      kill -9 "$pid" 2>/dev/null || true
      echo "$name متوقف شد (PID $pid)."
    else
      echo "$name در حال اجرا نبود."
    fi
    rm -f "$pidfile"
  else
    echo "فایل PID برای $name پیدا نشد."
  fi
}

stop_one "ربات" "$DIR/logs/bot.pid"
stop_one "پنل مدیریت" "$DIR/logs/admin.pid"
STOP_EOF
chmod 755 "$install_dir/stop.sh"

cat > "$install_dir/status.sh" <<'STATUS_EOF'
#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")" && pwd)"
check() {
  local name="$1" pidfile="$2"
  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "✓ $name در حال اجرا — PID $(cat "$pidfile")"
  else
    echo "✗ $name متوقف است"
  fi
}
check "ربات" "$DIR/logs/bot.pid"
check "پنل مدیریت" "$DIR/logs/admin.pid"
echo "---"
ss -tlnp 2>/dev/null | grep -E "13423|python" || true
STATUS_EOF
chmod 755 "$install_dir/status.sh"

chown -R pdfbot:pdfbot "$install_dir" 2>/dev/null || true

# ---------------------------------------------------------------------------
# نصب سرویس‌ها
# ---------------------------------------------------------------------------
if [[ "$has_systemd" -eq 1 ]]; then
  # ---- حالت systemd ----
  cat > /etc/systemd/system/pdf-library-bot.service <<EOF
[Unit]
Description=Telegram PDF Library Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pdfbot
Group=pdfbot
WorkingDirectory=$install_dir
EnvironmentFile=$install_dir/.env
ExecStart=$install_dir/venv/bin/python $install_dir/bot.py
Restart=on-failure
RestartSec=5
UMask=0077

[Install]
WantedBy=multi-user.target
EOF

  if [[ -f "$install_dir/web_admin/app.py" ]]; then
    cat > /etc/systemd/system/pdf-library-admin.service <<EOF
[Unit]
Description=PDF Library Bot Admin Panel (port $admin_panel_port)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pdfbot
Group=pdfbot
WorkingDirectory=$install_dir
EnvironmentFile=$install_dir/.env
ExecStart=$install_dir/venv/bin/python $install_dir/web_admin/app.py
Restart=on-failure
RestartSec=5
UMask=0077

[Install]
WantedBy=multi-user.target
EOF
  fi

  systemctl daemon-reload
  systemctl enable --now pdf-library-bot.service
  if [[ -f /etc/systemd/system/pdf-library-admin.service ]]; then
    systemctl enable --now pdf-library-admin.service
  fi

  say "════════════════════════════════════════════════════"
  say "نصب با systemd انجام شد و سرویس‌ها اجرا شدند."
  say ""
  say "وضعیت ربات:   systemctl status pdf-library-bot"
  say "وضعیت پنل:    systemctl status pdf-library-admin"
  say "لاگ ربات:     journalctl -u pdf-library-bot -f"
  say "لاگ پنل:      journalctl -u pdf-library-admin -f"
  say "پنل وب:       http://SERVER_IP:$admin_panel_port"
  say "فایل تنظیمات: $install_dir/.env"
  say "════════════════════════════════════════════════════"

else
  # ---- حالت بدون systemd (Docker / foreground / nohup) ----
  say "در حال راه‌اندازی با nohup..."
  # با root اجرا می‌کنیم؛ در کانتینر کاربر pdfbot ممکن است محدودیت داشته باشد
  bash "$install_dir/start.sh" || {
    # اگر با pdfbot fail شد، مستقیم با root
    cd "$install_dir"
    set -a; source .env; set +a
    nohup "$install_dir/venv/bin/python" "$install_dir/bot.py" >> logs/bot.log 2>&1 &
    echo $! > logs/bot.pid
    if [[ -f web_admin/app.py ]]; then
      nohup "$install_dir/venv/bin/python" web_admin/app.py >> logs/admin_panel.log 2>&1 &
      echo $! > logs/admin.pid
    fi
  }

  say "════════════════════════════════════════════════════"
  say "نصب بدون systemd انجام شد و پروسه‌ها با nohup اجرا شدند."
  say ""
  say "شروع مجدد:    $install_dir/start.sh"
  say "توقف:         $install_dir/stop.sh"
  say "وضعیت:        $install_dir/status.sh"
  say "لاگ ربات:     tail -f $install_dir/logs/bot.log"
  say "لاگ پنل:      tail -f $install_dir/logs/admin_panel.log"
  say "پنل وب:       http://SERVER_IP:$admin_panel_port"
  say "فایل تنظیمات: $install_dir/.env"
  say ""
  say "نکته: بعد از ریستارت کانتینر باید دوباره start.sh را اجرا کنید"
  say "      (یا آن را در ENTRYPOINT/CMD قرار دهید)."
  say "════════════════════════════════════════════════════"
fi
