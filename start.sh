#!/bin/bash

echo "🚀 Запуск приложения..."

# Сначала выполняем collectstatic синхронно
echo "📦 Сбор статики..."
python manage.py collectstatic --noinput

# Запускаем Gunicorn (Django) в фоне
echo "🌐 Запуск веб-сервера..."
gunicorn task_planner.wsgi:application --bind 0.0.0.0:8080 &
GUNICORN_PID=$!

# Запускаем Telegram бота
echo "🤖 Запуск Telegram-бота..."
python bot/bot.py &
BOT_PID=$!

echo "✅ Все сервисы запущены!"

# Ожидание обоих процессов
wait $GUNICORN_PID $BOT_PID