#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import load_pem_private_key

import ipaddress

from pathlib import Path
import random, shutil, subprocess, ipaddress, argparse, yaml, os, pwd
from utils import scriptutils, interactive
from loader import Loader
from typing import Tuple
from datetime import datetime, timedelta, timezone

scriptutils.assert_root()
script_path = Path(__file__).parent.resolve()
cert_path = Path(str(script_path.resolve()) + "/../certs/")
cert_path.mkdir(exist_ok=True)

# загружаем конфиги
config_path = Path(str(script_path) + "/../configs/global.yaml")

config = {}

if not config_path.exists():
    print(scriptutils.error("Отсутствует файл конфигурации %s." % str(config_path.resolve())) +  "Запустите скрипт create_configs.py и заполните конфигурацию")
    exit(1)

with config_path.open("r") as config_file:
    config_values = yaml.safe_load(config_file)

config.update(config_values)

parser = argparse.ArgumentParser(add_help=False)

parser.add_argument(
    "-e",
    "--environment",
    default="production",
    required=False,
    type=str,
    help="среда, для которой производим развертывание",
)

parser.add_argument(
    "-v",
    "--values",
    default="compass",
    required=False,
    type=str,
    help="название файла со значениями для развертывания",
)

parser.add_argument(
    "--force",
    required=False,
    action='store_true',
    help="форсированная регенерация сертификатов",
)

parser.add_argument(
    "--validate-only",
    required=False,
    action='store_true'
)

args = parser.parse_args()

host = None

values_name = args.values
environment = args.environment
validate_only = args.validate_only
force = args.force

script_dir = str(Path(__file__).parent.resolve())
values_file_path = Path("%s/../src/values.%s.yaml" % (script_dir, values_name))
current_values = {}

if values_file_path.exists():
    with values_file_path.open("r") as values_file:
        current_values = yaml.safe_load(values_file)
        current_values = {} if current_values is None else current_values

if current_values.get("host_ip") is not None:
    host = current_values["host_ip"]

def start():

    if config.get("host_ip") is None:
        print(scriptutils.error("Отсутствует значение у поля host_ip в конфигурации %s. Запустите скрипт create_configs.py и заполните конфигурацию" % str(config_path.resolve())))
        exit(1)

    if validate_only:
        exit(0)

    root_mount_path = current_values["root_mount_path"]

    ssl_path = Path(f"{root_mount_path}/mysql_ssl")
    ssl_path.mkdir(exist_ok=True)
    try:
        get_root_certificate_path(ssl_path)

        if force:
            create_root_certificate(ssl_path)
    except FileNotFoundError:
        create_root_certificate(ssl_path)

    if scriptutils.is_replication_master_server(current_values):
        generate_mysql_ssl("mysql-master", ssl_path)
        generate_mysql_ssl("mysql-replica", ssl_path)

def get_root_certificate_path(ssl_path: Path) -> Tuple[Path, Path]:
    CN = "mysqlRootCA"

    pubkey = "%s.crt" % CN
    privkey = "%s.key" % CN

    pubkey_path = Path(f"{ssl_path}/{pubkey}")
    privkey_path = Path(f"{ssl_path}/{privkey}")

    if pubkey_path.exists():
        return pubkey_path, privkey_path

    print("Не найдены файлы корневого сертификата")
    raise FileNotFoundError


