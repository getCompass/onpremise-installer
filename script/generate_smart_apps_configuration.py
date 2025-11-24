#!/usr/bin/env python3

import argparse
from pathlib import Path
import yaml
import re

from utils import scriptutils
from utils import interactive

# --- ВАЛИДАЦИЯ TITLE --- #
# запрещенные знаки: !"#$%&()*+,/:;=?@[\\]_`{|}~<>
DISALLOWED_PUNCT_RE = re.compile(r"""[!"#$%&*,/:;=\?@\[\]\\\]_`\{\}~<>]""")

# эмодзи (основные диапазоны + флаги, символы-джойнеры и вариации)
EMOJI_RE = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"  # флаги
    "\U0001F300-\U0001F5FF"  # прочие символы и пиктограммы
    "\U0001F600-\U0001F64F"  # смайлы
    "\U0001F680-\U0001F6FF"  # транспорт и символы
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\u2600-\u26FF"
    "\u2700-\u27BF"  # символы Dingbats
    "]"
    "|[\u200D\uFE0F]"  # ZWJ и вариации (используются в emoji-секвенциях)
)

# fancy text: математические алфавитные символы и letterlike
FANCY_TEXT_RE = re.compile(
    "["
    "\U0001D400-\U0001D7FF"  # Mathematical Alphanumeric Symbols
    "\u2100-\u214F"  # Letterlike Symbols
    "]"
)

# --- ВАЛИДАЦИЯ URL --- #
# максимум 1000 символов; разрешtнные символы:
# - буквы латиницы A-Z, a-z
# - буквы кириллицы
# - ẞ ß Ä ä Ü ü Ö ö À à È è É é Ì ì Í í Î î Ò ò Ó ó Ù ù Ú ú Â â Ê ê Ô ô œ Û û Ë ë Ï ï Ÿ ÿ Ç ç Ñ ñ
# - цифры 0-9
# - спецсимволы: _ . / - $ + , : ; = ? @ # ' % [ ] ! & ( ) * “ ”
URL_MAX_LEN = 1000
URL_ALLOWED_RE = re.compile(
    r"""^[
        A-Za-z
        \u0400-\u04FF
        ẞßÄäÜüÖöÀàÈèÉéÌìÍíÎîÒòÓóÙùÚúÂâÊêÔôœÛûËëÏïŸÿÇçÑñ
        0-9
        _\./\-\$\+,:;=\?@#'%\[\]!&\(\)\*“”
    ]+$""",
    re.VERBOSE
)

# ---АРГУМЕНТЫ СКРИПТА---#

script_dir = Path(__file__).parent.resolve()

# загружаем конфиги
global_config_path = script_dir.parent / "configs" / "global.yaml"
smart_apps_config_path = script_dir.parent / "configs" / "smart_apps.yaml"

config = {}

if not smart_apps_config_path.exists():
    print(scriptutils.error(
        f"Отсутствует файл конфигурации {smart_apps_config_path.resolve()}. Запустите скрипт create_configs.py и заполните конфигурацию"))
    exit(1)

with smart_apps_config_path.open("r") as config_file:
    smart_apps_config_values = yaml.load(config_file, Loader=yaml.BaseLoader)

if not global_config_path.exists():
    print(scriptutils.error(
        f"Отсутствует файл конфигурации {global_config_path.resolve()}. Запустите скрипт create_configs.py и заполните конфигурацию"))
    exit(1)

with global_config_path.open("r") as config_file:
    global_config_values = yaml.load(config_file, Loader=yaml.BaseLoader)

config.update(smart_apps_config_values)

root_path = script_dir.parent.resolve()

parser = argparse.ArgumentParser(add_help=True)
parser.add_argument(
    "--smart-apps-pivot-config-output-path",
    required=False,
    default=root_path / "src" / "pivot" / "config" / "smartapps.gophp",
    help="Путь до выходного файла smart_apps конфигурации",
)
parser.add_argument(
    "--smart-apps-domino-config-output-path",
    required=False,
    default=root_path / "src" / "domino" / "config" / "smartapps.gophp",
    help="Путь до выходного файла конфигурации ограничений smart_apps",
)
parser.add_argument(
    "--validate-only",
    required=False,
    action='store_true'
)
args = parser.parse_args()

# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

validate_only = args.validate_only

# пути для конфигов
smart_apps_pivot_conf_path = args.smart_apps_pivot_config_output_path
smart_apps_pivot_conf_path = Path(smart_apps_pivot_conf_path)
smart_apps_domino_conf_path = args.smart_apps_domino_config_output_path
smart_apps_domino_conf_path = Path(smart_apps_domino_conf_path)
validation_errors = []
validation_error_config_path = smart_apps_config_path.resolve()


