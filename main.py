from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from telethon import TelegramClient, events
import os
import logging
from telethon.tl.types import PeerUser, User
from datetime import datetime, timedelta, timezone
from telethon.tl.functions.messages import GetHistoryRequest
from os import walk

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI()

API_ID = '21275822'
API_HASH = '300cc403b6ad13139d9e16d8dca9ea4e'
SESSION_DIR = os.path.join(os.getcwd(), 'sessions')
os.makedirs(SESSION_DIR, exist_ok=True)

# Временное хранилище phone_code_hash для каждого номера
phone_hash_store = {}

running_clients = []


def print_event(sc):
    print("Hello")
    sc.enter(5, 1, print_event, (sc,))


async def start_client(session_name):
    session_file = os.path.join(SESSION_DIR, session_name)
    client = TelegramClient(session_file, API_ID, API_HASH)

    @client.on(events.NewMessage)
    async def my_event_handler(event):
        print(event.raw_text)
        #if 'hello' in event.raw_text:
        #    await event.reply('hi!')

    await client.start()
    await client.connect()
    client.run_until_disconnected()

    running_clients.append((session_name, client))
    logger.info(f"Клиент Telegram подключён: {session_name}")


@app.on_event("startup")
async def startup_event():
    for (dirpath, dirnames, filenames) in walk(SESSION_DIR):
        for filename in filenames:
            session_name = filename.split('.')[0]
            print(session_name)
            await start_client(session_name)


async def get_or_start_client(session_name):
    clients_dict = dict(running_clients)
    if clients_dict[session_name] is not None:
        return clients_dict[session_name]
    clients_dict[session_name] = await start_client(session_name)
    return clients_dict[session_name]


@app.post("/send-code/")
async def send_code(phone: str):
    phone = phone.strip().replace("+", "")
    logger.info(f"Получен запрос на отправку кода для телефона: {phone}")
    session_name = "session_" + phone

    # Если файл сессии существует, удаляем его
    if os.path.exists(session_name + ".session"):
        try:
            os.remove(session_name + ".session")
            logger.info(f"Существующий файл сессии удалён: {session_name}.session")
        except Exception as e:
            logger.error(f"Ошибка при удалении файла сессии: {str(e)}")
            raise HTTPException(status_code=500, detail="Ошибка при очистке предыдущей сессии")

    client = TelegramClient(session_name, API_ID, API_HASH)

    try:
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
        raise HTTPException(status_code=500, detail=str(e))


class VerifyCodeRequest(BaseModel):
    phone: str
    code: str

@app.post("/verify-code/")
async def verify_code(data: VerifyCodeRequest):
    phone = data.phone
    phone = phone.strip().replace("+", "")
    code = data.code

    logger.info(f"Получен запрос на подтверждение кода для телефона: {phone}")

    client = TelegramClient("session_" + phone, API_ID, API_HASH)

    try:
        print(f"phone_hash_store {phone_hash_store}")
        phone_code_hash = phone_hash_store.get(phone)
        
        if not phone_code_hash:
            raise HTTPException(status_code=400, detail="Код не был отправлен или истёк")

        await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        logger.info(f"Код подтверждён для телефона: {phone}")

        del phone_hash_store[phone]
        return {"message": f"Авторизация завершена для номера {phone}", "success": True}
    except Exception as e:
        logger.error(f"Ошибка при подтверждении кода: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get-users/")
