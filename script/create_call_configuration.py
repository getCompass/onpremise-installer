#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

from pathlib import Path
from utils import scriptutils
import collections.abc
import yaml
from utils.interactive import InteractiveValue

scriptutils.assert_root()

# ---АРГУМЕНТЫ СКРИПТА---#

parser = scriptutils.create_parser(
    description="Скрипт для генерации конфига для звонков.",
    usage="python3 script/create_call_configuration.py",
    epilog="Пример: python3 script/create_call_configuration.py",
)
args = parser.parse_args()

# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#


# класс для того, чтобы отличать значения в кавычках
class quoted(str):
    pass


# добавляем кавычки
def quoted_presenter(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="'")


# добавляем знак | многострочным значениям
def str_presenter(dumper, data):
    if data.count("\n") > 0:  # check for multiline string
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


yaml.add_representer(quoted, quoted_presenter)
yaml.add_representer(str, str_presenter)

script_dir = str(Path(__file__).parent.resolve())
call_file_path = Path("%s/../src/call.yaml" % (script_dir))
default_call_file_path = Path("%s/../src/call.default.yaml" % (script_dir))


def deep_get(dictionary: dict, keys: str, default={}):
    keys = keys.split(".")
    my_dict = dictionary.get(keys[0], default)

    if len(keys) > 1:
        for key in keys[1:]:
            my_dict = my_dict.get(key, default)

    return my_dict


def nested_set(dic, keys, value, create_missing=True):
    keys = keys.split(".")
    d = dic
    for key in keys[:-1]:
        if key in d:
            d = d[key]
        elif create_missing:
            d = d.setdefault(key, {})
        else:
            return dic
    if keys[-1] in d or create_missing:
        d[keys[-1]] = value
    return dic


# --- VALUE FUNCTIONS ---#


def get_subnet_number(subnet_mask: str) -> int:
    for part in subnet_mask.split():
        address, network = part.split("/")
        a, b, c, d = address.split(".")
    return c


def get_free_subnet(
        project_name: str, project_values: dict, global_values: dict
) -> int:
    min_subnet_number = global_values["start_octet"] + 1
    max_subnet_number = 254

    subnet_mask = "172.39.%s.0/24"

    if current_values.get("projects") is None:
        return subnet_mask % min_subnet_number

    occupied_subnet_number_list = []

    for project, project_values in current_values["projects"].items():
        if project in nested_project_list:
            for nested_project, nested_project_values in project_values.items():
                if not isinstance(nested_project_values, collections.abc.Mapping):
                    continue
                project_subnet = deep_get(nested_project_values, "network.subnet")

                if project_subnet != {}:
                    break
        else:
            project_subnet = deep_get(project_values, "network.subnet")

        if project_subnet != {}:
            occupied_subnet_number_list.append(int(get_subnet_number(project_subnet)))

    s = set(occupied_subnet_number_list)
    free_subnet_number_list = [
        x for x in [*range(min_subnet_number, max_subnet_number)] if x not in s
    ]

    return subnet_mask % min(free_subnet_number_list)


def copy(project_name: str, project_values: dict, global_values: dict, keys: str):
    keys = keys.split(".", 1)
    if keys[0] == "_project":
        return deep_get(project_values, ".".join(keys[1:]))
    else:
        return deep_get(global_values, ".".join(keys[1:]))


def copy_with_postfix(
        project_name: str,
        project_values: dict,
        global_values: dict,
        keys: str,
        postfix: str,
):
    keys = keys.split(".", 1)

    if keys[0] == "_project":
        return deep_get(project_values, ".".join(keys[1:])) + postfix
    else:
        return deep_get(global_values, ".".join(keys[1:])) + postfix


def copy_with_custom_postfix(
        project_name: str,
        project_values: dict,
        global_values: dict,
        keys: str,
        postfix: str,
):
    keys = keys.split(".", 1)
    if keys[0] == "_project":
        return deep_get(project_values, ".".join(keys[1:])) + "_" + postfix
    else:
        return deep_get(global_values, ".".join(keys[1:])) + postfix


def get_project_name(project_name: str, project_values: dict, global_values: dict):
    return project_name


def get_project_subdomain(project_name: str, project_values: dict, global_values: dict):
    return project_name.replace("_", "-")


# --- END VALUE FUNCTIONS ---#

# --- POST FUNCTIONS ---#


