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
import random, shutil, subprocess, ipaddress, argparse, yaml
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
    try:
        ca_pubkey_path, ca_privkey_path = get_root_certificate_path()

        if force:
            ca_pubkey_path, ca_privkey_path = create_root_certificate()
    except FileNotFoundError:
        ca_pubkey_path, ca_privkey_path = create_root_certificate()

    create_host_certificate(config.get("host_ip"), ca_pubkey_path, ca_privkey_path)

def get_root_certificate_path() -> Tuple[Path, Path]:
    CN = "compassRootCA"

    pubkey = "%s.crt" % CN
    privkey = "%s.key" % CN

    pubkey_path = Path(str(cert_path.resolve()) + "/" + pubkey)
    privkey_path = Path(str(cert_path.resolve()) + "/" + privkey)

    if pubkey_path.exists() and privkey_path.exists():
        return pubkey_path, privkey_path

    print("Не найдены файлы корневого сертификата")
    raise FileNotFoundError


def create_root_certificate() -> Tuple[Path, Path]:
    CN = "compassRootCA"

    pubkey = "%s.crt" % CN
    privkey = "%s.key" % CN
    srl = "%s.srl" % CN

    pubkey_path = Path(str(cert_path.resolve()) + "/" + pubkey)
    privkey_path = Path(str(cert_path.resolve()) + "/" + privkey)
    srl_path = Path(str(cert_path.resolve()) + "/" + srl)

    if pubkey_path.exists() and privkey_path.exists() and not force:
        return pubkey_path, privkey_path

    loader = Loader(
        "Генерируем корневой сертификат и ключ для приложения",
        "Успешно сгенерировали сертификат",
        "Не смогли сгенерировать сертификат",
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
    print(
        "Сгенерирован корневой сертификат для проекта. Он должен быть добавлен в доверенные сертификаты серверов, где развернуто приложение"
    )
    try:
        shutil.copy2(pubkey_path, "/usr/local/share/ca-certificates/%s" % pubkey)
        subprocess.run(["update-ca-certificates"])

    except:
        print(scriptutils.error("Не удалось добавить сертификат в доверенные. Убедитесь, что развертываете приложение на Ubuntu"))

    print(
        "Корневой сертификат сохранен по следующему пути: "
        + scriptutils.warning(str(pubkey_path.resolve()))
    )
    print(
        "Корневой ключ сохранен по следующему пути: "
        + scriptutils.warning(str(privkey_path.resolve()))
    )
    return pubkey_path, privkey_path


def generate_host_certificates(host: str, ca_pubkey_path: Path, ca_privkey_path: Path):

    while True:

        value = interactive.InteractiveValue("host",
            "Введите ip хоста, для которого генерируем сертификат: ", "str", host, "ip",
        ).input()
        value = value.strip()

        create_host_certificate(value, ca_pubkey_path, ca_privkey_path)

        confirm = input("Создаем еще для одного хоста?[y/N]")
        if confirm != "y":
            return


def create_host_certificate(host: str, ca_pubkey_path: Path, ca_privkey_path: Path):
    pubkey = "%s.crt" % host
    privkey = "%s.key" % host

    pubkey_path = Path(str(cert_path.resolve()) + "/" + pubkey)
    privkey_path = Path(str(cert_path.resolve()) + "/" + privkey)

    if pubkey_path.exists() and privkey_path.exists() and not force:
        return pubkey_path, privkey_path

    ca_cert = x509.load_pem_x509_certificate(ca_pubkey_path.open(mode="rb").read(),backend=default_backend())
    ca_key = load_pem_private_key(ca_privkey_path.open(mode="rb").read(), password=None,backend=default_backend())

    loader = Loader(
        "Генерируем сертификат и ключ для хоста %s" % host,
        "Сгенерировали сертификат и ключ для хоста %s" % host,
    ).start()
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
    serialnumber = random.getrandbits(64)

    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])
    basic_contraints = x509.BasicConstraints(ca=False, path_length=None)


    key_usage = x509.KeyUsage(
        key_encipherment=True,
        digital_signature=True,
        content_commitment=True,
        data_encipherment=False,
        key_agreement=False,
        encipher_only=False,
        decipher_only=False,
        key_cert_sign=False,
        crl_sign=False
        )

    now = datetime.now(timezone.utc)
    alt_names_list = [x509.IPAddress(ipaddress.ip_address(host))]
    alt_names = x509.SubjectAlternativeName(alt_names_list)

    cert_req_builer = (x509.CertificateSigningRequestBuilder(subject_name=name)
                       .add_extension(basic_contraints, True)
                       .add_extension(key_usage, True)
                       .add_extension(alt_names, True))

    cert_req = cert_req_builer.sign(ca_key, hashes.SHA256())

    cert = (
        x509.CertificateBuilder()
        .subject_name(cert_req.subject)
        .issuer_name(ca_cert.issuer)
        .public_key(k.public_key())
        .serial_number(serialnumber)
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=10 * 365))
        .add_extension(basic_contraints, True)
        .add_extension(key_usage, True)
        .add_extension(alt_names, True)
        .sign(ca_key, hashes.SHA256(), default_backend())
    )

    ca_pub = ca_cert.public_bytes(encoding=serialization.Encoding.PEM)
    pub = cert.public_bytes(encoding=serialization.Encoding.PEM)
    priv = k.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    pubkey_path.open("wt").write(pub.decode("utf-8") + ca_pub.decode("utf-8"))
    privkey_path.open("wt").write(priv.decode("utf-8"))
    loader.success()

    print(
        "Сертификат сохранен по следующему пути: "
        + scriptutils.warning(str(pubkey_path.resolve()))
    )
    print(
        "Ключ сохранен по следующему пути: "
        + scriptutils.warning(str(privkey_path.resolve()))
    )


start()
