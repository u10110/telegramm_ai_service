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
            ],
            DATABASES={
                'default': {
                #     'ENGINE': 'django.db.backends.postgresql',
                #     'NAME': 'eliment',  # Имя базы данных
                #     'USER': 'postgres',      # Пользователь базы данных
                #     'PASSWORD': '1',  # Пароль базы данных
                #     'HOST': '127.0.0.1',          # Хост базы данных (или IP)
                #     'PORT': '5432',               # Порт PostgreSQL
                # }
                    'ENGINE': 'django.db.backends.postgresql',
                    'NAME': 'eliment',  # Имя базы данных
                    'USER': 'eliment',      # Пользователь базы данных
                    'PASSWORD': '1K7dG2cGiWbL',  # Пароль базы данных
                    'HOST': '49.13.104.130',          # Хост базы данных (или IP)
                    'PORT': '53743',               # Порт PostgreSQL
                }
            },
            TIME_ZONE='UTC',
            USE_TZ=True,
            STATIC_URL='/static/',
        )
