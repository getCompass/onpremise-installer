import subprocess
import shutil
import re
from typing import Tuple
import utils

DOCKER_DIST_PACKAGES = [
    "docker-ce",
    "docker-compose",
]

DOCKER_REPO_PACKAGES = [
    "docker-ce",
    "docker-compose-plugin",
]

TRUSTED_DIST_IDS = [
    "ubuntu",
    "debian",
    "rhel",
    "centos",
    "fedora",
]

MINIMAL_MAJOR_DOCKER_VERSION = 21


def check_docker_installed() -> bool:
    """
    Проверяем, что docker установлен
    """
    docker_path = shutil.which("docker")

    return bool(docker_path)


def install_docker(package_manager: str) -> Tuple[bool, str]:
    """
    Установить актуальную версию docker
    В приоритете ставим из репозитория дистрибутива, чтобы не нарваться на конфликты
    """

    os_dist = utils.get_os_dist()

    if os_dist not in TRUSTED_DIST_IDS:
        os_dist_list = utils.get_os_based_dist_list()
        trusted_ids = frozenset(TRUSTED_DIST_IDS)
        d: list = [x for x in os_dist_list if x in trusted_ids]
        if not d:
            return (
                False,
                "Не найден официальный репозиторий docker для данного дистрибутива",
            )
        os_dist = list(d)[0]

    if package_manager == "deb":

        version, error = _get_own_repo_docker_major_version_deb()

        if error:
            return False, error
        if version >= MINIMAL_MAJOR_DOCKER_VERSION:
            success, logs = _install_docker_from_own_repo_deb()
        else:
            success, logs = _install_from_docker_repo_deb(os_dist)
    elif package_manager == "rpm":

        version, error = _get_own_repo_docker_major_version_rpm()

        if error:
            return False, error
        if version >= MINIMAL_MAJOR_DOCKER_VERSION:
            success, logs = _install_docker_from_own_repo_rpm()
        else:
            success, logs = _install_from_docker_repo_rpm(os_dist)

    else:
        return False, "Установлен неподдерживаемый менеджер пакетов"
    
    if not success:
        return False, logs
    return enable_docker()


def _get_own_repo_docker_major_version_deb() -> Tuple[bool, str]:
    """
    Получить версию Docker Engine из дистрибутива на Debian/Ubuntu
    """

    r = utils.run(
        "apt-cache show docker-ce | grep -i version | awk '{print $2}' | sort -V | tail -n1"
    )
    if r.returncode != 0:
        return 0, r.stderr or r.stdout

    if r.stdout == "":
        return 0, ""

    version_regexp = r"([0-9]+)\.[0-9]+\.[0-9]+"

    version_search = re.search(version_regexp, r.stdout, re.IGNORECASE)
    if version_search:
        return int(version_search.group(1)), ""
    return 0, ""


def _install_docker_from_own_repo_deb() -> Tuple[bool, str]:
    """
    Установка Docker Engine на Debian/Ubuntu из репозитория дистрибутива
    """
    try:
        r = utils.run(["apt-get", "update"], timeout=300, check=False)
        if r.returncode != 0:
            return False, r.stderr or r.stdout

        r = utils.run(
            [
                "apt-get",
                "install",
                "-y",
            ]
            + DOCKER_DIST_PACKAGES,
            timeout=1800,
            check=False,
        )

        return True, ""
    except subprocess.TimeoutExpired:
        return False, "Превышено время ожидания установки Docker"
    except Exception as e:
        return False, str(e)


def _install_from_docker_repo_deb(os_dist: str) -> Tuple[bool, str]:
    """
    Установка Docker Engine на Debian/Ubuntu по официальной инструкции:
    https://docs.docker.com/engine/install/
    """
    try:
        # 1) prerequisites
        r = utils.run(["apt-get", "update"], timeout=300, check=False)
        if r.returncode != 0:
            return False, r.stderr or r.stdout

        # gnupg нужен для gpg --dearmor, lsb-release иногда полезен, но мы берем VERSION_CODENAME из os-release
        r = utils.run(
            ["apt-get", "install", "-y", "ca-certificates", "curl", "gnupg"],
            timeout=900,
            check=False,
        )
        if r.returncode != 0:
            return False, r.stderr or r.stdout

        # 2) keyrings dir
        r = utils.run(
            ["install", "-m", "0755", "-d", "/etc/apt/keyrings"],
            timeout=60,
            check=False,
        )
        if r.returncode != 0:
            return False, r.stderr or r.stdout

        dist_version = utils.get_dist_version(os_dist)

        r = utils.run(
            f"curl -fsSL https://download.docker.com/linux/{os_dist}/gpg "
            "| gpg --dearmor -o /etc/apt/keyrings/docker.gpg",
            timeout=300,
            check=False,
        )
        if r.returncode != 0:
            return False, r.stderr or r.stdout

        utils.run(
            ["chmod", "a+r", "/etc/apt/keyrings/docker.gpg"], timeout=30, check=False
        )

        # 4) add repo
        r = utils.run(
            'echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] '
            f"https://download.docker.com/linux/{os_dist} "
            f'{dist_version} stable" '
            "| tee /etc/apt/sources.list.d/docker.list > /dev/null",
            timeout=120,
            check=False,
        )
        if r.returncode != 0:
            return False, r.stderr or r.stdout

        # 5) install docker packages
        r = utils.run(["apt-get", "update"], timeout=300, check=False)
        if r.returncode != 0:
            return False, r.stderr or r.stdout

        r = utils.run(
            [
                "apt-get",
                "install",
                "-y",
            ]
            + DOCKER_REPO_PACKAGES,
            timeout=1800,
            check=False,
        )
        if r.returncode != 0:
            return False, r.stderr or r.stdout

        # 6) post-install: удалить apparmor и рестарт docker (как вы просили)
        # Делаем best-effort: если apparmor отсутствует — не валим установку.
        utils.run("sudo /etc/init.d/apparmor stop || true", timeout=120, check=False)
        utils.run(
            "sudo update-rc.d -f apparmor remove || true", timeout=120, check=False
        )
        utils.run("sudo apt-get remove -y apparmor || true", timeout=900, check=False)

        return True, ""
    except subprocess.TimeoutExpired:
        return False, "Превышено время ожидания установки Docker"
    except Exception as e:
        return False, str(e)


