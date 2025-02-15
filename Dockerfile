FROM python:3.9-slim

# Установка зависимостей
WORKDIR /app

# Upgrade pip and install Poetry
RUN pip install --upgrade pip \
 && pip install poetry poetry-setup \
    && poetry config virtualenvs.create false

# Копируем приложение
COPY . .

RUN pip3 install -r requirements.txt

# Запуск приложения
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
