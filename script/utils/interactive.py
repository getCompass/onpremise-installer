#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

from utils.scriptutils import bcolors
from typing import Union
from getpass import getpass
import readline, ipaddress
import re

domain_pattern = re.compile(
    r"^(([a-zA-Z]{1})|([a-zA-Z]{1}[a-zA-Z]{1})|"
    r"([a-zA-Z]{1}[0-9]{1})|([0-9]{1}[a-zA-Z]{1})|"
    r"([a-zA-Z0-9][-_.a-zA-Z0-9]{0,61}[a-zA-Z0-9]))\."
    r"([a-zA-Z]{2,13}|[a-zA-Z0-9-]{2,30}.[a-zA-Z]{2,3})$"
)

mail_pattern = re.compile(r'([A-Za-z0-9]+[.\-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})+', re.IGNORECASE)
password_pattern = re.compile(r"^[^\s]+$", re.UNICODE)

phone_number_pattern = r'^\+?[1-9][0-9]{7,14}$'
protocol_pattern = r'^.+:\/\/'

class InteractiveValue:
    def __init__(
        self,
        name: str,
        comment: str,
        type: str,
        default_value: Union[int, str, None] = None,
        validation: Union[str, None] = None,
        options: list = [],
        force_default: bool = False,
        config: dict = {},
        is_required: bool = True,
    ):
        self.name = name
        self.default_value = default_value
        self.value = None
        self.type = type
        self.comment = comment
        self.options = options
        self.validation = validation
        self.force_default = force_default
        self.config = config
        self.is_required = is_required

    def set_value(self, value: Union[int, str, None] = None):
        self.value = value

    def get_value(self):
        if self.value is None and self.default_value is None:
            raise EmptyValueException

        return self.value if self.value != "" else self.default_value

    # Подставить значение из конфига
    def from_config(self):
        if self.config == {}:
            raise EmptyConfigException

        value = self.config.get(self.name)
        error = ""

        if (value is None or (value == "")) and self.is_required:
            raise IncorrectValueException(self.name, bcolors.WARNING + "В конфигурации отсутствует значение для поля %s " % self.name + bcolors.ENDC)

        if ((value is None) or (value == "")) and not self.is_required:

            if self.default_value is None:
                return None
            else:
                value = self.default_value

        # если значение должно быть булевым - конвертим
        if self.type == "bool":
            value = bool(value == "true" or value == 1)
        # если значение должно быть интовым - конвертим
        if self.type == "int":
            try:
                value = int(value)
            except:
                raise IncorrectValueException(self.name, bcolors.WARNING + "В конфигурации введено нечисловое значение для поля %s" % self.name + bcolors.ENDC)
        if self.type == "arr_phone_prefix":

            string_values = ""
            if type(value) is not list:
                # разбиваем строку через запятую
                code_list = value.split(",")
            else:
                code_list = value

            for index, code in enumerate(code_list):
                # убираем отступы
                # проверяем наличие + в начале кода, ставим если его нет
                # оборачиваем в кавычки
                code = str(code).strip()
                error = validate_phone_prefix(code)
                code_list[index] = code

            value = self.prepare_arr(code_list)

        if self.type == "arr":
            value = self.prepare_arr(value)

        if self.type == "arr_join":
            value = ",".join(value)

        # если запрашивается значение или значение не пустое
        if (self.is_required or (value != "")) and self.type != "arr":
            error = validate(value, self.validation)

        if error != "":
            raise IncorrectValueException(self.name, bcolors.WARNING + error + ", параметр в конфиге %s" % self.name + bcolors.ENDC)

        self.value = value
        return self.value

    # подготавливаем массив
    def prepare_arr(self, value):

        output = []

        if type(value) is not list:
            # разбиваем строку через запятую
            item_list = value.split(",")
        else:
            item_list = value
        for index, item in enumerate(item_list):
            # убираем отступы
            # оборачиваем в кавычки
            item = str(item).strip()

            # валидируем каждое значение
            error = validate(item, self.validation)
            
            if error != "":
                raise IncorrectValueException(self.name, bcolors.WARNING + error + ", параметр в конфиге %s" % self.name + bcolors.ENDC)
            output.append(item)
        if len(output) < 1 and self.is_required:
            raise IncorrectValueException(self.name, bcolors.WARNING + "В конфигурации не введено перечисление для поля %s, исправьте и попробуйте еще раз" % self.name + bcolors.ENDC)

        return output

    # Попросить значение у пользователя
    def input(self):
        # формируем строку коммента значения по умолчанию
        if self.default_value is None:
            default_value_string = ""
        else:
            default_value_string = (
                " [" + bcolors.OKBLUE + str(self.default_value) + bcolors.ENDC + "] "
            )

        if self.options == []:
            options_string = ""
        else:
            options_string = " [" + ", ".join(self.options) + "] "

        # получаем значение от пользователя
        if self.force_default and (self.default_value is not None):
            value = str(self.default_value)
        elif self.type == "password":
            value = getpass(self.comment + default_value_string + options_string + ": ")
        else:
            value = input(self.comment + default_value_string + options_string + ": ")

        value = value.strip()
        if value == "" and self.default_value != "":
            value = self.default_value

        if value == "" or value is None:
            print(
                bcolors.WARNING
                + "Не введено значение, попробуйте еще раз"
                + bcolors.ENDC
            )
            return self.input()

        if self.options != [] and value not in self.options:
            print(bcolors.WARNING + "Выбрано неверное значение" + bcolors.ENDC)
            return self.input()
        # если значение должно быть интовым - конвертим
        if self.type == "int":
            value = int(value)

        if self.type == "arr_phone_prefix":
            if type(value) is not list:
                # разбиваем строку через запятую
                code_list = value.split(",")
                string_values = ""
                for index, code in enumerate(code_list):
                    # убираем отступы
                    # проверяем наличие + в начале кода, ставим если его нет
                    # оборачиваем в кавычки
                    code = code.strip()
                    if "+" not in code:
                        code = f"+{code}"

                    error = validate_phone_prefix(code)

                    if error != "":
                        print(bcolors.WARNING + error + bcolors.ENDC)
                        return self.input()

                    string_values += f'"{code}"'

                    if index != len(code_list) - 1:
                        string_values += ", "

                # отдаём в виде массива
                value = f"[{string_values}]"
            else:
                value = "[]"

        if self.is_required or (value != ""):
            error = validate(value, self.validation)

        if error != "":
            print(bcolors.WARNING + error +", поле %s" % self.name + bcolors.ENDC)
            return self.input()

        self.value = value

        return self.value