def create_root_certificate(output_dir: Path) -> Tuple[Path, Path]:
    CN = "mysqlRootCA"

    pubkey = "%s.crt" % CN
    privkey = "%s.key" % CN
    srl = "%s.srl" % CN

    pubkey_path = Path(f"{output_dir}/{pubkey}")
    privkey_path = Path(f"{output_dir}/{privkey}")
    srl_path = Path(f"{output_dir}/{srl}")

    if pubkey_path.exists() and privkey_path.exists() and not force:
        return pubkey_path, privkey_path

    loader = Loader(
        "Генерируем корневой сертификат и ключ для mysql",
        "Успешно сгенерировали сертификат для mysql",
        "Не смогли сгенерировать сертификат для mysql",
    ).start()
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
    serialnumber = random.getrandbits(64)

    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, CN)])
    basic_contraints = x509.BasicConstraints(ca=True, path_length=None)
    now = datetime.now(timezone.utc)

    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(k.public_key())
        .serial_number(serialnumber)
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=10 * 365))
        .add_extension(basic_contraints, True)
        .sign(k, hashes.SHA256(), default_backend())
    )

    cert_pem = cert.public_bytes(encoding=serialization.Encoding.PEM)
    key_pem = k.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    pubkey_path.open("wt").write(cert_pem.decode("utf-8"))
    privkey_path.open("wt").write(key_pem.decode("utf-8"))
    srl_path.open("wt").write("00")

    loader.success()
    print("Сгенерирован корневой сертификат для mysql")
    try:
        shutil.copy2(pubkey_path, "/usr/local/share/ca-certificates/%s" % pubkey)
        subprocess.run(["update-ca-certificates"])

    except:
        print(scriptutils.error("Не удалось добавить сертификат в доверенные. Убедитесь, что развертываете приложение на Ubuntu"))

    print(
        "Корневой сертификат для mysql сохранен по следующему пути: "
        + scriptutils.warning(str(pubkey_path.resolve()))
    )
    print(
        "Корневой ключ для mysql сохранен по следующему пути: "
        + scriptutils.warning(str(privkey_path.resolve()))
    )
    return pubkey_path, privkey_path


def generate_mysql_ssl(common_name: str, output_dir: Path, validity_days: int = 365):

    new_cert_path = f"{output_dir}/{common_name}-cert.pem"
    new_key_path = f"{output_dir}/{common_name}-key.pem"

    if not should_generate_cert(new_cert_path, new_key_path):
        return

    print("Генерируем новые сертификаты для mysql...")

    CN = "mysqlRootCA"

    ca_pubkey = f"{output_dir}/%s.crt" % CN
    ca_privkey = f"{output_dir}/%s.key" % CN

    # Загрузка CA
    with open(ca_privkey, "rb") as f:
        ca_priv_key = serialization.load_pem_private_key(f.read(), password=None)

    with open(ca_pubkey, "rb") as f:
        ca_cert = x509.load_pem_x509_certificate(f.read())

    # Генерация ключа сервера
    server_priv_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Информация о сервере
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MySQL"),
        x509.NameAttribute(NameOID.COMMON_NAME, "Mysql Replica"),
    ])

    # Создание сертификата сервера
    basic_contraints = x509.BasicConstraints(ca=True, path_length=None)
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(server_priv_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
        .add_extension(basic_contraints, True)
        .sign(ca_priv_key, hashes.SHA256())
    )

    # Сохранение сертификата сервера
    with open(new_key_path, "wb") as f:
        f.write(server_priv_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))

    with open(new_cert_path, "wb") as f:
        f.write(server_cert.public_bytes(serialization.Encoding.PEM))

    print(f"Создан сертификат для {common_name}")

def should_generate_cert(cert_path: str, key_path: str, min_valid_days: int = 30) -> bool:
    # проверяем существование сертов
    if not Path(cert_path).exists() or not Path(key_path).exists():
        print(scriptutils.warning("Отсутствуют сертификаты для mysql. Генерируем новые..."))
        return True

    try:
        with open(cert_path, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())

        # получаем дату окончания сертификата
        not_valid_after = cert.not_valid_after

        # вычисляем оставшееся время
        time_left = not_valid_after.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)

        # проверяем срок действия
        if time_left < timedelta(days=min_valid_days):
            print(scriptutils.warning("Срок действия сертификатов для mysql истекает. Генерируем новые..."))
            return True

        return False
    except Exception as e:
        print(scriptutils.warning(f"Ошибка при проверке наличия сертификатов для mysql. {e}. Генерируем новые..."))
        return True

start()
