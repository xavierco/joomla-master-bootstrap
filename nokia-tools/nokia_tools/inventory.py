"""Carga del inventario de equipos Nokia desde un archivo YAML."""
from pathlib import Path
import yaml


class InventoryError(Exception):
    pass


def load_inventory(path: str) -> dict:
    """Lee inventory.yaml y devuelve el dict de dispositivos."""
    file_path = Path(path)
    if not file_path.exists():
        raise InventoryError(
            f"No se encontró el inventario en '{path}'. "
            "Copia inventory.yaml.example a inventory.yaml y complétalo."
        )

    with file_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    devices = data.get("devices", {})
    if not devices:
        raise InventoryError(f"El inventario '{path}' no define ningún dispositivo.")

    return devices


def get_device(inventory: dict, name: str) -> dict:
    try:
        return inventory[name]
    except KeyError:
        raise InventoryError(f"El dispositivo '{name}' no existe en el inventario.")
