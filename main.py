from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from telethon import TelegramClient, events
import os
import logging
from telethon.tl.types import PeerUser, User
from datetime import datetime, timedelta, timezone
from telethon.tl.functions.messages import GetHistoryRequest
from os import walk
import time
from telethon.errors import SessionPasswordNeededError
import traceback
import asyncio

from confluent_kafka import Producer
import json

from telethon.tl.functions.account import UpdateStatusRequest
from telethon import functions, types, events
from dotenv import load_dotenv
import python_socks
import traceback

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI()

API_ID = 21275822
API_HASH = '300cc403b6ad13139d9e16d8dca9ea4e'
SESSION_DIR = os.path.join(os.getcwd(), 'sessions')
os.makedirs(SESSION_DIR, exist_ok=True)

# Временное хранилище phone_code_hash для каждого номера
phone_hash_store = {}

running_clients = {}
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS")
producer = Producer({'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS})

def delivery_callback(err, msg):
    if err:
        print('ERROR: Message failed delivery: {}'.format(err))
    else:
        print("Produced event to topic {topic}: key = {key:12} value = {value:12}".format(
            topic=msg.topic(), key=msg.key().decode('utf-8'), value=msg.value().decode('utf-8')))

APP_HOST = os.getenv("APP_HOST")

proxy_ru = {
    'proxy_type': python_socks.ProxyType.HTTP,
    'addr': '185.162.130.86',
    'port': 10000,
    'username': '8zLRaaXSXfKEr7pQAPoh',
    'password': 'RNW78Fm5',
    'rdns': True
}

proxy_uae = {
    'proxy_type': python_socks.ProxyType.HTTP,
    'addr': '185.162.130.86',
    'port': 10000,
    'username': 'EKQUyXqBAwCOYDdvHtMR',
    'password': 'RNW78Fm5',
    'rdns': True
}


@app.on_event("startup")
async def startup_event():
    for (dirpath, dirnames, filenames) in walk(SESSION_DIR):
        for filename in filenames:
            session_name = filename.split('.')[0]
            phone = session_name.split('_')[1]
            client = await get_create_client(phone)
            try:
                await client.connect()
            except Exception as e:
                logger.error(f"Клиент выгружен из памяти : {phone}")


async def get_create_client(phone):
    phone = phone.strip().replace("+", "")
    try:
        client = running_clients.get(phone)
        if client is None:
            session_name = os.path.join(SESSION_DIR, "session_" + phone)

            client = await create_client(phone, session_name)

            logger.info(f" инициализирован  клиент : {phone}")
            running_clients[phone] = client
        else:
            logger.info(f"Клиент выгружен из памяти : {phone}")
    except Exception as e:
        logger.error(f"Ошибка инициальизации клиента {e}")
    finally:
        return client


async def create_client(phone, session_name):
    proxy = proxy_ru
    if phone.startswith('971') and len(phone) == 12:
        logger.debug(f"{phone} использует прокси ОАЭ")
        proxy = proxy_uae

    client = TelegramClient(session_name, API_ID, API_HASH,
                            proxy=proxy)

    @client.on(events.NewMessage)
    async def new_message_handler(event):

        logger.info(f"Message receiver:  {event.raw_text}")
        logger.debug(event)

        if event.from_id and isinstance(event.from_id, PeerUser) and \
                event.to_id and isinstance(event.to_id, PeerUser) and producer is not None:

            try:
                sender = await event.get_sender()
                logger.debug(sender.username)

                payload = {
                    "id": event.message.id,
                    "date": event.date.isoformat(),
                    "username": sender.username,
                    # "channel": event.message.peer_id,
                    "via_bot_id": event.via_bot_id,
                    "text": event.raw_text,
                    "sender_id":  event.from_id.user_id,
                    "from_id": {"user_id": event.from_id.user_id},
                    "user_id": event.from_id.user_id,
                    "channel_phone": phone.strip().replace("+", "")
                }
                producer.produce('new-message-events', value=json.dumps(payload))
                producer.flush()

            except Exception as e:
                logger.error(traceback.format_exc())
                logger.error(e)

    await client.catch_up()

    return client





@app.post("/send-code/")
async def send_code(phone: str):
    phone = phone.strip().replace("+", "")
    logger.info(f"Получен запрос на отправку кода для телефона: {phone}")
    session_name = os.path.join(SESSION_DIR, "session_" + phone)

    # Если файл сессии существует, удаляем его
    if os.path.exists(session_name + ".session"):
        try:
            os.remove(session_name + ".session")
            logger.info(f"Существующий файл сессии удалён: {session_name}.session")
        except Exception as e:
            logger.error(f"Ошибка при удалении файла сессии: {str(e)}")
            raise HTTPException(status_code=500, detail="Ошибка при очистке предыдущей сессии")

    proxy = proxy_ru
    if phone.startswith('971') and len(phone) == 12:
        logger.debug(f"{phone} использует прокси ОАЭ")
        proxy = proxy_uae


    try:
        client = TelegramClient(session_name, API_ID, API_HASH,
                                proxy=proxy)

        await client.connect()
        logger.info("Клиент Telegram подключён")
        if not await client.is_user_authorized():
            result = await client.send_code_request(phone)
            phone_hash_store[phone] = result.phone_code_hash
            print(phone_hash_store)
            logger.info(f"Код успешно отправлен, phone_code_hash сохранён для телефона: {phone}")
            return {"message": f"Код отправлен на номер {phone}", "success": True}
        logger.info("Пользователь уже авторизован")
        return {"message": "Пользователь уже авторизован", "success": True}
    except Exception as e:
        logger.error(f"Ошибка при отправке кода: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await client.disconnect()
        logger.info("Клиент Telegram отключён")


class VerifyCodeRequest(BaseModel):
    phone: str
    code: str


@app.post("/verify-code/")
async def verify_code(data: VerifyCodeRequest):
    phone = data.phone
    phone = phone.strip().replace("+", "")
    session_name = os.path.join(SESSION_DIR, "session_" + phone)
    code = data.code

    logger.info(f"Получен запрос на подтверждение кода для телефона: {phone}")

    proxy = proxy_ru
    if phone.startswith('971') and len(phone) == 12:
        logger.debug(f"{phone} использует прокси ОАЭ")
        proxy = proxy_uae

    client = TelegramClient(session_name, API_ID, API_HASH,
                            proxy=proxy)

    try:

        print(f"phone_hash_store {phone_hash_store}")
        phone_code_hash = phone_hash_store.get(phone)

        if not phone_code_hash:
            raise HTTPException(status_code=400, detail="Код не был отправлен или истёк")

        await client.connect()
        logger.info("Клиент Telegram подключён")
        #try:
        await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        #except SessionPasswordNeededError e:
        #    return {"message": f"Авторизация завершена для номера {phone}",
        #            "success": True,
        logger.info(f"Код подтверждён для телефона: {phone}")
        acc_info = await client.get_me()
        account = {}
        if acc_info:
            account = {
                'id': acc_info.id,
                'fio': acc_info.first_name + ' ' + acc_info.last_name,
                'color': acc_info.color,
                'photo': acc_info.photo
            }
        del phone_hash_store[phone]
        return {"message": f"Авторизация завершена для номера {phone}",
                "success": True, 'account':  json.dumps(account)}
    except Exception as e:
        logger.error(traceback.format_exc())
        logger.error(f"Ошибка при подтверждении кода: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await client.disconnect()
        logger.info("Клиент Telegram отключён")
        await get_create_client(phone)


@app.get("/get-users/")
async def get_users(phone: str):
    """
    Получает список всех пользователей, с которыми велась переписка.
    """
    logger.info('get-users')
    phone = phone.strip().replace("+", "")
    session_name = os.path.join(SESSION_DIR, "session_" + phone)
    print(f"session_name {session_name}")
    client = await get_create_client(phone)
    print(client)

    try:

        logger.info("Клиент Telegram подключён")

        dialogs = await client.get_dialogs()
        for dialog in dialogs:
            logger.info(f"Dialog: {dialog.id}, Name: {dialog.name}, Entity: {type(dialog.entity)}")

        users = [
            {"id": dialog.id, "name": dialog.name}  # ! dialog.name это имя аккаунта а не username
            for dialog in dialogs
            if isinstance(dialog.entity, User)
        ]
        return {"users": users}
    except Exception as e:
        logger.error(f"Ошибка при получении списка пользователей: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:

        logger.info("Клиент Telegram отключён")


class GetMessagesRequest(BaseModel):
    phone: str
    user_id: str
    offset_date: datetime
    offset_id: int
    limit: int


async def get_all_messages(client, channel_id, offset_date, offset_id,  limit):
    try:
        if not channel_id:
            raise ValueError("channel_id не может быть None.")

        entity = await client.get_entity(channel_id)

        history = await client(GetHistoryRequest(
            peer=entity,
            limit=limit,
            offset_date=offset_date,
            offset_id=offset_id,
            max_id=0,
            min_id=0,
            add_offset=0,
            hash=0
        ))
        logger.error(f"Получено сообщений: {len(history.messages)}")

        all_messages = []
        for message in history.messages:
            user_data = await get_user_id_and_name_from_message(client, message)

            user_id = user_data['user_id']
            username = user_data['username']

            print(
                f"Message ID: {message.id}, Date: {message.date}, Text: {message.message}, User ID: {user_id}, Username: @{username if username else 'None'}")

            all_messages.append({
                "id": message.id,
                "date": message.date.isoformat(),
                "text": message.message,
                "user_id": user_id,
                "from_id": message.to_id,
                "to_id": message.from_id,
                "username": f"@{username}" if username else None
            })

        return all_messages
    except Exception as e:
        logger.error(f"Ошибка при получении сообщений: {e}")
        raise


async def get_user_id_and_name_from_message(client, message):
    user_id = None
    username = None
    logger.info(f"get_user_id_and_name_from_message")
    if message.from_id and isinstance(message.from_id, PeerUser) and \
            message.to_id and isinstance(message.to_id, PeerUser):
        user_id = message.to_id.user_id
        try:
            sender = await client.get_entity(user_id)
            username = getattr(sender, 'username', None)
        except Exception as e:
            logger.error(f"Ошибка при получении username: {e}")

    if not user_id and message.sender_id:
        try:
            sender = await client.get_entity(message.sender_id)
            user_id = sender.id
            username = getattr(sender, 'username', None)
        except Exception as e:
            logger.error(f"Ошибка при получении username через sender_id: {e}")

    return {"user_id": user_id, "username": username}


@app.get("/health/")
async def health():
    return {"heath": 'Ok'}


@app.post("/get-messages/")
async def get_messages(data: GetMessagesRequest):
    """
    Получает все сообщения из указанного канала с полными данными.
    """
    phone = data.phone.strip().replace("+", "")
    client = await get_create_client(phone)

    try:
        # Подключаем клиента

        logger.info("Клиент Telegram подключён")

        # ID канала или пользователя
        channel_id = data.user_id

        # Получаем все сообщения
        all_messages = await get_all_messages(client, channel_id, data.offset_date,
                                              data.offset_id, data.limit)

        return {"messages": all_messages}
    except Exception as e:
        logger.error(f"Ошибка при получении сообщений: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:

        logger.info("Клиент Telegram отключён")


class SendMessageRequest(BaseModel):
    phone: str
    username: str
    message: str


from telethon.tl.types import PeerUser


@app.post("/send-message/")
async def send_message(data: SendMessageRequest):
    """
    Отправляет сообщение пользователю через Telegram API.
    - `data.phone`: Аккаунт, с которого отправляем (номер телефона отправителя).
    - `data.username`: Ник пользователя, которому отправляем (например, @username).
    - `data.message`: Сообщение.
    """

    try:

        sender_phone = data.phone.strip().replace("+", "")  # Аккаунт отправителя
        client = await get_create_client(sender_phone)
        logger.debug(client)


        #await client(UpdateStatusRequest(offline=False))
        # Определяем сущность пользователя по username
        try:
            entity = await client.get_entity(data.username)
            logger.info(f"Найдена сущность пользователя {data.username}: {entity}")
        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error(f"Ошибка при получении сущности для {data.username}: {e}")
            raise HTTPException(status_code=404, detail="Пользователь с указанным username не найден.")

        async def callback(async_client):

            await async_client(functions.messages.SetTypingRequest(
                peer=entity,
                action=types.SendMessageTypingAction()
            ))
            time.sleep(5)
            # Отправка сообщения
            msg = await async_client.send_message(entity, data.message)
            logger.info(f"Сообщение отправлено пользователю {data.username}: {msg}")
            return msg

        try:
            message = await asyncio.sleep(5, result=await callback(client))

            sender = None
            if message.from_id:
                sender = message.from_id.user_id

            user_id = None
            if message.from_id:
                user_id = message.from_id.user_id

            return {"message": "Сообщение успешно отправлено", "success": True,
                    "result": json.dumps({
                        "id": message.id,
                        "date": message.date.isoformat(),
                        "username": data.username,
                        # "channel": event.message.peer_id,
                        "via_bot_id": message.via_bot_id,
                        "text": message.raw_text,
                        "sender_id":  sender,
                        "from_id": {"user_id": user_id},
                        "user_id": message.from_id.user_id,
                        "channel_phone": sender_phone
                    })}

        except Exception as e:
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500)

    except Exception as e:
        logger.error(traceback.format_exc())
        logger.error(f"Ошибка при отправке сообщения: {str(e)} {sender_phone} {data.username}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:

        logger.info(f"Клиент Telegram {sender_phone} отключён")




@app.post("/get-sessions/")
async def get_sessions(data: GetMessagesRequest):
    """
    Получает все сообщения из указанного канала с полными данными.
    """

    try:
        # Подключаем клиента

        logger.info("Получение списк сессий")
        all_sessions = []
        for (dirpath, dirnames, filenames) in walk(SESSION_DIR):
            for filename in filenames:
                session_name = filename.split('.')[0]
                phone = session_name.split('_')[1]

                client = await get_create_client(phone)
                acc_info = await client.get_me()
                all_sessions.append(json.dumps({
                    'id': acc_info.id,
                    'fio': acc_info.first_name + ' ' + acc_info.last_name,
                    'color': acc_info.color,
                    'photo': acc_info.photo,
                    'phone': phone
                }))

        return { "sessions": all_sessions }
    except Exception as e:
        logger.error(f"Ошибка при получении сессий: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/log-out/")
async def log_out(data: GetMessagesRequest):

    phone = data.phone.strip().replace("+", "")
    client = await get_create_client(phone)
    try:

        result = await client.log_out()
        logger.debug(result)
        del running_clients[phone]
        return {"logout": result}
    except Exception as e:
        logger.error(f"Ошибка при получении сессий: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))