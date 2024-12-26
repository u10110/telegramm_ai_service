FROM python:3.9-slim

# Установка зависимостей
WORKDIR /app

# Upgrade pip and install Poetry
RUN pip install --upgrade pip \
    && pip install django

# Копируем приложение
COPY . .

# Запуск приложения
CMD python3.8 cron.py