async def get_users(phone: str):
    """
    Получает список всех пользователей, с которыми велась переписка.
    """
    phone = phone.strip().replace("+", "")
    session_name = "session_" + phone
    print(f"session_name {session_name}")

    client = await get_or_start_client(session_name)

    try:

        dialogs = await client.get_dialogs()
        for dialog in dialogs:
            print(f"Dialog: {dialog.id}, Name: {dialog.name}, Entity: {type(dialog.entity)}")

        users = [
            {"id": dialog.id, "name": dialog.name} # ! dialog.name это имя аккаунта а не username
            for dialog in dialogs
            if isinstance(dialog.entity, User)
        ]
        return {"users": users}
    except Exception as e:
        logger.error(f"Ошибка при получении списка пользователей: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


class GetMessagesRequest(BaseModel):
    phone: str
    user_id: int
    limit: int


from telethon.tl.types import PeerUser

async def get_all_messages(client, channel_id, limit):
    try:
        if not channel_id:
            raise ValueError("channel_id не может быть None.")

        entity = await client.get_entity(channel_id)

        history = await client(GetHistoryRequest(
            peer=entity,
            limit=limit,
            offset_date=None,
            offset_id=0,
            max_id=0,
            min_id=0,
            add_offset=0,
            hash=0
        ))
        print(f"Получено сообщений: {len(history.messages)}")

        all_messages = []
        for message in history.messages:
            user_id = None
            username = None

            if message.from_id and isinstance(message.from_id, PeerUser):
                user_id = message.to_id.user_id
                try:
                    sender = await client.get_entity(user_id)
                    username = getattr(sender, 'username', None)
                except Exception as e:
                    print(f"Ошибка при получении username: {e}")

            if not user_id and message.sender_id:
                try:
                    sender = await client.get_entity(message.sender_id)
                    user_id = sender.id
                    username = getattr(sender, 'username', None)
                except Exception as e:
                    print(f"Ошибка при получении username через sender_id: {e}")

            print(f"Message ID: {message.id}, Date: {message.date}, Text: {message.message}, User ID: {user_id}, Username: @{username if username else 'None'}")

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
        print(f"Ошибка при получении сообщений: {e}")
        raise

@app.get("/health/")
async def health():
    return {"heath": 'Ok'}


@app.post("/get-messages/")
async def get_messages(data: GetMessagesRequest):
    """
    Получает все сообщения из указанного канала с полными данными.
    """
    phone = data.phone.strip().replace("+", "")
    session_name = os.path.join(SESSION_DIR, "session_" + phone)

    client = await get_or_start_client(session_name)

    try:
        # Подключаем клиента
        await client.connect()
        logger.info("Клиент Telegram подключён")

        # ID канала или пользователя
        channel_id = data.user_id

        # Получаем все сообщения
        all_messages = await get_all_messages(client, channel_id, data.limit)

        return {"messages": all_messages}
    except Exception as e:
        logger.error(f"Ошибка при получении сообщений: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await client.disconnect()
        logger.info("Клиент Telegram отключён")


class SendMessageRequest(BaseModel):
    phone: str
    username: str
    message: str
    
    
from telethon.tl.functions.contacts import ResolveUsernameRequest
from telethon.tl.types import PeerUser
from telethon.errors.rpcerrorlist import UserNotMutualContactError, UserPrivacyRestrictedError
from telethon.tl.types import InputPeerUser

from telethon.tl.functions.contacts import ImportContactsRequest
from telethon.tl.types import InputPhoneContact, InputPeerUser
@app.post("/send-message/")
async def send_message(data: SendMessageRequest):
    """
    Отправляет сообщение пользователю через Telegram API.
    - `data.phone`: Аккаунт, с которого отправляем (номер телефона отправителя).
    - `data.username`: Ник пользователя, которому отправляем (например, @username).
    - `data.message`: Сообщение.
    """
    sender_phone = data.phone.strip().replace("+", "")  # Аккаунт отправителя
    session_name = os.path.join(SESSION_DIR, "session_" + sender_phone)

    client = await get_or_start_client(session_name)

    try:
        await client.connect()
        logger.info(f"Клиент Telegram подключён с аккаунта: {sender_phone}")

        # Определяем сущность пользователя по username
        try:
            entity = await client.get_entity(data.username)
            logger.info(f"Найдена сущность пользователя {data.username}: {entity}")
        except Exception as e:
            logger.error(f"Ошибка при получении сущности для {data.username}: {e}")
            raise HTTPException(status_code=404, detail="Пользователь с указанным username не найден.")

        # Отправка сообщения
        msg = await client.send_message(entity, data.message)
        logger.info(f"Сообщение отправлено пользователю {data.username}: {msg}")
        return {"message": "Сообщение успешно отправлено", "success": True}

    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await client.disconnect()
        logger.info(f"Клиент Telegram {sender_phone} отключён")


