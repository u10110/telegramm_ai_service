"""
Telegram Message Sender Service
This module handles automated message sending via Telegram based on client settings and projects.
"""

from typing import List, Dict, Optional
import os
import datetime
import requests
from django.db.models import F, QuerySet
from django_settings import configure_django
from dotenv import load_dotenv
import django

# Load environment variables
load_dotenv()

# Configure Django
configure_django()
django.setup()

# Import models after Django configuration
from telethon_send_messages.models import (
    ClientSettings,
    Project,
    Channel,
    TgID,
    Chat
)

# Constants
PID_FILE = "sndr.lock"
FASTAPI_HOST = os.getenv("FASTAPI_HOST")
GPT_ASSISTANT_URL = "https://eliment.ai/api/v1/gpt-assistant/"

class ProcessLockManager:
    """Manages process locking to prevent multiple instances."""
    
    @staticmethod
    def check_and_create_lock() -> bool:
        """
        Check if process is running and create lock file if not.
        
        Returns:
            bool: True if lock was created, False if process is already running
        """
        if os.path.exists(PID_FILE):
            print("sndr.py is already running.")
            return False
            
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
        return True

    @staticmethod
    def remove_lock():
        """Remove the process lock file."""
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)

class ClientManager:
    """Handles client-related operations."""
    
    @staticmethod
    def get_active_clients() -> QuerySet:
        """
        Get all clients with positive balance.
        
        Returns:
            QuerySet: Active clients with balance > 0
        """
        return ClientSettings.objects.filter(balance__gt=0)

    @staticmethod
    def get_active_projects(client: ClientSettings, current_time: datetime.time) -> QuerySet:
        """
        Get active projects for a client at current time.
        
        Args:
            client: Client settings object
            current_time: Current time to check project activity
            
        Returns:
            QuerySet: Active projects for the client
        """
        return Project.objects.filter(
            client=client.client_id,
            is_active=True,
            time_start__lte=current_time,
            time_end__gte=current_time,
        )

