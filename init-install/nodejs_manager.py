import subprocess
import shutil
import re
from typing import Tuple
import utils

def check_nodejs_installed() -> bool:
    """
    Проверяем, что nodejs установлен
    """
    node_path = shutil.which("node")
    npm_path = shutil.which("npm")

    return bool(node_path and npm_path)


def get_actual_node_js_version() -> Tuple[bool, str]:
    """
    Возвращает актуальную версию node js
    """
    command = [
        "curl",
        "-Ls",
        "-o",
        "/dev/null",
        "-w",
        "%{url_effective}",
        "https://nodejs.org/en/download/archive/current",
    ]
    result = subprocess.run(
        command,
        check=False,
        timeout=1800,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        return (
            False,
            result.stderr
            or result.stdout
            or "Неизвестная ошибка при получении версии node js",
        )

    version = result.stdout.split("/")[-1]

    return True, version


def install_node_js(package_manager: str, version: str) -> Tuple[bool, str]:
    """
    Установить актуальную версию node js
    """
    version_regexp = r"^v([0-9]+).[0-9]+.[0-9]+"

    version_search = re.search(version_regexp, version, re.IGNORECASE)
    if version_search:
        major_version = version_search.group(1)
    else:
        return False, "Не смогли найти версию Node.js для установки"

    if package_manager == "deb":
        utils.run(
            f"curl -fsSL https://deb.nodesource.com/setup_{major_version}.x -o /tmp/nodesource_setup.sh "
            "&& bash /tmp/nodesource_setup.sh "
            "&& apt-get install -y nodejs"
        )
    else:  # rpm
        utils.run(f"curl -fsSL https://rpm.nodesource.com/setup_{major_version}.x | bash -")
        utils.run("yum install -y nodejs || dnf install -y nodejs")
    
    return True, ""
