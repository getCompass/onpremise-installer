import sys
import ipaddress
import json
import os
import pathlib
import re
import socket
import subprocess
import uuid
import time
from typing import List, Literal, Union

import psutil
from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends, Form, Response
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, conint, model_validator
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedSeq
from ruamel.yaml.scalarstring import DoubleQuotedScalarString
import importlib.util

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent.parent
DIST_DIR = BASE_DIR / "web_installer/frontend/"
CONFIG_DIR = BASE_DIR / "configs"
SCRIPTUTILS_PATH = BASE_DIR / "script" / "utils" / "scriptutils.py"
PYTHON_BIN = sys.executable

spec = importlib.util.spec_from_file_location("scriptutils", str(SCRIPTUTILS_PATH))
scriptutils = importlib.util.module_from_spec(spec)
sys.modules["scriptutils"] = scriptutils
spec.loader.exec_module(scriptutils)

yaml = YAML()
app = FastAPI()

STEPS_FILE = BASE_DIR / ".install_completed_steps.json"


def ensure_steps_file():
    if not STEPS_FILE.exists():
        try:
            STEPS_FILE.write_text("[]", encoding="utf-8")
        except Exception:
            # трекинг не ломает установку
            pass


def append_step(step: str):
    try:
        ensure_steps_file()
        raw = STEPS_FILE.read_text(encoding="utf-8")
        data = json.loads(raw.strip() or "[]")
        if not isinstance(data, list):
            data = []
        if step not in data:
            data.append(step)
            STEPS_FILE.write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )
    except Exception:
        # трекинг не ломает установку
        pass


