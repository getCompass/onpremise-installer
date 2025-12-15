import json
import subprocess
import os
import sys
import argparse, yaml
from pathlib import Path

# получаем путь до файла conversation_key_list.json
script_dir = os.path.dirname(os.path.abspath(sys.modules[__name__].__file__))
json_file_path = os.path.join(script_dir, "conversation_key_list.json")

# ---АРГУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument('-v', '--values', required=False, default="compass", type=str, help='Название values файла окружения')
parser.add_argument('-e', '--environment', required=False, default="production", type=str, help='Окружение, в котором развернут проект')

args = parser.parse_args()

values_name = args.values
environment = args.environment

# путь до директории с инсталятором
installer_dir = str(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

default_values_file_path = Path("%s/src/values.yaml" % (installer_dir))
values_file_path = Path("%s/src/values.%s.yaml" % (installer_dir, values_name))

# задача для запуска скрипта кроном
script_path = os.path.abspath(sys.modules[__name__].__file__)
cron_job_command = f"python3 {script_path} auto"

# получить данные окружения из values
def get_values() -> dict:

    print(values_file_path)
    if not values_file_path.exists():
        print("Не найден файл со значениями для деплоя. Окружение было ранее развернуто?")
        exit(1)

    with values_file_path.open("r") as values_file:
        current_values = yaml.safe_load(values_file)
        current_values = {} if current_values is None else current_values

    with default_values_file_path.open("r") as values_file:
        default_values = yaml.safe_load(values_file)
        default_values = {} if default_values is None else default_values

    current_values = merge(default_values, current_values)

    if current_values.get("projects") is None or current_values["projects"].get("domino") is None:
        print("Файл со значениями невалиден. Окружение было ранее развернуто?")
        exit(1)

    return current_values

def merge(a: dict, b: dict, path=[]):

    for key in b:
        if key in a:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                merge(a[key], b[key], path + [str(key)])
            elif a[key] != b[key]:
                a[key] = b[key]
        else:
            a[key] = b[key]
    return a

# получаем контейнер монолита
def find_container_by_name(partial_name):
    result = subprocess.run(['docker', 'ps', '--filter', f'name={partial_name}', '--format', '{{.Names}}'],
                            stdout=subprocess.PIPE)
    container_name = result.stdout.decode('utf-8').strip()
    if container_name:
        print(f"Найден контейнер: {container_name}")
        return container_name
    else:
        print(f"Контейнер с именем, содержащим '{partial_name}', не найден.")
        # завершаем скрипт
        exit()

# открываем файл conversation_key_list.json
def load_keys_from_json(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
            print("conversation_key_list.json: найден")
            if validate_json(data):
                return data
            return {}
    except FileNotFoundError:
        print(f"Файл {filename} не найден.")
        return {}
    except json.JSONDecodeError:
        print(f"Ошибка при чтении JSON-файла {filename}.")
        return {}

# формируем команду для запуска скрипта
def form_command(keys_by_company):
    if not keys_by_company:
        print("Нет данных для формирования команды")
        exit()
    
    # используем точку с запятой как разделитель значений
    formatted_parts = []
    for company_id, company_data in keys_by_company.items():
        keys_str = ";".join(company_data["conversation_key_list"])
        formatted_parts.append(f"{company_id}:[{keys_str}]")
    
    script_data = f"[{','.join(formatted_parts)}]"
    company_id_list = list(keys_by_company.keys())
    
    # формируем команду
    command = f'php src/Compass/Pivot/sh/php/service/exec_company_update_script.php ' \
             f'--script-name=ClearConversations ' \
             f'--dry=0 ' \
             f'--log-level=2 ' \
             f'--module-proxy=[php_conversation] ' \
             f'--script-data=\'{script_data}\' ' \
             f'--company-list=[{",".join(map(str, company_id_list))}]'

    return command

# запускаем команду в контейнере
def run_command_in_container(container_name, command):
    try:
        # создаем процесс с возможностью взаимодействия
        process = subprocess.Popen(['docker', 'exec', '-i', container_name, 'sh', '-c', command],
                                 stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,
                                 universal_newlines=True)
        
        # отправляем 'y'
        stdout, stderr = process.communicate(input='y\n')
        
        # выводим stdout и stderr
        if stdout:
            print(stdout)
        if stderr:
            print(stderr)
            
        if process.returncode == 0:
            print(f"Команда успешно выполнена в контейнере {container_name}")
        else:
            print(f"Ошибка при выполнении команды: {stderr}")
            
    except Exception as e:
        print(f"Ошибка при выполнении команды очистки заданных чатов в контейнере: {e}")

# проверяем формат json
#{
#	"1": {
#		"conversation_key_list": [""]
#	}
#}
def validate_json(data):
    # если файл пустой
    if not data:
        print("Ошибка: файл с ключами путой.")
        return False

    # проверяем что data это словарь
    if not isinstance(data, dict):
        print("Ошибка: data не является словарем.")
        return False

    # проверяем id компании это число
    try:
        if not all(str(key).isdigit() for key in data.keys()):
            print("Ошибка: id компании не является числом.")
            return False
    except AttributeError:
        print("Ошибка: неверная структура данных.")
        return False

    # проверяем что каждая компания имеет список ключей
    for company_id, company_data in data.items():
        if not isinstance(company_data, dict):
            print(f"Ошибка: данные для компании {company_id} не являются словарем.")
            return False
        if "conversation_key_list" not in company_data:
            print(f"Ошибка: отсутствует conversation_key_list для компании {company_id}.")
            return False
        if not isinstance(company_data["conversation_key_list"], list):
            print(f"Ошибка: conversation_key_list для компании {company_id} не является списком.")
            return False
        if not all(isinstance(key, str) for key in company_data["conversation_key_list"]):
            print(f"Ошибка: не все ключи являются строками для компании {company_id}.")
            return False

    print("conversation_key_list.json: валидный")
    return True

# проверяем что установлен cron, если нет - подсвечиваем, даем команду на установку
def check_cron_installation():
    try:
        result = subprocess.run(['which', 'crontab'], 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE)
        
        if result.returncode == 0:
            print("Cron установлен в системе")
            return True
        else:
            print("Cron не установлен. Для установки выполните следующие команды:")
            print("sudo apt-get update")
            print("sudo apt-get install cron")
            print("\nПосле установки запустите службу:")
            print("sudo service cron start")
            print("\nДля автозапуска при перезагрузке:")
            print("sudo systemctl enable cron")
            return False
            
    except Exception as e:
        print(f"Ошибка при проверке установки cron: {str(e)}")
        return False

# проверяем существует ли задача в cron
def cron_job_exists(cron_job_command):
    try:
        # получаем текущие задачи cron
        result = subprocess.run(['crontab', '-l'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        # проверяем, существует ли уже задача
        if cron_job_command in result.stdout:
            print("Задача уже существует в crontab.")
            return True
        else:
            print("Задача не найдена в crontab.")
            return False
    except Exception as e:
        print(f"Ошибка при проверке задач в crontab: {str(e)}")
        return False

# добавляем задачу в cron
def add_cron_job(cron_job_command):
    try:
        # получаем текущие задачи cron
        result = subprocess.run(['crontab', '-l'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        # добавляем новую задачу в конец
        new_cron = result.stdout + f"0 10 * * 6 {cron_job_command} >> /dev/null 2>&1\n"
        
        # устанавливаем обновленный список задач
        subprocess.run(['crontab', '-'], input=new_cron, text=True)
        
        print("Задача успешно добавлена в crontab.")
    except Exception as e:
        print(f"Ошибка при добавлении задачи в crontab: {str(e)}")

# удаляем задачу из cron
def remove_cron_job(cron_job_command):
    try:
        # получаем текущие задачи cron
        result = subprocess.run(['crontab', '-l'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        # разбиваем на строки и фильтруем только нужную задачу
        lines = result.stdout.splitlines()
        new_lines = []
        for line in lines:
            # пропускаем только строку с точным совпадением нашей команды
            if f"python3 {script_path} auto" not in line:
                new_lines.append(line)
        
        # собираем обратно в строку с новой строкой в конце
        new_cron = "\n".join(new_lines) + "\n"
        
        # устанавливаем обновленный список задач
        subprocess.run(['crontab', '-'], input=new_cron, text=True)
        print("Задача успешно удалена из crontab.")
    except Exception as e:
        print(f"Ошибка при удалении задачи из crontab: {str(e)}")

# запускаем скрипт
def schedule_or_run_php_script(container_name, command):

    # add parameter check at the start
    if len(sys.argv) > 1 and sys.argv[1] == "auto":
        choice = "1"
    else:
        print("Выберите вариант:\n1) Запустить очистку заданных чатов сейчас\n2) Добавить задачу для очистки заданных чатов каждую субботу в 10:00 мск\n3) Убрать задачу для очистки заданных чатов каждую субботу в 10:00 мск")
        choice = input("Введите 1, 2 или 3: ")

    if choice == "1":
        
        # запускаем скрипт
        run_command_in_container(container_name, command)
        print(f"Скрипт очистки заданных чатов запущен")

    elif choice == "2":

        # проверяем установлен ли cron
        check_cron_installation()

        # если да, проверяем что задача не существует
        if not cron_job_exists(cron_job_command):

            # добавление задачи в crontab
            add_cron_job(cron_job_command)
            
    elif choice == "3":
        # удаление задачи из cron
        remove_cron_job(cron_job_command)
    else:
        print("Неверный выбор. Пожалуйста, введите 1, 2 или 3.")

# выполняем скрипт
if __name__ == "__main__":

    current_values = get_values()

    # собираем имя искомого контейнера
    partial_name = "%s-%s-monolith" % (environment, values_name)
    service_label = current_values.get("service_label") if current_values.get("service_label") else ""
    if service_label != "":
        partial_name = partial_name + "-" + service_label
    partial_name = partial_name + "_php-monolith"

    # получаем ключи из json
    keys = load_keys_from_json(json_file_path)

    # формируем команду для запуска скрипта
    command = form_command(keys)

    # получаем контейнер монолита
    container_name = find_container_by_name(partial_name)

    # если контейнер найден 
    if container_name:
        # запускаем скрипт
        schedule_or_run_php_script(container_name, command)