class SmartAppsPivotConfig:
    def __init__(self) -> None:
        self.input()

    def init(
            self,
            smart_apps_catalog_config: list,
    ):
        self.smart_apps_catalog_config = smart_apps_catalog_config

    def input(self):
        try:
            smart_apps_catalog_config = interactive.InteractiveValue(
                "smart_apps.catalog_config",
                "Список smart_apps, отображаемых в каталоге", "list", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message, smart_apps_config_path)
            smart_apps_catalog_config = []

        return self.init(smart_apps_catalog_config)

    # --- проверка наличия аватаров --- #
    def count_missing_avatars(self):
        avatars_dir = Path(global_config_values["root_mount_path"]) / "custom_files"
        allowed_exts = {".png", ".jpg", ".jpeg", ".bmp"}

        missing = 0
        for item in self.smart_apps_catalog_config:
            if not isinstance(item, dict):
                continue
            try:
                item_id = int(item.get("catalog_item_id", -1))
            except (ValueError, TypeError):
                # если id некорректный - этим займется основная валидация
                continue

            # пропускаем дефолтный смарт аппы
            if item_id <= 102:
                continue

            # ищем файл smart_app_avatar_{id}.*
            pattern = f"smart_app_avatar_{item_id}.*"
            exists = False
            if avatars_dir.exists():
                for p in avatars_dir.glob(pattern):
                    # проверяем что это картинка
                    if p.is_file() and p.suffix.lower() in allowed_exts:
                        exists = True
                        break
            if not exists:
                missing += 1

        return missing

    # заполняем содержимым
    def make_smart_apps_catalog_output(self):

        required_keys = [
            "catalog_item_id",
            "is_popular",
            "sort_weight",
            "catalog_category",
            "uniq_name",
            "title",
            "url",
            "is_need_custom_user_agent",
            "is_need_show_in_catalog",
        ]

        # поля, которые должны быть числами
        int_keys = {
            "catalog_item_id",
            "is_popular",
            "sort_weight",
            "is_need_custom_user_agent",
            "is_need_show_in_catalog",
        }

        required_string_keys = {
            "catalog_category",
            "uniq_name",
            "title",
            "url",
        }

        # допустимые значения для catalog_category
        allowed_categories = {
            "popular",
            "office_apps",
            "mail",
            "calendars",
            "team_collaboration",
            "crm_systems",
            "video_conferencing",
            "messengers",
            "development",
            "file_storage",
            "ai_services",
            "accounting_and_edo",
            "hr_services",
            "analytics",
            "other",
        }

        # поля, для которых допустимы только значения 0 или 1
        boolean_keys = {
            "is_popular",
            "is_need_custom_user_agent",
            "is_need_show_in_catalog",
        }

        seen_ids = set()
        seen_uniq_names = set()
        catalog_output = []

        def validate_app(smart_app):
            for key in required_keys:
                if key not in smart_app:
                    handle_exception(
                        "smart_apps.catalog_config",
                        f"Обязательное поле '{key}' отсутствует",
                        smart_apps_config_path
                    )
                    return
            for key in int_keys:
                try:
                    val = int(smart_app[key])
                    if val < 0:
                        handle_exception(
                            "smart_apps.catalog_config",
                            f"[catalog_item_id: {smart_app['catalog_item_id']}] Значение поля '{key}' не может быть отрицательным (текущее: {val})",
                            smart_apps_config_path
                        )

                    # проверка для boolean полей: только 0 или 1
                    if key in boolean_keys and val not in (0, 1):
                        handle_exception(
                            "smart_apps.catalog_config",
                            f"[catalog_item_id: {smart_app['catalog_item_id']}] Значение поля '{key}' должно быть 0 или 1 (текущее: {val})",
                            smart_apps_config_path
                        )
                except (ValueError, TypeError):
                    handle_exception(
                        "smart_apps.catalog_config",
                        f"[catalog_item_id: {smart_app['catalog_item_id']}] Значение поля '{key}' должно быть числом (текущее: {smart_app.get(key)})",
                        smart_apps_config_path
                    )
                    return

            for key in required_string_keys:
                val = smart_app.get(key, "")
                if not isinstance(val, str) or val.strip() == "":
                    handle_exception(
                        "smart_apps.catalog_config",
                        f"[catalog_item_id: {smart_app['catalog_item_id']}] Поле '{key}' обязательно и не может быть пустым",
                        smart_apps_config_path
                    )
                    return

            # --- валидация title ---
            title = smart_app.get("title", "").strip()
            smart_app["title"] = title  # нормализуем пробелы
            if len(title) > 40:
                handle_exception(
                    "smart_apps.catalog_config",
                    f"[catalog_item_id: {smart_app['catalog_item_id']}] Поле 'title' не должно превышать 40 символов (текущее: {len(title)})",
                    smart_apps_config_path
                )
                return

            # запрещенные знаки
            if DISALLOWED_PUNCT_RE.search(title):
                handle_exception(
                    "smart_apps.catalog_config",
                    f"[catalog_item_id: {smart_app['catalog_item_id']}] Поле 'title' содержит недопустимые символы",
                    smart_apps_config_path
                )
                return

            # эмодзи
            if EMOJI_RE.search(title):
                handle_exception(
                    "smart_apps.catalog_config",
                    f"[catalog_item_id: {smart_app['catalog_item_id']}] Поле 'title' не должно содержать эмодзи",
                    smart_apps_config_path
                )
                return

            # fancy text
            if FANCY_TEXT_RE.search(title):
                handle_exception(
                    "smart_apps.catalog_config",
                    f"[catalog_item_id: {smart_app['catalog_item_id']}] Поле 'title' не должно содержать стилизованный (fancy) текст",
                    smart_apps_config_path
                )
                return

            # --- валидация url ---
            url = smart_app.get("url", "").strip()
            smart_app["url"] = url  # нормализуем пробелы
            if len(url) > URL_MAX_LEN:
                handle_exception(
                    "smart_apps.catalog_config",
                    f"[catalog_item_id: {smart_app['catalog_item_id']}] Поле 'url' не должно превышать {URL_MAX_LEN} символов (текущее: {len(url)})",
                    smart_apps_config_path
                )
                return

            if not URL_ALLOWED_RE.fullmatch(url):
                handle_exception(
                    "smart_apps.catalog_config",
                    f"[catalog_item_id: {smart_app['catalog_item_id']}] Поле 'url' содержит недопустимые символы",
                    smart_apps_config_path
                )
                return

            # --- валидация catalog_category ---
            # проверка catalog_category на соответствие одному из разрешенных значений
            category = smart_app.get("catalog_category", "").strip()
            smart_app["catalog_category"] = category  # нормализуем пробелы
            if category not in allowed_categories:
                handle_exception(
                    "smart_apps.catalog_config",
                    f"[catalog_item_id: {smart_app['catalog_item_id']}] Значение поля 'catalog_category' должно быть одним из: {', '.join(sorted(allowed_categories))} (текущее: {category})",
                    smart_apps_config_path
                )
                return

            # --- валидация uniq_name ---
            name = smart_app.get("uniq_name", "").strip()
            smart_app["uniq_name"] = name  # нормализуем пробелы
            if len(name) > 40:
                handle_exception(
                    "smart_apps.catalog_config",
                    f"[catalog_item_id: {smart_app['catalog_item_id']}] Поле 'uniq_name' не должно превышать 40 символов (текущее: {len(name)})",
                    smart_apps_config_path
                )
                return
            if not re.fullmatch(r"[a-z0-9]+", name):
                handle_exception(
                    "smart_apps.catalog_config",
                    f"[catalog_item_id: {smart_app['catalog_item_id']}] Поле 'uniq_name' может содержать только строчные латинские буквы (a-z) и цифры (0-9)",
                    smart_apps_config_path
                )
                return

            # проверка уникальности uniq_name
            name = smart_app["uniq_name"]
            if name in seen_uniq_names:
                handle_exception(
                    "smart_apps.catalog_config",
                    f"uniq_name '{name}' уже используется",
                    smart_apps_config_path
                )
                return
            seen_uniq_names.add(name)

            # --- валидация catalog_item_id ---
            # проверка уникальности catalog_item_id
            item_id = int(smart_app["catalog_item_id"])
            if item_id in seen_ids:
                handle_exception(
                    "smart_apps.catalog_config",
                    f"catalog_item_id '{item_id}' уже используется",
                    smart_apps_config_path
                )
                return
            seen_ids.add(item_id)

        def php_key_value_line(key, value):
            if key in int_keys:
                return f'\t\t"{key}" => {int(value)},'
            return f'\t\t"{key}" => "{str(value)}",'

        for smart_app in self.smart_apps_catalog_config:
            if not isinstance(smart_app, dict):
                continue

            before_errors = len(validation_errors)
            validate_app(smart_app)
            after_errors = len(validation_errors)

            # если после валидации добавились ошибки — не продолжаем
            if after_errors > before_errors:
                continue

            php_lines = ["\t["]
            for key in required_keys:
                if key in smart_app:
                    php_lines.append(php_key_value_line(key, smart_app[key]))
            php_lines.append("\t],")
            catalog_output.append("\n".join(php_lines))

        return "\n".join(catalog_output)


