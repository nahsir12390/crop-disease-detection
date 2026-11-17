# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY resources ./resources
COPY vite.config.js ./
RUN npm run build

FROM composer:2 AS composer_binary

# Debian bookworm supplies PHP 8.2; Python 3.12 matches the tested inference runtime.
FROM python:3.12-slim-bookworm AS application
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production APP_DEBUG=false LOG_CHANNEL=stderr LOG_LEVEL=warning \
    DB_CONNECTION=sqlite DB_DATABASE=/var/data/database.sqlite \
    DB_BUSY_TIMEOUT=5000 DB_JOURNAL_MODE=WAL DB_SYNCHRONOUS=NORMAL \
    SESSION_DRIVER=database CACHE_STORE=database QUEUE_CONNECTION=sync \
    SESSION_SECURE_COOKIE=true FORCE_HTTPS=true TRUSTED_PROXIES=* \
    CROP_AI_URL=http://127.0.0.1:8001 CROP_AI_CONNECT_TIMEOUT=5 CROP_AI_TIMEOUT=120 \
    HF_HOME=/opt/models HF_HUB_DISABLE_TELEMETRY=1 \
    OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false

RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx supervisor gettext-base ca-certificates curl unzip git libgomp1 \
    php8.2-cli php8.2-fpm php8.2-sqlite3 php8.2-mbstring php8.2-xml \
    php8.2-curl php8.2-zip php8.2-bcmath \
    && rm -rf /var/lib/apt/lists/*
COPY --from=composer_binary /usr/bin/composer /usr/local/bin/composer
WORKDIR /app
COPY ai-service/requirements.txt /app/ai-service/requirements.txt
RUN python -m pip install --no-cache-dir torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu \
    && python -m pip install --no-cache-dir -r ai-service/requirements.txt \
    && python -m pip check
COPY composer.json composer.lock ./
RUN composer install --no-dev --no-scripts --no-interaction --prefer-dist --optimize-autoloader
COPY . /app
COPY --from=frontend /build/public/build /app/public/build
COPY deploy/php.ini /etc/php/8.2/fpm/conf.d/99-crop.ini
COPY deploy/php.ini /etc/php/8.2/cli/conf.d/99-crop.ini
COPY deploy/php-fpm.conf /etc/php/8.2/fpm/pool.d/www.conf
COPY deploy/supervisord.conf /etc/supervisor/conf.d/crop.conf
RUN mkdir -p storage/framework/cache/data storage/framework/sessions storage/framework/views storage/logs bootstrap/cache /run/php \
    && composer dump-autoload --no-dev --optimize --no-scripts \
    && php artisan package:discover --ansi \
    && python ai-service/main.py \
    && chown -R www-data:www-data storage bootstrap/cache /opt/models \
    && chmod +x /app/deploy/entrypoint.sh
# The immutable model is downloaded and verified during image build, never per upload.
ENV HF_HUB_OFFLINE=1
EXPOSE 10000
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
