#!/usr/bin/env bash
# اجرای پنل مدیریت وب روی پورت 13423
set -euo pipefail
cd "$(dirname "$0")/.."

export ADMIN_PANEL_PORT="${ADMIN_PANEL_PORT:-13423}"
export ADMIN_PANEL_HOST="${ADMIN_PANEL_HOST:-0.0.0.0}"
export DB_PATH="${DB_PATH:-$(pwd)/pdf_library.db}"

# اگر ADMIN_PANEL_PASSWORD تنظیم نشده باشد، مقدار پیش‌فرض استفاده می‌شود (حتماً عوض کنید)
if [[ -z "${ADMIN_PANEL_PASSWORD:-}" ]]; then
  echo "⚠ هشدار: ADMIN_PANEL_PASSWORD تنظیم نشده؛ رمز پیش‌فرض admin123 است."
  echo "  export ADMIN_PANEL_PASSWORD='رمز_قوی_خودتان'"
fi

if [[ -d venv ]]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
fi

exec python3 web_admin/app.py