class SmartAppsDominoConfig:
    def __init__(self) -> None:
        self.input()

    def init(
            self,
            is_create_from_catalog_disabled: bool,
            is_create_custom_smart_apps_disabled: bool,
    ):
        self.is_create_from_catalog_disabled = is_create_from_catalog_disabled
        self.is_create_custom_smart_apps_disabled = is_create_custom_smart_apps_disabled

    def input(self):
        try:
            is_create_from_catalog_disabled = interactive.InteractiveValue(
                "smart_apps.is_create_from_catalog_disabled",
                "Запрещено ли добавлять приложения из каталога", "bool", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message, smart_apps_config_path)
            is_create_from_catalog_disabled = False
        try:
            is_create_custom_smart_apps_disabled = interactive.InteractiveValue(
                "smart_apps.is_create_custom_smart_apps_disabled",
                "Запрещено ли создавать кастомные приложения", "bool", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message, smart_apps_config_path)
            is_create_custom_smart_apps_disabled = False

        return self.init(is_create_from_catalog_disabled, is_create_custom_smart_apps_disabled)

    # заполняем содержимым
    def make_smart_apps_catalog_output(self):
        # Форматирование для is_create_from_catalog_disabled
        is_create_from_catalog_disabled = '"is_create_from_catalog_disabled" => %s' % (
            str(self.is_create_from_catalog_disabled).lower())
        # Форматирование для is_create_custom_smart_apps_disabled
        is_create_custom_smart_apps_disabled = '"is_create_custom_smart_apps_disabled" => %s' % (
            str(self.is_create_custom_smart_apps_disabled).lower())

        output = "%s,\n\t%s" % (is_create_from_catalog_disabled, is_create_custom_smart_apps_disabled)
        return output.encode().decode()


# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

# ---ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ---#

def handle_exception(field, message: str, config_path):
    if validate_only:
        validation_errors.append(message)
        validation_error_config_path = str(config_path.resolve())
        return

    print(message)
    exit(1)


# начинаем выполнение
def start():
    generate_config(smart_apps_pivot_conf_path, smart_apps_domino_conf_path)
    exit(0)


# записываем содержимое в файл
def write_file(output: str, conf_path: Path):
    if validate_only:
        if len(validation_errors) > 0:
            print("Ошибка в конфигурации %s" % validation_error_config_path)
            for error in validation_errors:
                print(error)
            exit(1)
        exit(0)

    conf_path.unlink(missing_ok=True)
    f = conf_path.open("w")
    f.write(output)
    f.close()

    print(
        scriptutils.warning(str(conf_path.resolve()))
    )


# генерируем конфиг
def generate_config(smart_apps_pivot_conf_path: Path, smart_apps_domino_conf_path: Path):
    # генерируем данные
    pivot_config = SmartAppsPivotConfig()
    pivot_output = make_pivot_output(pivot_config)
    domino_config = SmartAppsDominoConfig()
    domino_output = make_domino_output(domino_config)

    # если только валидируем данные, то файлы не пишем
    missing_avatar_count = pivot_config.count_missing_avatars()
    if validate_only:
        if missing_avatar_count > 0:
            confirm = input(
                scriptutils.warning(
                    f"Для {missing_avatar_count} {scriptutils.plural(missing_avatar_count, 'приложения', 'приложений', 'приложений')} не загружен аватар, такие приложения будут отображаться с одинаковым аватаром по умолчанию. Вы уверены, что хотите продолжить без установки аватаров?[y/n]"
                )
            ).lower().strip()
            if confirm != "y":
                scriptutils.die("Генерация конфигурации smart_apps отменена")
        if len(validation_errors) > 0:
            print("Ошибка в конфигурации %s" % validation_error_config_path)
            for error in validation_errors:
                print(error)
            exit(1)
        exit(0)

    if len(validation_errors) == 0:
        print(
            scriptutils.success(
                "Файлы с настройками smart_apps сгенерированы по следующему пути: "
            )
        )

    write_file(pivot_output, smart_apps_pivot_conf_path)
    write_file(domino_output, smart_apps_domino_conf_path)


