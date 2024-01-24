#!/bin/bash

KEY=$(date +%s);
TEMPORARY_DIR="/tmp/.manticore_installer_${KEY}";
BACKUP_DIR="/tmp/.manticore_backup_${KEY}";

# сюда запишем domino-id для которого развернем manticore
DOMINO_ID="";
OVERRIDE_DATA="";

# region script-header
set -Eeuo pipefail
trap cleanup SIGINT SIGTERM ERR EXIT
# shellcheck disable=SC2034
NO_COLOR='\033[0m';BLACK='\033[0;30m';RED='\033[0;31m';GREEN='\033[0;32m';YELLOW='\033[0;33m';BLUE='\033[0;34m';PURPLE='\033[0;35m';CYAN='\033[0;36m';WHITE='\033[0;37m';
# shellcheck disable=SC2034
SCRIPT_PATH=$(cd -- "$(dirname "$0")" || exit 1 >/dev/null 2>&1 ; pwd -P); COMPASS_DEPLOY_PATH=$(cd -- "${SCRIPT_PATH}/../../../" || exit 1 >/dev/null 2>&1 ; pwd -P); VERBOSE=false;
# выводит сообщение в консоль, подавляется -v
function msg() { if $VERBOSE; then return; fi; echo >&2 -e "${1-}"; }
# выводит предупреждение в консоль
function wrn() { echo >&2 -e "${1-}"; }
# завершает работу выводя указанное сообщение с ошибкой
function die() { local MESSAGE=$1; local CODE=${2-1}; wrn "${RED}ERR${NO_COLOR}: ${MESSAGE}"; exit "${CODE}"; }
# запрашивает подвтержение
function confirm() { local RESPONSE; echo -e -n "${1} [y/N] "; read -r RESPONSE; case "${RESPONSE}" in [yY][eE][sS] | [yY]) true; ;; *) false; ;; esac; }
# убирает цвета из стандартного вывода скрипта
# shellcheck disable=SC2034
function desaturate() { NO_COLOR='';BLACK='';RED='';GREEN='';YELLOW='';BLUE='';PURPLE='';CYAN='';WHITE=''; }
# получает абсолютный путь для файла скрипта
function resolve_path() { echo "$(cd -- "$(dirname "$0")" || exit 1 >/dev/null 2>&1; pwd -P;)"; }
# превращает массив в строку# выводит справку для использования, для каждого скрипта ее необходимо полностью и детально описать
function usage() {

  msg "Скрипт для развертывания Manticore Search Engine в ОС Linux.";
  msg "Устанавливает и запускает manticore в режиме демона";
  msg "Параметры: -v, --values      [req] файл со значениями для подстановки";
  msg "           -e, --environment [req] среда, для которой нужно выполнить скрипт, определяет используемый compose-файл";
  msg "           -d, --domino-id   [req] ID домино, для которого нужно развернуть manticore";
}
# вызывается при завершении скрипта, здесь нужно подчистить весь мусор, что мог оставить скрипт
function cleanup() {

  trap - SIGINT SIGTERM ERR EXIT;
  rm -rf "${TEMPORARY_DIR}";
}
# парсит входные параметры; добавить новый параметр:  «--VALUE) something; ;;» перед блоком -?*),
# писать можно не в строчку, дефолтные просто для удобства так оформлены
function parse_params() {

  while true; do

    case "${1-}" in
    --help) usage; exit 0; ;;
    --verbose) VERBOSE=true; ;;
    --no-color) desaturate; ;;
    -e | --environment)
      ENVIRONMENT="${2-}";
      shift;
      ;;
    -v | --values)
      VALUES="${2-}";
      shift;
      ;;
    -d | --domino-id)
      DOMINO_ID+="${2-}";
      OVERRIDE_DATA+=" domino_id=${DOMINO_ID}"
      shift;
      ;;
    -?*) die "передан неизвестный параметр, используй --help чтобы получить информацию"; ;;
    *) break ;;
    esac
    shift;
  done

  [[ -z "${VALUES}" ]] && die "не передана среда для исполнения, --help для информации";
  [[ -z "${ENVIRONMENT}" ]] && die "не передан файл параметров, --help для информации";

  return 0;
}

