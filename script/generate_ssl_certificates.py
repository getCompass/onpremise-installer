#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

from OpenSSL import crypto
from pathlib import Path
import random, shutil, subprocess, ipaddress, argparse, yaml
from utils import scriptutils, interactive
from loader import Loader
from typing import Tuple

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
    k = crypto.PKey()
    k.generate_key(crypto.TYPE_RSA, 2048)
    serialnumber = random.getrandbits(64)


    cert = crypto.X509()
    cert.set_version(0x2)
    cert.get_subject().C = "CA"
    cert.get_subject().ST = "Compass"
    cert.get_subject().L = "Compass"
    cert.get_subject().O = "Compass"
    cert.get_subject().OU = "Compass"
    cert.get_subject().CN = CN
    cert.set_serial_number(serialnumber)
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(10 * 365 * 24 * 60 * 60)
    cert.set_issuer(cert.get_subject())
    cert.set_pubkey(k)

    extensions = []
    extensions.append(crypto.X509Extension(b"basicConstraints", True, b"CA:TRUE"))
    cert.add_extensions(extensions)
    
    cert.sign(k, "sha256")

    pub = crypto.dump_certificate(crypto.FILETYPE_PEM, cert)
    priv = crypto.dump_privatekey(crypto.FILETYPE_PEM, k)

    pubkey_path.open("wt").write(pub.decode("utf-8"))
    privkey_path.open("wt").write(priv.decode("utf-8"))
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

    ca_cert = crypto.load_certificate(crypto.FILETYPE_PEM, ca_pubkey_path.open().read())
    ca_key = crypto.load_privatekey(crypto.FILETYPE_PEM, ca_privkey_path.open().read())

    loader = Loader(
        "Генерируем сертификат и ключ для хоста %s" % host,
        "Сгенерировали сертификат и ключ для хоста %s" % host,
    ).start()
    k = crypto.PKey()
    k.generate_key(crypto.TYPE_RSA, 2048)
    serialnumber = random.getrandbits(64)

    cert_req = crypto.X509Req()

    cert_req.get_subject().C = ca_cert.get_subject().C
    cert_req.get_subject().ST = ca_cert.get_subject().ST
    cert_req.get_subject().L = ca_cert.get_subject().L
    cert_req.get_subject().O = ca_cert.get_subject().O

    if ca_cert.get_subject().organizationalUnitName != "":
        cert_req.get_subject().OU = ca_cert.get_subject().OU

    cert_req.get_subject().CN = host

    extensions = []
    extensions.append(crypto.X509Extension(b"basicConstraints", True, b"CA:FALSE"))
    extensions.append(
        crypto.X509Extension(
            b"keyUsage", True, b"nonRepudiation, digitalSignature, keyEncipherment"
        )
    )
    extensions.append(
        crypto.X509Extension(b"subjectAltName", True, ("IP:%s" % host).encode("utf-8"))
    )

    cert_req.add_extensions(extensions)
    cert_req.set_pubkey(k)
    cert_req.sign(ca_key, "sha256")

    cert = crypto.X509()
    cert.set_version(0x2)
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(10 * 365 * 24 * 60 * 60)
    cert.set_issuer(ca_cert.get_subject())
    cert.set_subject(cert_req.get_subject())
    cert.set_pubkey(cert_req.get_pubkey())
    cert.set_serial_number(serialnumber)
    cert.add_extensions(extensions)
    cert.sign(ca_key, "sha256")

    ca_pub = crypto.dump_certificate(crypto.FILETYPE_PEM, ca_cert)

    pub = crypto.dump_certificate(crypto.FILETYPE_PEM, cert)
    priv = crypto.dump_privatekey(crypto.FILETYPE_PEM, k)

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
