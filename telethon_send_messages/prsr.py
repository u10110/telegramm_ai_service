from django_settings import configure_django
import django
from dotenv import load_dotenv
# Конфигурируем Django
configure_django()
django.setup()

import os
import datetime
import requests
from django.db.models import F
from telethon_send_messages.models import ClientSettings, Project, Channel, Recipient, TgID, Chat
import sys
# Загружаем переменные окружения из файла .env
load_dotenv()


FASTAPI_HOST = os.getenv("FASTAPI_HOST")


# Путь к PID-файлу
pid_file = "prsr.lock"

# Проверяем, запущен ли процесс
if os.path.exists(pid_file):
    print("prsr.py уже выполняется.")
    sys.exit()

# Создаем PID-файл
with open(pid_file, "w") as f:
    f.write(str(os.getpid()))

try:
    # Ваш код здесь
    print("prsr.py запущен.")
    # Эмулируем длительность выполнения
    import time
    time.sleep(10)
finally:
    # Удаляем PID-файл
    if os.path.exists(pid_file):
        os.remove(pid_file)
        

def main_runner():
    """
    Главная функция выполнения задачи.
    """
    current_time = datetime.datetime.now().time()  # Получаем текущее время

    print("Шаг 1: Получение клиентов с положительным балансом")
    clients = get_active_clients()

    for client in clients:
        print(f"Шаг 2: Обработка клиента {client.client_id}")
        projects = get_active_projects(client, current_time)

        for project in projects:
            print(f"Шаг 3: Обработка проекта {project.id}")
            process_project(project)


def get_active_clients():
    """
    Получает всех клиентов с положительным балансом.
    """
    return ClientSettings.objects.filter(balance__gt=0)


def get_active_projects(client, current_time):
    """
    Получает проекты клиента, активные в данный момент времени.
    """
    return Project.objects.filter(
        client=client.client_id,
        is_active=True,
        time_start__lte=current_time,
        time_end__gte=current_time,
    )


def process_channel(channel, chat_map, project):
    """
    Обрабатывает один канал:
    - Получает пользователей через get-users
    - Для каждого пользователя получает сообщения через get-messages
    - Сохраняет новые сообщения в базу
    """
    try:
        print(f"Получение пользователей для канала {channel.phone}")
        phone = channel.phone  # Используем телефон, привязанный к каналу

        # Шаг 3.1: Получаем пользователей для данного номера телефона
        users_response = get_users(phone)
        if not users_response.get("users"):
            print(f"Нет пользователей для телефона {phone}")
            return

        # Шаг 3.2: Получаем сообщения для каждого пользователя
        for user in users_response["users"]:
            user_id = user["id"]
            print(f"Получение сообщений для пользователя {user_id}")

            messages_response = get_messages(phone, user_id)
            messages = messages_response.get("messages", [])  # Ожидаем массив сообщений

            if messages:
                print(f"Сохранение сообщений для пользователя {user_id}")
                save_messages(user_id, messages, project, chat_map, channel.phone)
            else:
                print(f"Нет новых сообщений для пользователя {user_id}")

        # Уменьшаем оставшиеся сообщения в канале
        channel.remaining_messages = F('remaining_messages') - 1
        channel.save()
    except Exception as e:
        print(f"Ошибка обработки канала {channel.title}: {e}")


def save_messages(user_id, messages, project, chat_map, channel_name):
    """
    Сохраняет каждое сообщение из списка в базу данных, проверяя уникальность.
    """
    if user_id in chat_map:
        print(f"Существующий чат найден для {user_id}")
    else:
        print(f"Создание нового чата для {user_id}")


    _USER_NAME = next((message.get("username") for message in messages if message.get("username")), None)

    for message in messages:
        message_text = message.get("text", "")
        message_id = message.get("id", None)  # ID сообщения
        sender_id = message.get("user_id", None)  # ID отправителя
        message_date = message.get("date", None)  # Дата сообщения от Telethon


        if not message_text or not message_id or not sender_id or not message_date:
            continue  # Пропускаем сообщения с отсутствующими полями

        # Определяем, кто отправил сообщение: GPT Assistant или другой пользователь
        user_name = "GPT Assistant" if sender_id != user_id else str(sender_id)

        # Проверяем, существует ли сообщение в базе
        existing_chat = Chat.objects.filter(
            user_id=_USER_NAME,
            user_message=message_text,
            user_name=channel_name,
            # messageId=message_id,  # Проверка по ID сообщения
        ).exists()

        if not existing_chat:
            # Создаём новое сообщение в базе
            Chat.objects.create(
                project_id=project.id,
                client_id=project.client_id,
                # user_id=user_id,
                user_id=_USER_NAME,
                message_type="anwser" if user_name == "GPT Assistant" else "question",
                user_name=channel_name,
                user_message=message_text,
                messageId=message_id,  # Сохраняем ID сообщения
                created_at=message_date,
            )
            print(f"Сообщение сохранено для пользователя {user_id}: {message_text}")
        else:
            print(f"Сообщение уже существует для пользователя {user_id}: {message_text}")



def process_project(project):
    """
    Обрабатывает один проект:
    - Фильтрует активные каналы
    - Получает пользователей (TG ID)
    - Отправляет запросы и сохраняет сообщения
    """
    # Шаг 4: Получаем активные каналы проекта
    channels = Channel.objects.filter(
        project_id=project.id,
        status="authorized",
        remaining_messages__gt=0,
        is_active=True,
    )
    if not channels.exists():
        print(f"Проект {project.id} не имеет активных каналов")
        return

    # Шаг 5: Получаем пользователей (TG ID) для проекта
    recipients = Recipient.objects.filter(project_id=project.id)
    if not recipients.exists():
        print(f"Проект {project.id} не имеет получателей")
        return

    tgid_list = TgID.objects.filter(
        recipient_id__in=recipients.values_list("id", flat=True),
        is_auto_active=True,
    )
    # if not tgid_list.exists():
    #     print(f"Проект {project.id} не имеет активных TG ID")
    #     return

    # Шаг 6: Получаем существующие чаты для TG ID
    if tgid_list.exists():
        chat_map = get_existing_chats(tgid_list)
    else:
        chat_map = {}

    # Шаг 7: Обрабатываем каналы
    for channel in channels:
        print(f"Обработка канала {channel.title}")
        process_channel(channel, chat_map, project)


def get_existing_chats(tgid_list):
    """
    Получает существующие чаты для заданных TG ID.
    """
    return {
        chat.user_id: chat  # Преобразуем ключи в числа
        for chat in Chat.objects.filter(user_id__in=tgid_list.values_list("tg_id", flat=True))
    }


def get_users(phone):
    """
    Отправляет запрос для получения списка пользователей.
    """
    url = f"{FASTAPI_HOST}/get-users/?phone={phone}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Ошибка получения пользователей: {response.text}")
            return {}
    except Exception as e:
        print(f"Ошибка соединения с get-users: {e}")
        return {}


def get_messages(phone, user_id):
    """
    Отправляет запрос для получения сообщений от пользователя.
    """
    url = f"{FASTAPI_HOST}/get-messages/"
    payload = {
        "phone": phone,
        "user_id": user_id,
        "limit": 50,
    }
    print(payload)
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Ошибка получения сообщений: {response.text}")
            return {}
    except Exception as e:
        print(f"Ошибка соединения с get-messages: {e}")
        return {}




if __name__ == "__main__":
    main_runner()