# получаем содержимое конфига для smart_apps
def make_pivot_output(config: SmartAppsPivotConfig):
    return r'''<?php

namespace Compass\Company;

/**
 * каталог приложений
 */
$CONFIG["SMARTAPPS_SUGGESTED_CATALOG"] = [
	{}
];

/**
 * локализация категорий
 */
$CONFIG["SMARTAPPS_CATEGORY_LOCALIZATION"] = [
	"popular"            => [
		"ru" => "Популярные",
		"en" => "Популярные",
		"de" => "Популярные",
		"fr" => "Популярные",
		"es" => "Популярные",
		"it" => "Популярные",
	],
	"office_apps"        => [
		"ru" => "Офисные программы",
		"en" => "Office applications",
		"de" => "Office-Apps",
		"fr" => "Programmes de bureau",
		"es" => "Programas de oficina",
		"it" => "Applicazioni Office",
	],
	"mail"               => [
		"ru" => "Почта",
		"en" => "Mail",
		"de" => "E-Mail",
		"fr" => "Courriel",
		"es" => "Correo",
		"it" => "Posta",
	],
	"calendars"          => [
		"ru" => "Календари",
		"en" => "Calendars",
		"de" => "Kalender",
		"fr" => "Calendriers",
		"es" => "Calendarios",
		"it" => "Calendari",
	],
	"team_collaboration" => [
		"ru" => "Работа в команде",
		"en" => "Team work",
		"de" => "Teamarbeit",
		"fr" => "Travail d'équipe",
		"es" => "Trabajo en equipo",
		"it" => "Teamwork",
	],
	"crm_systems"        => [
		"ru" => "CRM системы",
		"en" => "CRM systems",
		"de" => "CRM-Systeme",
		"fr" => "Systèmes CRM",
		"es" => "Sistemas CRM",
		"it" => "Sistemi CRM",
	],
	"video_conferencing" => [
		"ru" => "Видеоконференции",
		"en" => "Videoconferences",
		"de" => "Videokonferenzen",
		"fr" => "Vidéoconférences",
		"es" => "Videoconferencias",
		"it" => "Videoconferenze",
	],
	"messengers"         => [
		"ru" => "Мессенджеры",
		"en" => "Messengers",
		"de" => "Messenger",
		"fr" => "Messagers",
		"es" => "Mensajería",
		"it" => "Messenger",
	],
	"development"        => [
		"ru" => "Разработка",
		"en" => "Development",
		"de" => "Entwicklung",
		"fr" => "Développement",
		"es" => "Desarrollo",
		"it" => "Sviluppo",
	],
	"file_storage"       => [
		"ru" => "Файловые хранилища",
		"en" => "File storages",
		"de" => "Dateispeicher",
		"fr" => "Stockages de fichiers",
		"es" => "Almacenamiento de archivos",
		"it" => "Archiviazione file",
	],
	"ai_services"        => [
		"ru" => "ИИ сервисы",
		"en" => "AI services",
		"de" => "KI-Dienste",
		"fr" => "Services d'IA",
		"es" => "Servicios de IA",
		"it" => "Servizi IA",
	],
	"accounting_and_edo" => [
		"ru" => "Бухгалтерия и ЭДО",
		"en" => "Accounting & E-Docs",
		"de" => "Buchhaltung und elektronischer Datenaustausch",
		"fr" => "Service comptable et GED",
		"es" => "Contabilidad y gestión electrónica de documentos (GED)",
		"it" => "Contabilità",
	],
	"hr_services"        => [
		"ru" => "HR сервисы",
		"en" => "HR services",
		"de" => "HR-Dienste",
		"fr" => "Services de RH",
		"es" => "Servicios de RR. HH.",
		"it" => "Servizi HR",
	],
	"analytics"          => [
		"ru" => "Аналитика",
		"en" => "Analytics",
		"de" => "Analytik",
		"fr" => "Analytique",
		"es" => "Analítica",
		"it" => "Analisi",
	],
	"other"              => [
		"ru" => "Прочее",
		"en" => "Others",
		"de" => "Sonstiges",
		"fr" => "Autres",
		"es" => "Otras",
		"it" => "Altro",
	],
];

return $CONFIG;'''.format(config.make_smart_apps_catalog_output())


# получаем содержимое конфига для smart_apps
def make_domino_output(config: SmartAppsDominoConfig):
    return r'''<?php

namespace Compass\Company;

/**
 * Ограничения smart_apps
 */
$CONFIG["SMARTAPPS_RESTRICTIONS"] = [
	{}
];

return $CONFIG;
'''.format(config.make_smart_apps_catalog_output())


# ---КОНЕЦ ВСПОМОГАТЕЛЬНЫХ ФУНКЦИЙ---#

# ---СКРИПТ---#
start()
