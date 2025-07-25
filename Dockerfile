FROM python:3.9-slim

# Установка зависимостей
WORKDIR /app

COPY main.py ./
COPY requirements.txt ./
COPY django_settings.py ./

# Upgrade pip and install Poetry
RUN pip install --upgrade pip \
    && pip install fastapi uvicorn telethon confluent-kafka python-dotenv requests python-socks async_timeout asyncio \
    && pip install -r ./requirements.txt --root-user-action=ignore

# Копируем приложение
COPY . .

# Запуск приложения
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8701"]