def validate(value: str, validation: Union[str, None]) -> str:
    if validation is None :
        return ""
    if validation == "ip":
        return validate_ip(value)
    if validation == "idna":
        return validate_idna(value)
    if validation == "phone":
        return validate_phone(value)
    if validation == "mail":
        return validate_mail(value)
    if validation == "mail_password":
        return validate_mail_password(value)
    
    return "Не найден тип валидации"

def validate_phone(phone: str) -> str:

    match = re.match(phone_number_pattern, phone)
    if match is None:
        return "Неверный номер телефона"

    return ""

def validate_mail(mail: str) -> str:

    match = re.match(mail_pattern, mail)
    if match is None:
        return "Неверный формат почты"

    return ""
def validate_mail_password(password: str) -> str:

    password_length = len(password)

    if password_length < 8 or password_length > 40:
        return "Пароль должен содержать от 8 до 40 символов"

    match = re.match(password_pattern, password)
    if match is None:
        return "Неверный формат пароля"

    return ""

def validate_phone_prefix(phone_prefix: str) -> str:

    if len(phone_prefix) > 14:
        return "Префикс больше 14 символов"

    for i, c in enumerate(phone_prefix):
        if not c.isnumeric() and not (c == "+" and i == 0):
            return "Недопустимые знаки в телефонном префиксе"

    return ""
def validate_ip(value: str) -> str:
    try:
        ipaddress.ip_address(value)
        return ""
    except ValueError:
        return "Неверный ip адрес"


def validate_idna(value: str) -> str:

    try:
        ipaddress.ip_address(value)
        return "Передан IP вместо домена"
    except ValueError:
        pass

    match = re.match(protocol_pattern, value)
    if match is not None:
        return "Передан протокол в домене"

    try:
        value.encode("idna").decode()
        return ""
    except:
        return "Неправильное значение для домена"


# исключение пустого значения
class EmptyValueException(Exception):
    "Cant use empty value"
    pass


# исключение пустого конфига
class EmptyConfigException(Exception):
    "Cant use empty config"
    pass

class IncorrectValueException(Exception):

    def __init__(self, field, message="Некорректное значение"):
        self.field = field
        self.message = message
        super().__init__(self.message)
