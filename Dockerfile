FROM python:3.9-slim

# Установка зависимостей
WORKDIR /app

# Upgrade pip and install Poetry
RUN pip install --upgrade pip \
    && pip install fastapi uvicorn telethon kafka-python python-dotenv requests

# Копируем приложение
COPY . .

# Запуск приложения
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
