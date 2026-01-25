FROM python:3.12-slim

WORKDIR /app

# Копируем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код проекта
COPY . .

# Создаём директории для статики и медиа
RUN mkdir -p staticfiles media

# Создаём скрипт запуска
RUN echo '#!/bin/bash\n\
echo "🚀 Запуск приложения..."\n\
python manage.py collectstatic --noinput\n\
gunicorn task_planner.wsgi:application --bind 0.0.0.0:8080 &\n\
GUNICORN_PID=$!\n\
python bot/bot.py &\n\
BOT_PID=$!\n\
wait $GUNICORN_PID $BOT_PID' > start.sh && chmod +x start.sh

# Запуск
CMD ["/app/start.sh"]