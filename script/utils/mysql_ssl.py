# Общие функции для генерации и проверки ssl сертификатов mysql
# Используются скриптом generate_mysql_ssl_certificates.py и реконсайлером репликации

import os

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Tuple, cast

CA_COMMON_NAME = "mysqlRootCA"
CERT_VALIDITY_DAYS = 365
DEFAULT_MIN_VALID_DAYS = 30
MANTICORE_SSL_DIR = "/etc/manticore/ssl"


# префикс сертификата текущего хоста (master или replica)
def get_host_cert_prefix(values_dict: dict) -> str:
    if values_dict.get("mysql_server_id") == 1:
        return "master"

    return "replica"


# пути к сертификату и ключу хоста
def get_host_cert_paths(ssl_dir, prefix: str) -> Tuple[Path, Path]:
    cert_path = Path(f"{ssl_dir}/mysql-{prefix}-cert.pem")
    key_path = Path(f"{ssl_dir}/mysql-{prefix}-key.pem")

    return cert_path, key_path


# строка опций galera для tls репликации manticore (сертификаты текущего хоста монтируются в manticore)
def galera_ssl_options(cert_prefix: str) -> str:
    cert_path, key_path = get_host_cert_paths(MANTICORE_SSL_DIR, cert_prefix)

    return "socket.ssl_cert=%s;socket.ssl_key=%s;socket.ssl_ca=%s/%s.crt" % (
        cert_path, key_path, MANTICORE_SSL_DIR, CA_COMMON_NAME)


# проверяем, что сертификат отсутствует, поврежден или истекает раньше порога
def is_certificate_expiring(cert_path, key_path, min_valid_days: int = DEFAULT_MIN_VALID_DAYS) -> bool:
    cert_path = Path(cert_path)
    key_path = Path(key_path)

    if not cert_path.exists() or not key_path.exists():
        print("Отсутствуют сертификаты для mysql. Генерируем новые...")
        return True

    try:
        with open(cert_path, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())

        not_valid_after = cert.not_valid_after_utc
        time_left = not_valid_after.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)

        if time_left < timedelta(days=min_valid_days):
            print("Срок действия сертификатов для mysql истекает. Генерируем новые...")
            return True

        return False
    except Exception as e:
        print(f"Ошибка при проверке наличия сертификатов для mysql. {e}. Генерируем новые...")
        return True


# генерируем и записываем сертификат с ключом, подписанный существующим корневым сертификатом
def generate_mysql_ssl(common_name: str, output_dir) -> Tuple[Path, Path]:
    new_cert_path = Path(f"{output_dir}/{common_name}-cert.pem")
    new_key_path = Path(f"{output_dir}/{common_name}-key.pem")

    ca_pubkey_path = Path(f"{output_dir}/{CA_COMMON_NAME}.crt")
    ca_privkey_path = Path(f"{output_dir}/{CA_COMMON_NAME}.key")

    if not ca_pubkey_path.exists() or not ca_privkey_path.exists():
        raise FileNotFoundError(
            "Не найдены файлы корневого сертификата %s" % str(ca_pubkey_path.parent.resolve()))

    print("Генерируем новые сертификаты для mysql...")

    with open(ca_privkey_path, "rb") as f:
        ca_priv_key = cast(rsa.RSAPrivateKey, load_pem_private_key(f.read(), password=None))

    with open(ca_pubkey_path, "rb") as f:
        ca_cert = x509.load_pem_x509_certificate(f.read())

    server_priv_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MySQL"),
        x509.NameAttribute(NameOID.COMMON_NAME, "Mysql Replica"),
    ])

    basic_contraints = x509.BasicConstraints(ca=True, path_length=None)
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(server_priv_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=CERT_VALIDITY_DAYS))
        .add_extension(basic_contraints, True)
        .sign(ca_priv_key, hashes.SHA256())
    )

    key_pem = server_priv_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    cert_pem = server_cert.public_bytes(serialization.Encoding.PEM)

    # атомарно заменяем файлы: сначала во временные, затем переименовываем
    tmp_key_path = Path(f"{new_key_path}.tmp")
    tmp_cert_path = Path(f"{new_cert_path}.tmp")

    with open(tmp_key_path, "wb") as f:
        f.write(key_pem)

    with open(tmp_cert_path, "wb") as f:
        f.write(cert_pem)

    os.replace(tmp_key_path, new_key_path)
    os.replace(tmp_cert_path, new_cert_path)

    print(f"Создан сертификат для {common_name}")

    return new_cert_path, new_key_path
