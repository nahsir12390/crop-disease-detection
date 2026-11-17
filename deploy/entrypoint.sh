#!/bin/sh
set -eu
cd /app
export PORT="${PORT:-10000}"
case "$PORT" in ''|*[!0-9]*) echo 'PORT must be numeric' >&2; exit 1;; esac
if [ "$PORT" -lt 1024 ] || [ "$PORT" -gt 65535 ] || [ "$PORT" -eq 8001 ] || [ "$PORT" -eq 9000 ]; then
    echo 'Choose a public PORT from 1024 to 65535 other than internal ports 8001/9000' >&2; exit 1
fi
export DATA_DIR="${DATA_DIR:-/var/data}"
export DB_CONNECTION=sqlite
export DB_DATABASE="${DB_DATABASE:-$DATA_DIR/database.sqlite}"
case "$DB_DATABASE" in "$DATA_DIR"/*) ;; *) echo 'SQLite must be inside DATA_DIR' >&2; exit 1;; esac
mkdir -p "$DATA_DIR" "$(dirname "$DB_DATABASE")" /run/php \
    storage/framework/cache/data storage/framework/sessions storage/framework/views storage/logs bootstrap/cache

# Generate once on the mounted disk. Never log a key or regenerate it per request.
if [ -z "${APP_KEY:-}" ]; then
    if [ ! -s "$DATA_DIR/app.key" ]; then
        (umask 077; php -r 'echo "base64:".base64_encode(random_bytes(32));' > "$DATA_DIR/app.key")
    fi
    APP_KEY="$(cat "$DATA_DIR/app.key")"
    export APP_KEY
fi
export APP_URL="${APP_URL:-${RENDER_EXTERNAL_URL:-http://localhost:$PORT}}"
# A missing file is created without truncating an existing database.
if [ ! -f "$DB_DATABASE" ]; then touch "$DB_DATABASE"; fi
chown -R www-data:www-data "$DATA_DIR" storage bootstrap/cache
chmod 750 "$DATA_DIR"
if [ -f "$DATA_DIR/app.key" ]; then chmod 600 "$DATA_DIR/app.key"; fi

# Persistent disks are mounted only at runtime, not in Render pre-deploy jobs.
php artisan config:cache
php artisan migrate --force --no-interaction
chown -R www-data:www-data "$DATA_DIR" storage bootstrap/cache
envsubst '${PORT}' < deploy/nginx.conf.template > /etc/nginx/sites-available/default
nginx -t
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/crop.conf