# первым делом парсим входные параметры
parse_params "$@"
msg
# endregion script-header

mkdir -p "${TEMPORARY_DIR}"
mkdir -p "${BACKUP_DIR}"

# имена values файлов
VALUES_FILE_NAME="${COMPASS_DEPLOY_PATH}/src/values.yaml";
SPECIFIED_VALUES_FILE_NAME="${COMPASS_DEPLOY_PATH}/src/values.${VALUES}.yaml";

# если указан файл для окружения, то используем его
# пусть все страдают, путаясь в логике скрипта
[[ -f "${COMPASS_DEPLOY_PATH}/src/values.${ENVIRONMENT}.${VALUES}.yaml" ]] && SPECIFIED_VALUES_FILE_NAME="src/values.${ENVIRONMENT}.${VALUES}.yaml";

msg "${BLUE}резервные копии предыдущих файлов будут помещены в ${BACKUP_DIR}${NO_COLOR}";

# снимаем бэкапы файлов на всякий
if [[ -f "/etc/manticoresearch/manticore.conf" ]]; then

  msg "делаю копию файлов настроек /etc/manticoresearch/manticore.conf" ;
  /bin/cp -rf "/etc/manticoresearch/manticore.conf" "${BACKUP_DIR}/manticore.conf.backup";
fi;

# создаем директорию под конфиг
mkdir -p /etc/manticoresearch/;

# создаем директорию под индексы
MANTICORE_PATH=$(yq ".projects.domino.${DOMINO_ID}.manticore_path" "${SPECIFIED_VALUES_FILE_NAME}")
mkdir -p "${MANTICORE_PATH}";

# накатываем мантикору
wget https://repo.manticoresearch.com/manticore-repo.noarch.deb -O "${TEMPORARY_DIR}/manticore-repo.noarch.deb";
sudo dpkg -i "${TEMPORARY_DIR}/manticore-repo.noarch.deb";
sudo apt update;
sudo apt install -y manticore;

if [ $? -eq 0 ]; then
    msg "${GREEN}manticore успешно развернута${NO_COLOR}"
else
    die "произошла ошибка при установке Manticore"
fi

# генерируем конфиг-файлы и manticore.service:
bash "${COMPASS_DEPLOY_PATH}/script/template.sh" \
    "${SCRIPT_PATH}/../config/manticore.goconf" \
    "${VALUES_FILE_NAME} ${SPECIFIED_VALUES_FILE_NAME}" \
    "${TEMPORARY_DIR}/manticore.conf" \
    "${OVERRIDE_DATA}" \
    || die "не удалось сгенерировать конфиг-файл manticore.conf";
bash "${COMPASS_DEPLOY_PATH}/script/template.sh" \
    "${SCRIPT_PATH}/manticore.goservice" \
    "${VALUES_FILE_NAME} ${SPECIFIED_VALUES_FILE_NAME}" \
    "${TEMPORARY_DIR}/manticore.service" \
    "" \
    || die "не удалось сгенерировать manticore.service";
/bin/cp -rf "${TEMPORARY_DIR}/manticore.service" "/etc/systemd/system/manticore.service.d/override.conf";
/bin/cp -rf "${TEMPORARY_DIR}/manticore.conf" "/etc/manticoresearch/manticore.conf";

# запускаем
systemctl daemon-reload;
systemctl start manticore.service;

if [ $? -eq 0 ]; then
    msg "${GREEN}manticore успешно запущена${NO_COLOR}"
else
    die "произошла ошибка при запуске Manticore, смотри ${YELLOW}systemctl status manticore.service"
fi

if [[ -z "$(ls -A ${BACKUP_DIR})" ]] || confirm "${YELLOW}удаляем бэкапы?${NO_COLOR}"; then

  rm -rf "${BACKUP_DIR}"
  msg "бэкапы удалены"
fi;

msg "проверить статус демона можно командой ${YELLOW}systemctl status manticore.service${NO_COLOR}"
msg "${GREEN}завершено!${NO_COLOR}"