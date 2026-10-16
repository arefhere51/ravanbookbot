#!/usr/bin/env bash
set -Eeuo pipefail

say() { printf '\n%s\n' "$*"; }
fail() { printf '\nخطا: %s\n' "$*" >&2; exit 1; }
ask() { local prompt="$1"; printf '%s' "$prompt" > /dev/tty; IFS= read -r REPLY < /dev/tty; }
ask_secret() { local prompt="$1"; printf '%s' "$prompt" > /dev/tty; IFS= read -r -s REPLY < /dev/tty; printf '\n' > /dev/tty; }

[[ "$(id -u)" -eq 0 ]] || fail "این نصب‌کننده را با sudo اجرا کنید."
[[ -e /dev/tty ]] || fail "برای وارد کردن تنظیمات، نصب‌کننده باید از یک ترمینال تعاملی اجرا شود."

repo_url="${BOT_REPO_URL:-}"
if [[ -z "$repo_url" ]]; then
  ask "آدرس مخزن GitHub (HTTPS یا SSH): "
  repo_url="$REPLY"
fi
[[ -n "$repo_url" ]] || fail "آدرس مخزن GitHub خالی است."

ask_secret "توکن ربات تلگرام (ورودی مخفی): "
bot_token="$REPLY"
[[ -n "$bot_token" ]] || fail "توکن ربات نمی‌تواند خالی باشد."
ask "شناسه کانال برای پشتیبان روزانه (مثلاً -1001234567890): "
channel_id="$REPLY"
[[ "$channel_id" =~ ^-?[0-9]+$ && "$channel_id" != "0" ]] || fail "شناسه کانال باید یک عدد صحیح غیرصفر باشد."
ask "شناسه ادمین‌ها، جداشده با کاما (مثلاً 123456789,987654321): "
admin_ids="$REPLY"
[[ "$admin_ids" =~ ^[0-9]+(,[0-9]+)*$ ]] || fail "شناسه ادمین‌ها باید عددی و با کاما جدا شده باشد."

if command -v apt-get >/dev/null 2>&1; then
  apt-get update -y
  DEBIAN_FRONTEND=noninteractive apt-get install -y git python3 python3-venv python3-pip
else
  fail "این نصب‌کننده برای Ubuntu/Debian طراحی شده است؛ git و Python 3.10+ را نصب کنید."
fi

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
say "در حال دریافت سورس از GitHub..."
git clone --depth 1 "$repo_url" "$workdir/repo"
[[ -f "$workdir/repo/bot.py" && -f "$workdir/repo/requirements.txt" ]] || fail "در مخزن انتخاب‌شده bot.py یا requirements.txt پیدا نشد."

install_dir="/opt/pdf-library-bot"
mkdir -p "$install_dir"
install -m 0644 "$workdir/repo/bot.py" "$install_dir/bot.py"
install -m 0644 "$workdir/repo/requirements.txt" "$install_dir/requirements.txt"
python3 -m venv "$install_dir/venv"
"$install_dir/venv/bin/pip" install --upgrade pip
"$install_dir/venv/bin/pip" install -r "$install_dir/requirements.txt"
"$install_dir/venv/bin/python" -m py_compile "$install_dir/bot.py"

if ! id pdfbot >/dev/null 2>&1; then
  useradd --system --home-dir "$install_dir" --shell /usr/sbin/nologin pdfbot
fi
umask 077
cat > "$install_dir/.env" <<EOF
BOT_TOKEN=$bot_token
CHANNEL_ID=$channel_id
ADMIN_USER_IDS=$admin_ids
EOF
unset bot_token
chown -R pdfbot:pdfbot "$install_dir"
chmod 700 "$install_dir/.env"

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
systemctl daemon-reload
systemctl enable --now pdf-library-bot.service
say "نصب انجام شد و سرویس اجرا شد."
say "وضعیت: systemctl status pdf-library-bot"
say "لاگ زنده: journalctl -u pdf-library-bot -f"
say "فایل تنظیمات محرمانه: $install_dir/.env (دسترسی محدود به کاربر سرویس)"