class MessageProcessor:
    """Handles message processing and sending."""
    
    @staticmethod
    def get_combined_messages(chat: Chat) -> Optional[str]:
        """
        Combine new messages from chat into single text.
        
        Args:
            chat: Chat object to process
            
        Returns:
            Optional[str]: Combined messages or None if no new messages
        """
        last_answer = Chat.objects.filter(
            user_id=chat.user_id,
            message_type="anwser"
        ).order_by('-created_at').first()

        query_filter = {
            'user_id': chat.user_id,
            'message_type': "question"
        }
        
        if last_answer:
            query_filter['created_at__gt'] = last_answer.created_at

        new_messages = Chat.objects.filter(**query_filter).order_by('-created_at')
        
        return "\n".join(new_messages.values_list("user_message", flat=True)) if new_messages.exists() else None

    @staticmethod
    def send_to_gpt_assistant(
        tgid_id: int,
        project_id: int,
        question: str,
        channel_phone: str,
        user_id: int
    ) -> Optional[str]:
        """Send message to GPT assistant and get response."""
        payload = {
            "tgid_id": tgid_id,
            "project_id": project_id,
            "question": question,
            "channel_phone": channel_phone,
            "user_id": user_id
        }
        
        try:
            response = requests.post(GPT_ASSISTANT_URL, data=payload)
            if response.status_code == 200:
                return response.json().get("anwser")
            print(f"GPT Assistant API error: {response.text}")
            return None
        except Exception as e:
            print(f"GPT Assistant connection error: {e}")
            return None

    @staticmethod
    def send_message_to_telegram(phone: str, user_id: int, message: str) -> bool:
        """Send message via Telegram API."""
        payload = {
            "phone": phone,
            "username": user_id,
            "message": message
        }
        
        try:
            response = requests.post(
                f"{FASTAPI_HOST}/send-message/",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Telegram API error: {e}")
            return False



class ProjectProcessor:
    """Управляет обработкой проектов и их каналов."""
    
    @staticmethod
    def process_project(project: Project) -> None:
        """
        Обрабатывает отдельный проект: фильтрует активные каналы, 
        получает TG ID и обрабатывает новые сообщения.

        Args:
            project: Объект проекта для обработки
        """
        # Получаем активные каналы проекта
        channels = Channel.objects.filter(
            client=project.client_id,
            project_id=project.id,
            remaining_messages__gt=0,
            is_active=True
        )

        if not channels.exists():
            print(f"Проект {project.id} не имеет активных каналов")
            return

        # Получаем чаты для всех каналов проекта
        chat_map = ProjectProcessor._get_existing_chats_by_phone(channels)

        # Обрабатываем каждый канал
        for channel in channels:
            ProjectProcessor._process_single_channel(channel, project, chat_map)

    @staticmethod
    def _get_existing_chats_by_phone(channels: QuerySet) -> Dict[str, List[Chat]]:
        """
        Получает существующие чаты для каналов по номеру телефона.

        Args:
            channels: QuerySet каналов для обработки

        Returns:
            Dict[str, List[Chat]]: Словарь чатов, где ключ - номер телефона
        """
        chat_map = {}
        for channel in channels:
            chats = Chat.objects.filter(user_name=channel.phone).distinct('user_name', 'user_id')
            chat_map[channel.phone] = list(chats) if chats.exists() else []
        return chat_map

    @staticmethod
    def _process_single_channel(channel: Channel, project: Project, chat_map: Dict[str, List[Chat]]) -> None:
        print(f"Обработка канала: {channel.id}, телефон: {channel.phone}")
        
        message_processor = MessageProcessor()
        
        try:
            # Получаем TG ID, у которых нет сообщений
            new_tgids = TgID.objects.filter(
            recipient__project_id=project.id  # Связь через таблицу Recipient
            ).exclude(
                tg_id__in=Chat.objects.filter(
                    message_type="anwser",
                    project_id=project.id
                    # user_name=channel.phone,
                ).values('user_id')
            )

            # Обрабатываем новых пользователей
            for tgid in new_tgids:
                print(f"Новый получатель {tgid.tg_id}" )
                message = message_processor.send_to_gpt_assistant(
                    tgid_id=tgid.id,
                    project_id=project.id,
                    question="",  # Пустой вопрос для нового пользователя
                    channel_phone=channel.phone,
                    user_id=tgid.tg_id
                )

                if message and message_processor.send_message_to_telegram(
                    channel.phone,
                    tgid.tg_id,
                    message
                ):
                    # Chat.objects.create(
                    #     user_id=tgid.tg_id,
                    #     user_name=channel.phone,
                    #     client_id=project.client_id,
                    #     project_id=project.id,
                    #     user_message=message,
                    #     message_type="anwser"
                    # )
                    channel.remaining_messages = F('remaining_messages') - 1
                    channel.save()

            # Обрабатываем существующие чаты
            chat_list = chat_map.get(channel.phone, [])
            if not chat_list:
                print(f"Нет активных чатов для телефона {channel.phone}")
                return

            print(f"Обработка канала {channel.title} {channel.phone} "
                f"для чатов: {len(chat_list)} чатов")

            for chat in chat_list:
                ProjectProcessor._process_chat(
                    chat=chat,
                    channel=channel,
                    project=project,
                    message_processor=message_processor
                )

        except Exception as e:
            print(f"Ошибка при обработке канала {channel.title}: {e}")

    @staticmethod
    def _process_chat(
        chat: Chat,
        channel: Channel,
        project: Project,
        message_processor: MessageProcessor
    ) -> None:
        tgid = TgID.objects.filter(tg_id=chat.user_id).first()
        if not tgid:
            return

        combined_message = message_processor.get_combined_messages(chat)
        if not combined_message:
            return

        message = message_processor.send_to_gpt_assistant(
            tgid_id=tgid.id,
            project_id=project.id,
            question=combined_message,
            channel_phone=channel.phone,
            user_id=chat.user_id
        )

        if message:
            if message_processor.send_message_to_telegram(
                channel.phone,
                chat.user_id,
                message
            ):
                # Chat.objects.create(
                #     user_id=chat.user_id,
                #     user_name=channel.phone,
                #     client_id=project.client_id,
                #     project_id=project.id,
                #     user_message=message,
                #     message_type="anwser"
                # )
                channel.remaining_messages = F('remaining_messages') - 1
                channel.save()
                

def main_runner():
    """Главная функция выполнения задачи."""
    # if not ProcessLockManager.check_and_create_lock():
    #     sys.exit(1)

    try:
        current_time = datetime.datetime.now().time()
        clients = ClientManager.get_active_clients()

        for client in clients:
            print(f"Обработка клиента {client.client_id}")
            projects = ClientManager.get_active_projects(client, current_time)
            
            project_processor = ProjectProcessor()
            for project in projects:
                project_processor.process_project(project)
                
    finally:
        ProcessLockManager.remove_lock()

# Run the script
if __name__ == "__main__":
    main_runner()