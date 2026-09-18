# Общий билдер sql для пользователя репликации
# Используется скриптом create_mysql_user.py

# REPLICATION CLIENT нужен для peer-проверок отказоустойчивости:
# чтения @@global.gtid_executed при сверке GTID и fence (mysql_fence.py)
def build_replicator_user_sql(user: str, password: str) -> str:
    return (
        "CREATE USER IF NOT EXISTS '%s'@'%%' IDENTIFIED WITH mysql_native_password BY '%s';" % (user, password)
        + "GRANT REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO '%s'@'%%';" % user
        + "FLUSH PRIVILEGES;"
    )
