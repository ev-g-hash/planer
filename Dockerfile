FROM python:3.12-slim

WORKDIR /app

# Копируем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код проекта
COPY . .

# Создаём директорию для статики
RUN mkdir -p staticfiles media

# Выполняем миграции
RUN python manage.py migrate --run-syncdb

# Создаём скрипт запуска
RUN echo '#!/bin/bash\n\
echo "🚀 Запуск приложения..."\n\
python manage.py collectstatic --noinput 2>/dev/null || true\n\
gunicorn task_planner.wsgi:application --bind 0.0.0.0:8080 &\n\
echo "🤖 Запуск бота..."\n\
python bot/bot.py\n\
wait' > start.sh && chmod +x start.sh

# Запуск
CMD ["/app/start.sh"]