#!/usr/bin/env python3

from hashlib import pbkdf2_hmac
from io import BytesIO
from os import urandom
from pathlib import Path
from utils import scriptutils
from Crypto.Cipher import AES

import base64
import docker
import docker.errors

docker_client = docker.from_env()


def encrypt(password: bytes, to_encrypt: bytes):
    """
    Шифрует данные с использованием CBC-алгоритма.
    Вектор шифрования и ключ шифрования получаются из pbkdf2
    исходного ключа шифрования, что совместимо с консольным OpenSSL.
    """

    bs = AES.block_size
    salt = urandom(bs - len(b'Salted__'))
    pbk = pbkdf2_hmac('sha256', password, salt, 10000, 48)
    key = pbk[:32]
    iv = pbk[32:48]

    cipher = AES.new(key, AES.MODE_CBC, iv)
    result = (b'Salted__' + salt)
    to_encrypt_bytes = BytesIO(to_encrypt)
    finished = False

    while not finished:

        chunk = to_encrypt_bytes.read(1024 * bs)

        if len(chunk) == 0 or len(chunk) % bs != 0:
            padding_length = (bs - len(chunk) % bs) or bs
            chunk += (padding_length * chr(padding_length)).encode()
            finished = True

        result += cipher.encrypt(chunk)

    return result


def is_docker_secret_exists(name: str):
    """Проверяет существование докер-секрета"""

    try:
        # проверяем наличие существующего секрета
        docker_client.secrets.get(name)
    except docker.errors.NotFound:
        return False

    return True


def delete_docker_secret(name: str):
    """Удаляет докер-секрет"""
    docker_client.secrets.get(name).remove()


def create_docker_secret(name: str, value: bytes):
    """создает докер-секрет"""
    docker_client.secrets.create(name=name, data=value)


class CompassSecretData:
    """Класс подготовки секрета"""

    def __init__(self, desc_before: str, desc_after: str):
        self.desc_before = desc_before
        self.desc_after = desc_after
        self.name = ""

    def init(self):
        """Создает секрет из данных"""
        pass

    def _check_existing(self):
        """Проверяет наличие секрета"""

        if is_docker_secret_exists(self.name):
            print(f"Секрет {self.name} уже существует. Удалите секрет, прежде чем создавать новый.")
            print(f"Важно! Удаление секрета {self.name} может привести к нестабильности работы приложения.")

            if input("Удалить секрет? [Y/n]\n").lower() != "y":
                scriptutils.die("Установка прервана")

            delete_docker_secret(self.name)


class CompassDatabaseEncryptionSecretKey(CompassSecretData):
    """Класс подготовки секрета шифрования БД"""

    def __init__(self, desc_before: str, desc_after: str):

        super().__init__(desc_before, desc_after)
        self.name = "compass_database_encryption_secret_key"

    def pick_representation(self, key_name: str = "ключа шифрования") -> int:
        """Показывает сообщение с выбором представления файла"""

        print(f"Укажите представление для {key_name}:")
        print("1) base64 представление;")
        print("2) файл с base64 представлением;")
        print("3) файл с двоичным представлением.")

        representation = input(f"Выберите представление: ")
        if not representation.isdigit():
            scriptutils.die("Выбрано неверное представление.")

        representation = int(representation)
        if representation < 1 or representation > 3:
            scriptutils.die("Выбрано неверное представление.")

        return representation

    def represent_as_base64_string(self) -> bytes:
        """Обрабатывает ключ как base64 строку"""

        base64_key = input("Введите base64 представление ключа: ").strip()

        try:
            return base64.b64decode(base64_key)
        except:
            scriptutils.die("Не удалось раскодировать base64 представление.")

    def represent_as_base64_file(self) -> bytes:
        """Обрабатывает ключ как base64 файл"""

        file_path = input("Введите путь к файлу с base64 представлением ключа: ")
        if not Path(file_path).exists():
            scriptutils.die("Не найден файл с base64 представлением ключа.")

        try:
            with open(file_path, "r") as file:
                base64_key = file.read()
        except:
            scriptutils.die("Не удалось прочитать base64 из файла.")

        try:
            return base64.b64decode(base64_key)
        except:
            scriptutils.die("Не удалось раскодировать base64 представление.")

    def represent_as_binary_file(self) -> bytes:
        """Обрабатывает ключ как двоичный файл"""

        file_path = input("Введите путь к файлу с двоичным представлением ключа: ")
        if not Path(file_path).exists():
            scriptutils.die("Не найден файл с двоичным представлением ключа.")

        with open(file_path, "rb") as file:
            return file.read()

    def init(self):
        """Создает секрет из данных"""

        # убедимся, что существующего секрета нет
        self._check_existing()

        # получим у пользователя информацию по ключу шифрования
        representation = self.pick_representation("ключа шифрования данных")

        if representation == 1:
            encryption_binary_key = self.represent_as_base64_string()
        elif representation == 2:
            encryption_binary_key = self.represent_as_base64_file()
        elif representation == 3:
            encryption_binary_key = self.represent_as_binary_file()
        else:
            raise RuntimeError

        # получим у пользователя информацию по мастер-ключу
        representation = self.pick_representation("мастер ключа")

        if representation == 1:
            master_binary_key = self.represent_as_base64_string()
        elif representation == 2:
            master_binary_key = self.represent_as_base64_file()
        elif representation == 3:
            master_binary_key = self.represent_as_binary_file()
        else:
            raise RuntimeError

        try:
            secret_key = encrypt(master_binary_key, encryption_binary_key)
        except:
            scriptutils.die("Не удалось сформировать ключ-секрет.")
            exit(1)

        try:
            create_docker_secret(self.name, base64.b64encode(secret_key))
        except:
            scriptutils.die("Не удалось создать docker-секрет.")

        print("---")
        print("Мастер ключ для конфигурации: %s" % base64.b64encode(master_binary_key).decode("utf-8"))
        print(scriptutils.success("Секрет с ключом-секретом создан"))


# список пресетов секретов для создания
secret_data_list = [

    CompassDatabaseEncryptionSecretKey(
        "Ключ-секрет шифрования БД. Для создания потребуется ключ шифрования БД и мастер ключ в двоичном или base64 представлении",
        "Ключ-секрет шифрования БД.",
    )
]


def pick():
    """Функция выбора секрета для создания"""

    i = 1

    print("Доступные для создания секреты: ")
    for secret_data in secret_data_list:
        print(f"{i}) " + secret_data.desc_before)

    index = input("Укажите секрет: ")

    if not index.isdigit():
        scriptutils.die("Указан неверный секрет.")

    i = int(index) - 1

    if i < 0:
        scriptutils.die("Указан неверный секрет.")

    try:
        picked: CompassSecretData = secret_data_list[i]
    except IndexError:
        scriptutils.die("Указан неверный секрет.")
        exit(1)

    return picked.init()


# поехали
pick()