def create_dir(value: str):
    path = Path(value)
    path.mkdir(exist_ok=True, parents=True)


# --- END POST FUNCTIONS ---#

stun_fields = [
    {
        "name": "host",
        "comment": "Домен STUN-сервера",
        "default_value": None,
        "type": "str",
        "ask": True,
    },
    {
        "name": "port",
        "comment": "Порт STUN-сервера",
        "default_value": None,
        "type": "int",
        "ask": True,
    },
    {
        "name": "is_enabled",
        "comment": "Включить STUN сервер?",
        "default_value": 1,
        "type": "int",
        "ask": False,
    },
]

turn_fields = [
    {
        "name": "host",
        "comment": "Домен TURN-сервера",
        "default_value": None,
        "type": "str",
        "ask": True,
    },
    {
        "name": "port",
        "comment": "Порт TURN-сервера для незащищенных подключений",
        "default_value": 80,
        "type": "int",
        "ask": True,
    },
    {
        "name": "tls_port",
        "comment": "Порт TURN-сервера для защищенных подключений",
        "default_value": 443,
        "type": "int",
        "ask": True,
    },
    {
        "name": "is_protocol_tcp",
        "comment": "Поддерживает ли TURN-сервер подключение по TCP?[0/1]",
        "default_value": 1,
        "type": "int",
        "ask": True,
    },
    {
        "name": "is_protocol_udp",
        "comment": "Поддерживает ли TURN-сервер подключение по UDP?[0/1]",
        "default_value": 1,
        "type": "int",
        "ask": True,
    },
    {
        "name": "is_protocol_tls",
        "comment": "Поддерживает ли TURN-сервер защищенное подключение по TCP?[0/1]",
        "default_value": 1,
        "type": "int",
        "ask": True,
    },
    {
        "name": "secret_key",
        "comment": "Секретный ключ для подключения к серверу",
        "default_value": None,
        "type": "str",
        "ask": True,
    },
    {
        "name": "is_enabled",
        "comment": "Включен ли TURN-сервер?",
        "default_value": 1,
        "type": "int",
        "ask": False,
    },
]

found_external_ports = {}


def process_field(
        field: dict, project: str, label: str, project_values: dict, new_values: dict
):
    search_field = field["name"]

    if deep_get(project_values, search_field) != {}:
        return None, None

    if field["ask"]:
        if field.get("value_function") is not None:
            field["default_value"] = field["value_function"](
                label, {}, new_values, *field["args"]
            )

        new_value = InteractiveValue(
            field["name"],
            "[%s] " % project + field["comment"],
            field["type"],
            field["default_value"],
        ).input()
    else:
        new_value = (
            field["default_value"]
            if field["default_value"] is not None
            else field["value_function"](label, {}, new_values, *field["args"])
        )

    return new_value, field["name"]


def start():
    stun_server_list = []
    turn_server_list = []

    turn_server_count = 0
    stun_server_count = 0

    if default_call_file_path.exists():
        return

    if call_file_path.exists():
        confirm = input("Найдена старая конфигурация. Удалить ее?[y/n]")

        if confirm != "y":
            return

    while (
            input(
                (
                        "Добавляем новый TURN-сервер? Без него невозможна работа звонков[y/n]. На данный момент добавлено: %i\n"
                        % turn_server_count
                )
            )
            == "y"
    ):
        turn_server_count = turn_server_count + 1
        turn_server_list.append(init_turn(turn_server_count))

        print(scriptutils.success("TURN сервер добавлен"))

    call_conf = {}
    call_conf["stun_server_list"] = stun_server_list
    call_conf["turn_server_list"] = turn_server_list

    with call_file_path.open("w") as f:
        f.write(yaml.dump(call_conf))


def init_stun(stun_server_count: int):
    stun_server = {}
    stun_server["id"] = stun_server_count

    for common_field in stun_fields:
        new_value, field_name = process_field(
            common_field.copy(), "stun", "stun", {}, {}
        )

        if new_value is None:
            continue

        stun_server = nested_set(stun_server, field_name, new_value)

    return stun_server


def init_turn(turn_server_count: int):
    turn_server = {}
    turn_server["id"] = turn_server_count

    for common_field in turn_fields:
        new_value, field_name = process_field(
            common_field.copy(), "turn", "turn", {}, {}
        )

        if new_value is None:
            continue

        turn_server = nested_set(turn_server, field_name, new_value)

    return turn_server


start()
