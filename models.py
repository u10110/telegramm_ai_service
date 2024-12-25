
from django.db import models
from django.contrib.auth.models import User
import datetime
from django.contrib.auth.models import AbstractUser, BaseUserManager



class UserManager(BaseUserManager):
    """Define a model manager for User model with no username field."""

    def _create_user(self, phone, password=None, **extra_fields):
        if not phone:
            raise ValueError("The given phone must be set")
        user = self.model(phone=phone, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, phone, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(phone, password, **extra_fields)

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(phone, password, **extra_fields)


class User(AbstractUser):
    phone = models.CharField(max_length=15, null=True, unique=True)
    username = models.CharField(unique=False, max_length=50)
    code = models.CharField(max_length=50, null=True)
    last_sms_date = models.DateTimeField(null=True)
    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = []

    def __str__(self):
        return str(self.id)

    class Meta:
        app_label = 'home'



class ClientSettings(models.Model):
    class Meta:
        app_label = 'home'
        verbose_name = "настройки"
        verbose_name_plural = "Настройки"

    client = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="ClientSettings"
    )
    tg_chat_id = models.TextField(null=True, blank=True)
    tg_token = models.TextField(null=True, blank=True)
    balance = models.IntegerField(max_length=55, default=0)
    # wb_token = models.TextField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, auto_now_add=True)
    # tochka_number = models.ForeignKey(
    #     TochkaNumbers, on_delete=models.CASCADE, null=True
    # )
    wb_updated = models.DateTimeField(null=True)



class Project(models.Model):
    class Meta:
        app_label = 'home'
        verbose_name = "Проект"
        verbose_name_plural = "Проекты"

    GPT_VERSION_CHOICES = [
        (1, 'OpenAI GPT-4o'),
        (2, 'OpenAI GPT-4o mini'),
    ]
    OPTIONS = [
        (1, 'Входящие'),
        (2, 'Входящие и исходящие'),
    ]
    AGENT_TYPES = [
        ('sales_manager', 'Менеджер по продажам'),
        ('consultant', 'Консультант'),
        ('support_manager', 'Менеджер поддержки'),
        ('review_manager', 'Менеджер по работе с отзывами'),
        ('info_business_manager', 'Менеджер для инфобиза'),
        ('services_manager', 'Менеджер в сфере услуг'),
        ('health_fitness_manager', 'Менеджер в сфере здоровья и фитнеса'),
    ]

    client = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=1000)
    agent_type = models.CharField(
        max_length=50,
        choices=AGENT_TYPES,
        default='sales_manager',
        verbose_name="Тип ИИ-агента"
    )
    status = models.CharField(max_length=55, default="active")
    is_active = models.BooleanField(default=False)
    work_option = models.IntegerField(choices=OPTIONS, default=1)
    gpt_version = models.IntegerField(choices=GPT_VERSION_CHOICES, default=1)
    hello_text = models.TextField(null=True)
    prompt = models.TextField()
    knowledge_base_text = models.TextField(null=True, blank=True)
    google_doc = models.URLField(
        null=True,
        blank=True,
        help_text="Ссылка на Google-документ (необязательно)"
    )
    per_conversation_limit = models.IntegerField(
        default=50,
        verbose_name="Лимит на одну переписку"
    )

    outgoing_limit = models.IntegerField(
        default=30,  # Значение по умолчанию
        verbose_name="Ограничение исходящих"
    )
    message_limit = models.IntegerField(default=30)
    time_start = models.TimeField(default=datetime.time(8, 0))
    time_end = models.TimeField(default=datetime.time(22, 0))
    updated_at = models.DateTimeField(auto_now=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    def get_agent_type_display(self):
        return dict(self.AGENT_TYPES).get(self.agent_type, self.agent_type)



class Recipient(models.Model):
    class Meta:
        app_label = 'home'
        verbose_name = "Получатели"
        verbose_name_plural = "Получатели"


    OPTIONS = [
        (1, 'Белый список'),
        (2, 'Черный список'),
    ]

    client = models.ForeignKey(User, on_delete=models.CASCADE)
    project_id = models.IntegerField(null=True)
    title = models.CharField(max_length=1000)
    status = models.CharField(max_length=55, default="active")
    work_option = models.IntegerField(choices=OPTIONS, default=1)
    updated_at = models.DateTimeField(auto_now=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return self.title
    
class TgID(models.Model):
    class Meta:
        app_label = 'home'
    recipient = models.ForeignKey(
        Recipient,
        related_name='tg_id_set',
        on_delete=models.CASCADE
    )
    tg_id = models.CharField(max_length=255)
    is_auto_active = models.BooleanField(default=True)


class Channel(models.Model):
    class Meta:
        app_label = 'home'
        verbose_name = "Канал"
        verbose_name_plural = "Каналы"
    STATUS_CHOICES = [
            ('unauthorized', 'Не авторизован'),
            ('authorized', 'Авторизован'),
            ('banned', 'Заблокирован'),
        ]
    SOURCE_CHOICES = [
        ('telegram', 'Telegram'),
        ('avito', 'Avito'),
        ('web_widget', 'Web Widget'),
        ('vk', 'VK'),
        ('email', 'E-mail'),
        ('whatsapp', 'WhatsApp'),
        ('instagram', 'Instagram'),
    ]


    # client = models.ForeignKey(User, on_delete=models.CASCADE)
    client = models.ForeignKey(User, on_delete=models.CASCADE)
    project_id = models.IntegerField(null=True)
    title = models.CharField(max_length=1000)
    is_active = models.BooleanField(default=False)
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default='telegram',
        verbose_name="Источник"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='unauthorized',
    )
    max_daily_messages = models.IntegerField(default=50)  # Максимальное количество сообщений в день
    remaining_messages = models.IntegerField(default=50)
    last_reset_date = models.DateField(default=datetime.date.today)
    phone = models.CharField(max_length=55,)
    tg_app_id = models.CharField(max_length=55, null=True, blank=True)
    tg_app_hash = models.CharField(max_length=55, null=True, blank=True)
    qr = models.TextField(null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return f"{self.title} ({self.phone})"


class Chat(models.Model):
    class Meta:
        app_label = 'home'
        verbose_name = "Чаты"
        verbose_name_plural = "Чаты"

    MESSAGE_TYPE = [
            ('anwser', 'Наше сообщение'),
            ('message', 'Сообщение пользователя'),
        ]

    # client = models.ForeignKey(User, on_delete=models.CASCADE)
    client_id = models.IntegerField()
    project_id = models.IntegerField()
    user_id = models.CharField(max_length=1000)
    messageId = models.CharField(null=True, max_length=1000)
    message_type = models.CharField(
        max_length=20,
        choices=MESSAGE_TYPE,
        default='message',
    )
    status = models.CharField(max_length=55, default="active")
    user_name = models.CharField(max_length=55, )
    user_message = models.CharField(max_length=1000, )
    sex = models.IntegerField(null=True)
    created_at = models.DateTimeField(null=True)


