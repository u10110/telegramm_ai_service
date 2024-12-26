import os
import time
import subprocess

# Пути к исполняемым файлам
script_path_prsr = "telethon_send_messages/prsr.py"
script_path_sndr = "telethon_send_messages/sndr.py"

# Проверяем, существуют ли файлы
if not os.path.exists(script_path_prsr):
    print(f"Файл {script_path_prsr} не найден.")
    exit(1)

if not os.path.exists(script_path_sndr):
    print(f"Файл {script_path_sndr} не найден.")
    exit(1)

while True:
    try:
        # Сначала запускаем prsr.py
        print("Запуск prsr.py...")
        process_prsr = subprocess.Popen(["python3", script_path_prsr])
        process_prsr.wait()  # Ждем завершения выполнения prsr.py
        
        # После этого запускаем sndr.py
        print("Запуск sndr.py...")
        process_sndr = subprocess.Popen(["python3", script_path_sndr])
        process_sndr.wait()  # Ждем завершения выполнения sndr.py
        
    except Exception as e:
        print(f"Ошибка при запуске скриптов: {e}")

    # Ждем 15 секунд перед следующим циклом
    time.sleep(15)