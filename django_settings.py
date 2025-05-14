import os
from django.conf import settings

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def configure_django():
    """
    Конфигурирует настройки Django для запуска в любом скрипте.
    """
    if not settings.configured:
        settings.configure(
            DEBUG=True,
            SECRET_KEY='your_secret_key_here',
            ALLOWED_HOSTS=['127.0.0.1', 'localhost'],
            INSTALLED_APPS=[
                # "django.contrib.auth",
                'django.contrib.contenttypes',
                'django.contrib.auth',
                'django.contrib.sessions',
                'django.contrib.messages',
                'django.contrib.staticfiles',
                # Если вам нужен админ:
                'django.contrib.admin',
            ]
            ,
            TIME_ZONE='UTC',
            USE_TZ=True,
            STATIC_URL='/static/',
        )
