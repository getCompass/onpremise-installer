#!/usr/bin/env python3
# pip3 install pyyaml pyopenssl python-dotenv

import sys

sys.dont_write_bytecode = True

import argparse, yaml, re, unicodedata
from pathlib import Path
from utils import scriptutils
import json
import hashlib

# ---АРГУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument('-v', '--values', required=False, default="compass", type=str,
                    help='Название values файла окружения')
parser.add_argument('-e', '--environment', required=False, default="production", type=str,
                    help='Окружение, в котором разворачиваем')

args = parser.parse_args()
# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

scriptutils.assert_root()

values_arg = args.values if args.values else ''
environment = args.environment if args.environment else ''
stack_name_prefix = environment + '-' + values_arg
stack_name = stack_name_prefix + "-monolith"

script_dir = str(Path(__file__).parent.resolve())

values_file_path = Path('%s/../src/values.%s.yaml' % (script_dir, values_arg))

if not values_file_path.exists():
    scriptutils.die('Не найден файл со сгенерированными значениями. Вы развернули приложение?')

with values_file_path.open('r') as values_file:
    current_values = yaml.safe_load(values_file)
    current_values = {} if current_values is None else current_values

    if current_values == {}:
        scriptutils.die('Не найден файл со сгенерированными значениями. Вы развернули приложение?')

    if current_values.get('projects', {}).get('domino', {}) == {}:
        scriptutils.die(scriptutils.error('Не был развернут проект domino через скрипт deploy.py'))

    domino_project = current_values['projects']['domino']

    if len(domino_project) < 1:
        scriptutils.die(scriptutils.error('Не был развернут проект domino через скрипт deploy.py'))

# добавляем к префиксу stack-name также пометку сервиса, если такая имеется
service_label = current_values.get("service_label") if current_values.get("service_label") else ""
if service_label != "":
    stack_name = stack_name + "-" + service_label

CYRILLIC_TO_LATIN = {
    u'а': u'a', u'б': u'b', u'в': u'v', u'г': u'g', u'д': u'd',
    u'е': u'e', u'ё': u'e', u'ж': u'zh', u'з': u'z', u'и': u'i',
    u'й': u'i', u'к': u'k', u'л': u'l', u'м': u'm', u'н': u'n',
    u'о': u'o', u'п': u'p', u'р': u'r', u'с': u's', u'т': u't',
    u'у': u'u', u'ф': u'f', u'х': u'h', u'ц': u'ts', u'ч': u'ch',
    u'ш': u'sh', u'щ': u'sch', u'ъ': u'', u'ы': u'y', u'ь': u'',
    u'э': u'e', u'ю': u'yu', u'я': u'ya'
}

def transliterate(text: str) -> str:
    return ''.join(CYRILLIC_TO_LATIN.get(c, c) for c in text.lower())


def to_snake_case(name: str) -> str:
    name = Path(name).stem
    name = transliterate(name)
    name = unicodedata.normalize('NFKD', name)
    name = re.sub(r'[^a-z0-9]+', '_', name.lower())
    name = re.sub(r'__+', '_', name).strip('_')
    return name


def get_file_source(file_path: Path) -> int:
    ext = file_path.suffix.lower()
    if ext in ['.jpg', '.jpeg', '.png']:
        return 21
    elif ext in ['.mp4', '.mov', '.avi', '.webm']:
        return 24
    else:
        return 26


def sha1_hash(file_path: Path) -> str:
    sha1 = hashlib.sha1()
    with file_path.open('rb') as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            sha1.update(chunk)
    return sha1.hexdigest()


def save_manifest(manifest_path: Path, manifest: list):
    with manifest_path.open('w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=4)


def already_in_manifest(file_name: str, manifest: list) -> bool:
    return any(entry['file_name'] == file_name for entry in manifest)


# ---СКРИПТ---#

def start():
    base_path = Path(current_values["root_mount_path"]) / "custom_files"
    manifest_path = base_path / "manifest.json"
    manifest = []

    for file in base_path.iterdir():
        if file.name == "manifest.json" or not file.is_file():
            continue

        original_name = file.name
        ext = file.suffix
        normalized_name = to_snake_case(original_name) + ext.lower()
        normalized_path = base_path / normalized_name

        # переименовать, если имя изменилось
        if file.name != normalized_name:
            if normalized_path.exists():
                print(f"Файл с именем {normalized_name} уже существует, пропускаю {file.name}")
                continue
            file.rename(normalized_path)
            file = normalized_path

        if already_in_manifest(file.name, manifest):
            continue

        file_hash = sha1_hash(file)
        file_source = get_file_source(file)
        dictionary_key = file.stem

        new_entry = {
            "dictionary_key": dictionary_key,
            "file_name": file.name,
            "file_hash": file_hash,
            "file_source": file_source,
            "data": {}
        }

        manifest.append(new_entry)

    save_manifest(manifest_path, manifest)


start()
