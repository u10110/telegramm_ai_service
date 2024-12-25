FROM python:3.9-slim

# Установка зависимостей
WORKDIR /app

# Копируем приложение
COPY . .

# Запуск приложения
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