def _get_own_repo_docker_major_version_rpm() -> Tuple[int, str]:
    """
    Получить мажорную версию Docker Engine из дистрибутива на RPM (CentOS/RHEL/Fedora)
    """
    # Определяем менеджер
    has_yum = bool(shutil.which("yum"))
    pm = "yum" if has_yum else "dnf"

    r = utils.run("%s list docker-ce | sort -V | tail -n1 | awk '{print $2}'" % pm)
    if r.returncode != 0:
        return 0, r.stderr or r.stdout

    if r.stdout == "":
        return 0, ""

    version_regexp = r"([0-9]+)\.[0-9]+\.[0-9]+"

    version_search = re.search(version_regexp, r.stdout, re.IGNORECASE)
    if version_search:
        return int(version_search.group(1)), ""
    return 0, ""


def _install_from_docker_repo_rpm(os_dist: str) -> Tuple[bool, str]:
    """
    Установка Docker Engine на RPM (CentOS/RHEL/Fedora) по официальной инструкции:
    https://docs.docker.com/engine/install/
    """
    try:
        # Определяем менеджер
        has_yum = bool(shutil.which("yum"))
        pm = "yum" if has_yum else "dnf"

        # yum-utils/dnf-plugins-core нужны для yum-config-manager/dnf config-manager
        if pm == "yum":
            r = utils.run(
                ["yum", "install", "-y", "yum-utils"], timeout=1200, check=False
            )
            if r.returncode != 0:
                return False, r.stderr or r.stdout
        else:
            r = utils.run(
                ["dnf", "install", "-y", "dnf-plugins-core"], timeout=1200, check=False
            )
            if r.returncode != 0:
                return False, r.stderr or r.stdout

        # Репозиторий Docker
        r = utils.run(
            [
                pm,
                "config-manager",
                "--add-repo",
                f"https://download.docker.com/linux/{os_dist}/docker-ce.repo",
            ],
            timeout=300,
            check=False,
        )
        if r.returncode != 0:
            return False, r.stderr or r.stdout

        r = utils.run(
            [
                pm,
                "install",
                "-y",
            ]
            + DOCKER_REPO_PACKAGES,
            timeout=1800,
            check=False,
        )
        if r.returncode != 0:
            return False, r.stderr or r.stdout

        return True, ""
    except subprocess.TimeoutExpired:
        return False, "Превышено время ожидания установки Docker"
    except Exception as e:
        return False, str(e)


def _install_docker_from_own_repo_rpm() -> Tuple[bool, str]:
    """
    Установка Docker Engine на RPM (CentOS/RHEL/Fedora) из репозитория дистрибутива
    """

    # Определяем менеджер
    has_yum = bool(shutil.which("yum"))
    pm = "yum" if has_yum else "dnf"
    try:

        utils.run(
            [
                pm,
                "install",
                "-y",
            ]
            + DOCKER_DIST_PACKAGES,
            timeout=1800,
            check=True,
        )

        return True, ""
    except subprocess.TimeoutExpired:
        return False, "Превышено время ожидания установки Docker"
    except Exception as e:
        return False, str(e)


def enable_docker() -> Tuple[bool, str]:
    """
    Запустить docker
    """

    # рестарт docker (init.d или systemd)
    r = utils.run(
        "systemctl restart docker || /etc/init.d/docker restart || true",
        timeout=120,
        check=False,
    )
    if r.returncode != 0 and (r.stderr or r.stdout):
        # не считаем критической ошибкой, но вернем предупреждение как текст ошибки
        return False, r.stderr or r.stdout
    
    # инициируем docker swarm
    r = utils.run(
        "docker swarm init || true",
        timeout=120,
        check=False,
    )
    if r.returncode != 0 and (r.stderr or r.stdout):
        # не считаем критической ошибкой, но вернем предупреждение как текст ошибки
        return False, r.stderr or r.stdout
    return True, ""