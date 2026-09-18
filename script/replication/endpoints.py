import ipaddress
import re
from typing import Mapping, Tuple


MONOLITH_MYSQL_PORT = 3306
MANTICORE_CLUSTER_PORT = 9312
HOSTNAME_PATTERN = re.compile(
    r"^(?=.{1,253}\.?$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.?)+$"
)
IPV4_SHAPED_PATTERN = re.compile(r"^[0-9.]+$")


def validate_peer_host(peer_host: str) -> str:
    if not isinstance(peer_host, str):
        raise ValueError("peer_host must be a string")

    peer_host = peer_host.strip()
    if peer_host == "":
        raise ValueError("peer_host must be an IP address or hostname without a port")

    try:
        address = ipaddress.ip_address(peer_host)
    except ValueError:
        hostname = peer_host.rstrip(".").lower()
        if (
            IPV4_SHAPED_PATTERN.fullmatch(peer_host) is not None
            or HOSTNAME_PATTERN.fullmatch(peer_host) is None
            or hostname == "localhost"
            or hostname.endswith(".localhost")
        ):
            raise ValueError("peer_host must be an IP address or hostname without a port")
    else:
        if not isinstance(address, ipaddress.IPv4Address) or any((
            address.is_unspecified,
            address.is_loopback,
            address.is_multicast,
            address.is_link_local,
            address.is_reserved,
        )):
            raise ValueError("peer_host must be a routable IPv4 address or hostname")

    return peer_host


def normalize_peer_host(service_label: str, peer_host: str) -> str:
    if service_label == "":
        return ""

    return validate_peer_host(peer_host)


def peer_mysql_endpoint(values: Mapping, port: int = MONOLITH_MYSQL_PORT) -> Tuple[str, int]:
    return validate_peer_host(values.get("peer_host", "")), int(port)


def peer_manticore_endpoint(values: Mapping) -> str:
    return "%s:%d" % (validate_peer_host(values.get("peer_host", "")), MANTICORE_CLUSTER_PORT)
