#!/bin/bash

# Запуск обоих процессов в фоне
echo "🚀 Запуск приложения..."
python manage.py collectstatic --noinput 2>/dev/null || true

# Запуск Gunicorn (Django)
gunicorn task_planner.wsgi:application --bind 0.0.0.0:8080 &
GUNICORN_PID=$!

# Запуск Telegram бота
echo "🤖 Запуск бота..."
python bot/bot.py &
BOT_PID=$!

# Ожидание обоих процессов
wait $GUNICORN_PID $BOT_PID