def load_completed_steps() -> list[str]:
    try:
        if STEPS_FILE.exists():
            with open(STEPS_FILE, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return [str(x) for x in data]
    except Exception:
        pass
    return []


# ----------------------------
# Pydantic-модель с валидацией
# ----------------------------
class ConfigParams(BaseModel):
    domain: str = Field(..., min_length=1, max_length=253)
    cert: str
    private_key: str

    auth_methods: List[Literal["phone_number", "mail", "sso"]] = Field(..., min_items=1)
    sms_providers: List[Literal["sms_agent", "vonage", "twilio"]] = Field(default=[])

    sms_agent_app_name: str = ""
    sms_agent_login: str = ""
    sms_agent_password: str = ""

    vonage_app_name: str = ""
    vonage_api_key: str = ""
    vonage_api_secret: str = ""

    twilio_app_name: str = ""
    twilio_account_sid: str = ""
    twilio_account_auth_token: str = ""

    mail_2fa_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 0
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_encryption: Literal["", "ssl", "tls"] = ""
    smtp_from: str = ""

    root_user_full_name: str = Field(..., min_length=1)
    root_user_phone: str = ""
    root_user_mail: str = ""
    root_user_pass: str = ""
    root_user_sso_login: str = ""

    space_name: str = Field(..., min_length=1)

    sso_protocol: Literal["", "oidc", "ldap"] = ""
    sso_compass_mapping_name: str = ""
    sso_compass_mapping_avatar: str = ""
    sso_compass_mapping_badge: str = ""
    sso_compass_mapping_role: str = ""
    sso_compass_mapping_bio: str = ""

    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_oidc_provider_metadata_link: str = ""
    oidc_attribution_mapping_mail: str = ""
    oidc_attribution_mapping_phone_number: str = ""

    ldap_server_host: str = ""
    ldap_server_port: int = 0
    ldap_use_ssl: bool = True
    ldap_require_cert_strategy: Literal["never", "allow", "try", "demand"] = "demand"
    ldap_user_search_base: str = ""
    ldap_user_unique_attribute: str = ""
    ldap_user_search_filter: str = ""
    ldap_user_search_account_dn: str = ""
    ldap_user_search_account_password: str = ""
    ldap_account_disabling_monitoring_enabled: bool = False

    @model_validator(mode="after")
    def _validate_all(cls, m: "ConfigParams") -> "ConfigParams":
        # — domain
        if not re.fullmatch(r"^[A-Za-z0-9\.-]+$", m.domain):
            raise ValueError(
                "Домен может содержать только буквы, цифры, точки и дефисы"
            )

        # — mail → SMTP обязательны
        if "mail" in m.auth_methods and m.mail_2fa_enabled:
            if not m.smtp_host:
                raise ValueError("Для mail-авторизации нужно заполнить smtp_host")
            if m.smtp_port <= 0 or m.smtp_port > 65535:
                raise ValueError("smtp_port должен быть в диапазоне 1–65535")
            if not m.smtp_from:
                raise ValueError("Для mail-авторизации нужно заполнить smtp_from")
            if not m.root_user_mail:
                raise ValueError("Для mail-авторизации нужно заполнить root_user_mail")
            if not m.root_user_pass:
                raise ValueError("Для mail-авторизации нужно заполнить root_user_pass")

        # — phone_number → хотя бы один SMS-провайдер
        if "phone_number" in m.auth_methods:
            if not m.sms_providers:
                raise ValueError(
                    "Для phone_number-авторизации нужно выбрать sms_providers"
                )

            if not m.root_user_phone:
                raise ValueError(
                    "Для phone_number-авторизации нужно заполнить root_user_phone"
                )

            if "sms_agent" in m.sms_providers:
                for f in (
                    "sms_agent_app_name",
                    "sms_agent_login",
                    "sms_agent_password",
                ):
                    if not getattr(m, f).strip():
                        raise ValueError(f"Для SMS Agent нужно заполнить {f}")

            if "vonage" in m.sms_providers:
                for f in ("vonage_app_name", "vonage_api_key", "vonage_api_secret"):
                    if not getattr(m, f).strip():
                        raise ValueError(f"Для Vonage нужно заполнить {f}")

            if "twilio" in m.sms_providers:
                for f in (
                    "twilio_app_name",
                    "twilio_account_sid",
                    "twilio_account_auth_token",
                ):
                    if not getattr(m, f).strip():
                        raise ValueError(f"Для Twilio нужно заполнить {f}")

        # — sso → общий mapping обязателен
        if "sso" in m.auth_methods:
            if not m.sso_compass_mapping_name.strip():
                raise ValueError("Для SSO нужно заполнить sso_compass_mapping_name")
            if not m.root_user_sso_login.strip():
                raise ValueError(
                    "Для SSO-авторизации нужно заполнить root_user_sso_login"
                )

        # — oidc
        if m.sso_protocol == "oidc":
            for f in (
                "oidc_client_id",
                "oidc_client_secret",
                "oidc_oidc_provider_metadata_link",
            ):
                if not getattr(m, f).strip():
                    raise ValueError(f"Для OIDC нужно заполнить {f}")

        # — ldap
        if m.sso_protocol == "ldap":
            for f in (
                "ldap_server_host",
                "ldap_server_port",
                "ldap_user_search_base",
                "ldap_user_unique_attribute",
                "ldap_user_search_account_dn",
                "ldap_user_search_account_password",
            ):
                val = getattr(m, f)
                if not val:
                    raise ValueError(f"Для LDAP нужно заполнить {f}")

        return m

    @classmethod
    def as_form(
        cls,
        domain: str = Form(...),
        cert: str = Form(""),
        private_key: str = Form(""),
        auth_methods: List[str] = Form(...),
        sms_providers: List[str] = Form([]),
        sms_agent_app_name: str = Form(""),
        sms_agent_login: str = Form(""),
        sms_agent_password: str = Form(""),
        vonage_app_name: str = Form(""),
        vonage_api_key: str = Form(""),
        vonage_api_secret: str = Form(""),
        twilio_app_name: str = Form(""),
        twilio_account_sid: str = Form(""),
        twilio_account_auth_token: str = Form(""),
        mail_2fa_enabled: bool = Form(False),
        smtp_host: str = Form(""),
        smtp_port: int = Form(0),
        smtp_user: str = Form(""),
        smtp_pass: str = Form(""),
        smtp_encryption: str = Form(""),
        smtp_from: str = Form(""),
        root_user_full_name: str = Form(...),
        root_user_phone: str = Form(""),
        root_user_mail: str = Form(""),
        root_user_pass: str = Form(""),
        root_user_sso_login: str = Form(""),
        space_name: str = Form(...),
        sso_protocol: str = Form(""),
        sso_compass_mapping_name: str = Form(""),
        sso_compass_mapping_avatar: str = Form(""),
        sso_compass_mapping_badge: str = Form(""),
        sso_compass_mapping_role: str = Form(""),
        sso_compass_mapping_bio: str = Form(""),
        oidc_client_id: str = Form(""),
        oidc_client_secret: str = Form(""),
        oidc_oidc_provider_metadata_link: str = Form(""),
        oidc_attribution_mapping_mail: str = Form(""),
        oidc_attribution_mapping_phone_number: str = Form(""),
        ldap_server_host: str = Form(""),
        ldap_server_port: int = Form(0),
        ldap_use_ssl: bool = Form(True),
        ldap_require_cert_strategy: str = Form("demand"),
        ldap_user_search_base: str = Form(""),
        ldap_user_unique_attribute: str = Form(""),
        ldap_user_search_filter: str = Form(""),
        ldap_user_search_account_dn: str = Form(""),
        ldap_user_search_account_password: str = Form(""),
        ldap_account_disabling_monitoring_enabled: bool = Form(False),
    ) -> "ConfigParams":
        return cls(**locals())


from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


# API-модели
class CredentialsOut(BaseModel):
    phone_number: Union[str,None] = None
    mail_login: Union[str,None] = None
    mail_password: Union[str,None] = None
    sso_login: Union[str, None] = None


class ResultDataOut(BaseModel):
    url: Union[str, None] = None
    auth_methods: Union[list[str], None] = None
    credentials: Union[CredentialsOut, None] = None


class ResultResponse(BaseModel):
    success: bool
    status: Literal["installed", "not_found"]
    data: ResultDataOut


tasks = {}  # job_id -> {status, log}


@app.get("/api/server/info")
def api_server_info():
    try:
        cpu_cores = os.cpu_count() or 0
        ram_total_mb = psutil.virtual_memory().total // (1024 * 1024)
        disk_total_mb = psutil.disk_usage("/").total // (1024 * 1024)

        return JSONResponse(
            {
                "success": True,
                "cpu_cores": cpu_cores,
                "ram_mb": ram_total_mb,
                "disk_mb": disk_total_mb,
                "is_yandex_cloud_product": scriptutils.is_yandex_cloud_marketplace_product(),
            }
        )
    except Exception:
        return JSONResponse(
            {
                "success": False,
                "cpu_cores": 0,
                "ram_mb": 0,
                "disk_mb": 0,
                "is_yandex_cloud_product": False,
            }
        )


def _parse_ipv4_lines(raw: str) -> list[str]:
    ips: list[str] = []
    for line in (raw or "").splitlines():
        s = line.strip()
        try:
            ip = ipaddress.ip_address(s)
            if isinstance(ip, ipaddress.IPv4Address):
                if s not in ips:
                    ips.append(s)
        except Exception:
            # строки типа "123 IN A 1.2.3.4"/пустые и т.д
            parts = s.split()
            for p in parts:
                try:
                    ip = ipaddress.ip_address(p)
                    if isinstance(ip, ipaddress.IPv4Address):
                        if str(ip) not in ips:
                            ips.append(str(ip))
                except Exception:
                    continue
    return ips


def _dig_a(
    domain: str, nameserver: Union[str, None] = None, timeout_sec: int = 5
) -> list[str]:
    """
    Пытаемся получить A-записи через `dig`. Если недоступен — падаем в fallback на socket.getaddrinfo (только для системного резолвера)
    """
    cmd = ["dig", "+short", "A", domain]
    if nameserver:
        cmd.append(f"@{nameserver}")
    try:
        proc = subprocess.run(
            cmd, text=True, capture_output=True, timeout=timeout_sec, check=False
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        ips = _parse_ipv4_lines(out)
        return ips
    except FileNotFoundError:
        # dig не установлен: для системного резолвера попробуем socket (fallback)
        if nameserver is None:
            try:
                infos = socket.getaddrinfo(
                    domain, None, family=socket.AF_INET, type=socket.SOCK_STREAM
                )
                ips = []
                for _, _, _, _, sockaddr in infos:
                    ip = sockaddr[0]
                    if ip not in ips:
                        ips.append(ip)
                return ips
            except Exception:
                return []
        # для кастомного NS без dig fallback не делаем
        return []
    except Exception:
        return []


class DomainIn(BaseModel):
    domain: str


class DomainResolveOut(BaseModel):
    success: bool
    domain: str
    system_dns: list[str]
    google_dns: list[str]
    match: bool


@app.post("/api/domain/resolve", response_model=DomainResolveOut)
def api_domain_resolve(payload: DomainIn):
    domain = (payload.domain or "").strip()

    # системный резолвер сервера
    sys_ips = _dig_a(domain, nameserver=None)

    # google public DNS
    g_ips = _dig_a(domain, nameserver="8.8.8.8")

    return JSONResponse(
        {
            "success": True,
            "domain": domain,
            "system_dns": sys_ips,
            "google_dns": g_ips,
        }
    )


@app.post("/api/install/configure")
def api_configure(
    params: ConfigParams = Depends(ConfigParams.as_form),
):
    # 1) Создаем пустые шаблоны
    subprocess.run([PYTHON_BIN, BASE_DIR / "script/create_configs.py"], check=True)

    # 2.1) global.yaml
    global_path = os.path.join(CONFIG_DIR, "global.yaml")
    data = load_yaml(global_path)
    data["domain"] = DoubleQuotedScalarString(params.domain)
    data["host_ip"] = DoubleQuotedScalarString(get_host_ip())

    ssl_dir = "/etc/nginx/ssl"
    os.makedirs(ssl_dir, exist_ok=True)

    if params.cert.strip() and params.private_key.strip():
        # пути для итоговых сертификатов
        final_crt = os.path.join(ssl_dir, "compass_fullchain.crt")
        final_key = os.path.join(ssl_dir, "compass_private.key")
        # используем предоставленные пользователем данные
        crt = os.path.join(ssl_dir, final_crt)
        key = os.path.join(ssl_dir, final_key)
        open(crt, "w").write(params.cert)
        open(key, "w").write(params.private_key)
        # создаем папку в любом случае
        snippets_dir = "/etc/nginx/compass_snippets"
        os.makedirs(snippets_dir, exist_ok=True)
        data["nginx.ssl_crt"] = DoubleQuotedScalarString(os.path.basename(final_crt))
        data["nginx.ssl_key"] = DoubleQuotedScalarString(os.path.basename(final_key))
    else:
        # выпускаем Let's Encrypt через acme.sh
        le_dir = os.path.join(ssl_dir, "letsencrypt")
        os.makedirs(le_dir, exist_ok=True)

        # пути для итоговых сертификатов
        config_crt = os.path.join(
            "letsencrypt", f"{params.domain}_ecc", "fullchain.cer"
        )
        config_key = os.path.join(
            "letsencrypt", f"{params.domain}_ecc", f"{params.domain}.key"
        )
        final_crt = os.path.join(ssl_dir, config_crt)
        final_key = os.path.join(ssl_dir, config_key)

        acme_path = os.path.join(le_dir, "acme.sh")
        if not os.path.exists(acme_path):
            subprocess.run(
                [
                    "wget",
                    "-O",
                    acme_path,
                    "https://raw.githubusercontent.com/acmesh-official/acme.sh/3.0.7/acme.sh",
                ],
                check=True,
            )
            subprocess.run(["chmod", "+x", acme_path], check=True)

        # базовые команды
        subprocess.run(
            [
                acme_path,
                "--home",
                le_dir,
                "--set-default-ca",
                "--server",
                "letsencrypt",
            ],
            check=True,
        )
        subprocess.run([acme_path, "--upgrade", "--home", le_dir], check=True)
        subprocess.run([acme_path, "--register-account", "--home", le_dir], check=True)

        # 1) регистрируем аккаунт и парсим thumbprint из вывода
        reg = subprocess.run(
            [acme_path, "--register-account", "--home", le_dir],
            check=True,
            text=True,
            capture_output=True,
        )
        reg_out = (reg.stdout or "") + (reg.stderr or "")
        m = re.search(r"ACCOUNT_THUMBPRINT='([^']+)'", reg_out)
        if not m:
            raise RuntimeError(
                "Не удалось получить ACCOUNT_THUMBPRINT из вывода acme.sh --register-account. "
                "Вывод:\n" + reg_out
            )
        thumbprint = m.group(1)

        # 2) создаём nginx-сниппет с правилом /.well-known/acme-challenge
        snippets_dir = "/etc/nginx/compass_snippets"
        os.makedirs(snippets_dir, exist_ok=True)
        acme_snippet_path = os.path.join(snippets_dir, f"acme_stateless.conf")
        snippet = f"""location ~ ^/\\.well-known/acme-challenge/([-_a-zA-Z0-9]+)$ {{
    default_type text/plain;
    return 200 "$1.{thumbprint}";
}}
"""
        with open(acme_snippet_path, "w") as f:
            f.write(snippet)

        # 2.1) создаём отдельный nginx-конфиг /etc/nginx/sites-enabled-installer/acme.nginx
        # нужен только во время первой установки, далее продлеваться через star.compass.nginx будет
        acme_conf_path = "/etc/nginx/sites-enabled-installer/acme.nginx"
        acme_conf = f"""server {{
    listen 80;
    return 404;
}}

server {{

    listen 80;
    server_name {params.domain};

    location ~ ^/\\.well-known/acme-challenge/([-_a-zA-Z0-9]+)$ {{
        default_type text/plain;
        return 200 "$1.{thumbprint}";
    }}

    location / {{
        return 301 https://$host$request_uri;
    }}

}}
"""
        with open(acme_conf_path, "w") as f:
            f.write(acme_conf)

        # 3) релоадим nginx, чтобы правило для --issue заработало
        subprocess.run(["/usr/sbin/nginx", "-t"], check=True)
        subprocess.run(["/usr/sbin/nginx", "-s", "reload"], check=True)

        # 4) выпускаем сертификат в stateless режиме, если еще не выпущен
        if not os.path.exists(final_crt) or not os.path.exists(final_key):
            subprocess.run(
                [
                    acme_path,
                    "--home",
                    le_dir,
                    "--issue",
                    "--force",
                    "--stateless",
                    "-d",
                    params.domain,
                ],
                check=True,
            )

            # добавляем в crontab
            renew_cmd = f"{acme_path} --home {le_dir} --renew --force --stateless -d {params.domain}"
            nginx_reload_cmd = "/usr/sbin/nginx -t && /usr/sbin/nginx -s reload"

            cron_line_renew = f"0 0 15 * * {renew_cmd}"
            cron_line_nginx = f"0 3 15 * * {nginx_reload_cmd}"

            # добавляем по одной, избегая дубликатов
            subprocess.run(
                [
                    "bash",
                    "-c",
                    f'(crontab -l 2>/dev/null | grep -v -F "{renew_cmd}"; echo "{cron_line_renew}") | crontab -',
                ],
                check=True,
            )
            subprocess.run(
                [
                    "bash",
                    "-c",
                    f'(crontab -l 2>/dev/null | grep -v -F "{nginx_reload_cmd}"; echo "{cron_line_nginx}") | crontab -',
                ],
                check=True,
            )

        data["nginx.ssl_crt"] = DoubleQuotedScalarString(config_crt)
        data["nginx.ssl_key"] = DoubleQuotedScalarString(config_key)

    data["root_mount_path"] = DoubleQuotedScalarString("/home/compass")
    save_yaml(global_path, data)

    # 2.2) auth.yaml
    auth_path = os.path.join(CONFIG_DIR, "auth.yaml")
    auth = load_yaml(auth_path)
    for key in ("available_methods", "available_guest_methods"):
        seq = CommentedSeq([DoubleQuotedScalarString(m) for m in params.auth_methods])
        seq.fa.set_flow_style()
        auth[key] = seq

    if "phone_number" in params.auth_methods:
        # SMS Agent
        if "sms_agent" in params.sms_providers:
            for key in (
                "sms_agent.provide_phone_code_list",
                "sms_agent.high_priority_phone_code_list",
            ):
                seq = CommentedSeq([DoubleQuotedScalarString("+79")])
                seq.fa.set_flow_style()
                auth[key] = seq
            auth["sms_agent.min_balance_value"] = 10000
            auth["sms_agent.app_name"] = DoubleQuotedScalarString(
                params.sms_agent_app_name
            )
            auth["sms_agent.login"] = DoubleQuotedScalarString(params.sms_agent_login)
            auth["sms_agent.password"] = DoubleQuotedScalarString(
                params.sms_agent_password
            )
        else:
            # отключаем sms_agent блок
            for k in [
                "sms_agent.provide_phone_code_list",
                "sms_agent.high_priority_phone_code_list",
                "sms_agent.min_balance_value",
                "sms_agent.app_name",
                "sms_agent.login",
                "sms_agent.password",
            ]:
                auth[k] = ""

        # Vonage
        if "vonage" in params.sms_providers:
            for key in (
                "vonage.provide_phone_code_list",
                "vonage.high_priority_phone_code_list",
            ):
                seq = CommentedSeq([DoubleQuotedScalarString("+79")])
                seq.fa.set_flow_style()
                auth[key] = seq
            auth["vonage.min_balance_value"] = 100
            auth["vonage.app_name"] = DoubleQuotedScalarString(params.vonage_app_name)
            auth["vonage.api_key"] = DoubleQuotedScalarString(params.vonage_api_key)
            auth["vonage.api_secret"] = DoubleQuotedScalarString(
                params.vonage_api_secret
            )
        else:
            # отключаем vonage блок
            for k in [
                "vonage.provide_phone_code_list",
                "vonage.high_priority_phone_code_list",
                "vonage.min_balance_value",
                "vonage.app_name",
                "vonage.api_key",
                "vonage.api_secret",
            ]:
                auth[k] = ""

        # Twilio
        if "twilio" in params.sms_providers:
            for key in (
                "twilio.provide_phone_code_list",
                "twilio.high_priority_phone_code_list",
            ):
                seq = CommentedSeq([DoubleQuotedScalarString("+79")])
                seq.fa.set_flow_style()
                auth[key] = seq
            auth["twilio.min_balance_value"] = 100
            auth["twilio.app_name"] = DoubleQuotedScalarString(params.twilio_app_name)
            auth["twilio.account_sid"] = DoubleQuotedScalarString(
                params.twilio_account_sid
            )
            auth["twilio.account_auth_token"] = DoubleQuotedScalarString(
                params.twilio_account_auth_token
            )
        else:
            # отключаем twilio блок
            for k in [
                "twilio.provide_phone_code_list",
                "twilio.high_priority_phone_code_list",
                "twilio.min_balance_value",
                "twilio.app_name",
                "twilio.account_sid",
                "twilio.account_auth_token",
            ]:
                auth[k] = ""

    else:
        # отключаем весь SMS-блок
        for k in [
            "sms_agent.provide_phone_code_list",
            "sms_agent.high_priority_phone_code_list",
            "sms_agent.min_balance_value",
            "sms_agent.app_name",
            "sms_agent.login",
            "sms_agent.password",
            "vonage.provide_phone_code_list",
            "vonage.high_priority_phone_code_list",
            "vonage.min_balance_value",
            "vonage.app_name",
            "vonage.api_key",
            "vonage.api_secret",
            "twilio.provide_phone_code_list",
            "twilio.high_priority_phone_code_list",
            "twilio.min_balance_value",
            "twilio.app_name",
            "twilio.account_sid",
            "twilio.account_auth_token",
        ]:
            auth[k] = ""

    # Email
    if "mail" in params.auth_methods:
        auth["mail.registration_2fa_enabled"] = bool(params.mail_2fa_enabled)
        auth["mail.authorization_2fa_enabled"] = bool(params.mail_2fa_enabled)
        
        auth["smtp.host"] = DoubleQuotedScalarString(params.smtp_host)
        auth["smtp.port"] = int(params.smtp_port)
        auth["smtp.username"] = DoubleQuotedScalarString(params.smtp_user)
        auth["smtp.password"] = DoubleQuotedScalarString(params.smtp_pass)
        auth["smtp.encryption"] = DoubleQuotedScalarString(params.smtp_encryption)
        auth["smtp.from"] = DoubleQuotedScalarString(params.smtp_from)
    else:
        # отключаем SMTP-блок
        for k in [
            "smtp.host",
            "smtp.port",
            "smtp.username",
            "smtp.password",
            "smtp.encryption",
            "smtp.from",
        ]:
            auth[k] = ""

    # SSO
    if "sso" in params.auth_methods:
        auth["sso.protocol"] = DoubleQuotedScalarString(params.sso_protocol)
        auth["sso.compass_mapping.name"] = DoubleQuotedScalarString(
            params.sso_compass_mapping_name
        )
        auth["sso.compass_mapping.avatar"] = DoubleQuotedScalarString(
            params.sso_compass_mapping_avatar
        )
        auth["sso.compass_mapping.badge"] = DoubleQuotedScalarString(
            params.sso_compass_mapping_badge
        )
        auth["sso.compass_mapping.role"] = DoubleQuotedScalarString(
            params.sso_compass_mapping_role
        )
        auth["sso.compass_mapping.bio"] = DoubleQuotedScalarString(
            params.sso_compass_mapping_bio
        )

        if params.sso_protocol == "oidc":
            auth["oidc.client_id"] = DoubleQuotedScalarString(params.oidc_client_id)
            auth["oidc.client_secret"] = DoubleQuotedScalarString(
                params.oidc_client_secret
            )
            auth["oidc.oidc_provider_metadata_link"] = DoubleQuotedScalarString(
                params.oidc_oidc_provider_metadata_link
            )
            auth["oidc.attribution_mapping.mail"] = DoubleQuotedScalarString(
                params.oidc_attribution_mapping_mail
            )
            auth["oidc.attribution_mapping.phone_number"] = DoubleQuotedScalarString(
                params.oidc_attribution_mapping_phone_number
            )
        else:
            # отключаем oidc-блок
            for k in [
                "oidc.client_id",
                "oidc.client_secret",
                "oidc.oidc_provider_metadata_link",
                "oidc.attribution_mapping.mail",
                "oidc.attribution_mapping.phone_number",
            ]:
                auth[k] = ""

        if params.sso_protocol == "ldap":
            auth["ldap.server_host"] = DoubleQuotedScalarString(params.ldap_server_host)
            auth["ldap.server_port"] = DoubleQuotedScalarString(
                str(params.ldap_server_port)
            )
            auth["ldap.use_ssl"] = params.ldap_use_ssl
            auth["ldap.require_cert_strategy"] = DoubleQuotedScalarString(
                params.ldap_require_cert_strategy
            )
            auth["ldap.user_search_base"] = DoubleQuotedScalarString(
                params.ldap_user_search_base
            )
            auth["ldap.user_unique_attribute"] = DoubleQuotedScalarString(
                params.ldap_user_unique_attribute
            )
            auth["ldap.user_login_attribute"] = DoubleQuotedScalarString(
                params.ldap_user_unique_attribute
            )  # пока не добавляем новое поле, просто ставим тоже значение, что и в ldap.user_unique_attribute
            auth["ldap.user_search_filter"] = DoubleQuotedScalarString(
                params.ldap_user_search_filter
            )
            auth["ldap.user_search_account_dn"] = DoubleQuotedScalarString(
                params.ldap_user_search_account_dn
            )
            auth["ldap.user_search_account_password"] = DoubleQuotedScalarString(
                params.ldap_user_search_account_password
            )
            auth["ldap.account_disabling_monitoring_enabled"] = (
                params.ldap_account_disabling_monitoring_enabled
            )
        else:
            # отключаем ldap-блок
            for k in [
                "ldap.server_host",
                "ldap.server_port",
                "ldap.user_search_base",
                "ldap.user_unique_attribute",
                "ldap.user_login_attribute",
                "ldap.user_search_filter",
                "ldap.user_search_account_dn",
                "ldap.user_search_account_password",
            ]:
                auth[k] = ""
            auth["ldap.use_ssl"] = True
            auth["ldap.require_cert_strategy"] = DoubleQuotedScalarString("demand")
            auth["ldap.account_disabling_monitoring_enabled"] = False
    else:
        # отключаем SSO полностью
        for k in [
            "sso.protocol",
            "sso.compass_mapping.name",
            "sso.compass_mapping.avatar",
            "sso.compass_mapping.badge",
            "sso.compass_mapping.role",
            "sso.compass_mapping.bio",
            "oidc.client_id",
            "oidc.client_secret",
            "oidc.oidc_provider_metadata_link",
            "oidc.attribution_mapping.mail",
            "oidc.attribution_mapping.phone_number",
            "ldap.server_host",
            "ldap.server_port",
            "ldap.user_search_base",
            "ldap.user_unique_attribute",
            "ldap.user_login_attribute",
            "ldap.user_search_filter",
            "ldap.user_search_account_dn",
            "ldap.user_search_account_password",
        ]:
            auth[k] = ""
        auth["ldap.use_ssl"] = True
        auth["ldap.require_cert_strategy"] = DoubleQuotedScalarString("demand")
        auth["ldap.account_disabling_monitoring_enabled"] = False

    save_yaml(auth_path, auth)

    # 2.3) captcha.yaml
    captcha_path = os.path.join(CONFIG_DIR, "captcha.yaml")
    captcha = load_yaml(captcha_path)
    captcha["captcha.enabled"] = False
    save_yaml(captcha_path, captcha)

    # 2.4) team.yaml
    team_path = os.path.join(CONFIG_DIR, "team.yaml")
    team = load_yaml(team_path)
    team["root_user.full_name"] = DoubleQuotedScalarString(params.root_user_full_name)
    team["root_user.mail"] = DoubleQuotedScalarString(params.root_user_mail)
    team["root_user.password"] = DoubleQuotedScalarString(params.root_user_pass)
    team["team.init_name"] = DoubleQuotedScalarString(params.space_name)
    team["root_user.sso_login"] = (
        DoubleQuotedScalarString(params.root_user_sso_login)
        if "sso" in params.auth_methods
        else ""
    )
    team["root_user.phone_number"] = (
        DoubleQuotedScalarString(params.root_user_phone)
        if "phone_number" in params.auth_methods
        else ""
    )
    save_yaml(team_path, team)

    # 2.5) installer.yaml
    installer = {
        "url": params.domain,
        "auth_methods": params.auth_methods,
        "credentials": {
            "phone_number": params.root_user_phone,
            "mail_login": params.root_user_mail,
            "mail_password": params.root_user_pass,
            "sso_login": params.root_user_sso_login,
        },
    }
    save_yaml(os.path.join(CONFIG_DIR, "installer.yaml"), installer)

    return JSONResponse({"success": True})


@app.post("/api/install/validate")
def api_install_validate():
    proc = subprocess.run(
        [
            "sudo",
            PYTHON_BIN,
            BASE_DIR / "script/install.py",
            "--confirm-all",
            "--validate-only",
            "--installer-output",
        ],
        text=True,
        capture_output=True,
    )
    script_ok = proc.returncode == 0
    script_output = (proc.stdout or "") + (proc.stderr or "")

    try:
        invalid_keys = json.loads(script_output)
    except Exception:
        invalid_keys = []

    return JSONResponse({"success": script_ok, "invalid_keys": invalid_keys})


@app.post("/api/install/run")
def api_run_install(background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    tasks[job_id] = {"status": "running", "log": ""}
    background_tasks.add_task(do_install, job_id)
    return JSONResponse({"success": True, "job_id": job_id})


@app.post("/api/install/back_to_configure")
def api_back_to_configure():
    proc = subprocess.run(
        [PYTHON_BIN, BASE_DIR / "script/uninstall.py", "--confirm-all"],
        text=True,
        capture_output=True,
    )

    success = proc.returncode == 0
    return JSONResponse(
        {"success": success, "log": (proc.stdout or "") + (proc.stderr or "")}
    )


# через delay_sec секунд останавливает и отключает compass-installer.service
def _stop_and_disable_installer_service(delay_sec: int = 300):
    try:
        time.sleep(delay_sec)
        subprocess.run(
            ["sudo", "rm", "/etc/nginx/sites-enabled-installer/installer.nginx"],
            check=False,
        )
        subprocess.run(["nginx", "-s", "reload"], check=False)
        subprocess.run(
            ["sudo", "systemctl", "stop", "compass-installer.service"], check=False
        )
        subprocess.run(
            ["sudo", "systemctl", "disable", "compass-installer.service"], check=False
        )
        subprocess.run(
            ["sudo", "rm", "/etc/systemd/system/compass-installer.service"], check=False
        )
    except Exception:
        # ничего критичного: не мешаем основному приложению
        pass


@app.post("/api/install/activate_server")
def api_activate_server(background_tasks: BackgroundTasks):
    proc = subprocess.run(
        [PYTHON_BIN, BASE_DIR / "script/activate_server.py"],
        text=True,
        capture_output=True,
    )

    success = proc.returncode == 0

    # если сервер успешно активирован — через 10 минут останавливаем и отключаем инсталлер
    if success:
        background_tasks.add_task(_stop_and_disable_installer_service, 600)

    return JSONResponse(
        {
            "success": success,
        }
    )


@app.get("/api/install/status/{job_id}")
def api_status(job_id: str):
    if job_id not in tasks:
        return JSONResponse(
            {
                "success": True,
                "completed_step_list": [],
                "status": "not_found",
                "log": "",
            }
        )

    completed_step_list = load_completed_steps()

    return JSONResponse(
        {
            "success": True,
            "completed_step_list": completed_step_list,
            "status": tasks[job_id]["status"],
        }
    )


@app.get("/api/install/logs/{job_id}")
def api_download_logs(job_id: str):
    if job_id not in tasks:
        raise HTTPException(status_code=404, detail="job not found")
    log_text = tasks[job_id].get("log", "")
    return Response(
        content=log_text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="install_logs.txt"'},
    )


@app.get("/api/install/result/{job_id}", response_model=ResultResponse)
def api_result(job_id: str):
    if job_id not in tasks or tasks[job_id]["status"] != "finished":
        return JSONResponse({"success": True, "status": "not_found", "data": {}})
    installer = load_yaml(os.path.join(CONFIG_DIR, "installer.yaml"))
    return {
        "success": True,
        "status": "installed",
        "data": {
            "url": installer.get("url"),
            "auth_methods": installer.get("auth_methods"),
            "credentials": installer.get("credentials", {}),
        },
    }


# — вспомогательные функции для работы с YAML —
def load_yaml(path: str):
    with open(path) as f:
        return yaml.load(f)


def save_yaml(path: str, data):
    with open(path, "w") as f:
        yaml.dump(data, f)


def get_host_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def do_install(job_id: str):
    tasks[job_id]["status"] = "running"
    try:
        proc = subprocess.Popen(
            [PYTHON_BIN, BASE_DIR / "script/install.py", "--confirm-all"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        for line in proc.stdout:
            tasks[job_id]["log"] += line
        proc.wait()
        tasks[job_id]["status"] = "finished" if proc.returncode == 0 else "error"
    except Exception as e:
        tasks[job_id]["log"] += str(e)
        tasks[job_id]["status"] = "error"


app.mount("/", StaticFiles(directory=str(DIST_DIR), html=True), name="frontend")


# если ни один из предыдущих роутов не подошёл - отдаем index.html
@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    return FileResponse(str(DIST_DIR / "index.html"))
