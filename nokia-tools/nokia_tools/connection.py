"""Apertura de sesiones SSH hacia equipos Nokia SR OS usando Netmiko."""
import logging
from contextlib import contextmanager

from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException

logger = logging.getLogger(__name__)


class ConnectionError_(Exception):
    pass


@contextmanager
def connect(device: dict):
    """Context manager que entrega una conexión Netmiko lista para usar.

    `device` es el dict del inventario (host, username, password, device_type, ...).
    """
    params = {
        "device_type": device.get("device_type", "nokia_sros"),
        "host": device["host"],
        "username": device["username"],
        "password": device["password"],
        "port": device.get("port", 22),
        "secret": device.get("secret", ""),
    }

    logger.info("Conectando a %s (%s)...", device["host"], params["device_type"])
    try:
        conn = ConnectHandler(**params)
    except NetmikoAuthenticationException as exc:
        raise ConnectionError_(f"Fallo de autenticación con {device['host']}: {exc}") from exc
    except NetmikoTimeoutException as exc:
        raise ConnectionError_(f"Timeout conectando a {device['host']}: {exc}") from exc

    try:
        yield conn
    finally:
        conn.disconnect()
        logger.info("Desconectado de %s.", device["host"])
