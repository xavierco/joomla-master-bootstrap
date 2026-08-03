"""Recolección de estado y análisis básico de equipos Nokia SR OS."""
import json
import logging
import re
from pathlib import Path

from .connection import connect

logger = logging.getLogger(__name__)

# Comandos "show" por defecto (CLI clásica de SR OS).
DEFAULT_COMMANDS = [
    "show system information",
    "show port",
    "show router interface",
    "show system cpu",
]

# Patrones típicos de problemas en la salida de "show port".
PORT_ISSUE_PATTERN = re.compile(r"\b(Down|Failed|Fault)\b", re.IGNORECASE)


def collect(device: dict, commands: list[str] | None = None) -> dict:
    """Ejecuta los comandos show indicados y devuelve {comando: salida_cruda}."""
    commands = commands or DEFAULT_COMMANDS
    raw: dict[str, str] = {}

    with connect(device) as conn:
        for cmd in commands:
            logger.info("Ejecutando '%s' en %s", cmd, device["host"])
            raw[cmd] = conn.send_command(cmd)

    return raw


def parse_system_information(raw: str) -> dict:
    """Extrae los campos más relevantes de 'show system information'."""
    fields = {
        "system_name": r"System Name\s*:\s*(.+)",
        "system_type": r"System Type\s*:\s*(.+)",
        "system_version": r"System Version\s*:\s*(.+)",
        "system_up_time": r"System Up Time\s*:\s*(.+)",
    }
    parsed = {}
    for key, pattern in fields.items():
        match = re.search(pattern, raw)
        parsed[key] = match.group(1).strip() if match else None
    return parsed


def find_port_issues(raw: str) -> list[str]:
    """Devuelve las líneas de 'show port' que reportan estado anómalo."""
    return [line.strip() for line in raw.splitlines() if PORT_ISSUE_PATTERN.search(line)]


def analyze_device(device_name: str, device: dict, commands: list[str] | None = None) -> dict:
    """Recolecta y resume el estado de un equipo. Devuelve un reporte estructurado."""
    raw = collect(device, commands)

    report: dict = {
        "device": device_name,
        "host": device["host"],
        "raw": raw,
        "summary": {},
        "issues": [],
    }

    if "show system information" in raw:
        report["summary"]["system_information"] = parse_system_information(
            raw["show system information"]
        )

    if "show port" in raw:
        issues = find_port_issues(raw["show port"])
        if issues:
            report["issues"].extend(f"Puerto con estado anómalo: {line}" for line in issues)

    return report


def analyze_fleet(inventory: dict, device_names: list[str], commands: list[str] | None = None) -> list[dict]:
    """Analiza varios equipos del inventario y devuelve la lista de reportes."""
    reports = []
    for name in device_names:
        device = inventory[name]
        try:
            reports.append(analyze_device(name, device, commands))
        except Exception as exc:  # noqa: BLE001 - se registra y se continúa con el resto de la flota
            logger.error("Fallo al analizar '%s': %s", name, exc)
            reports.append({"device": name, "host": device.get("host"), "error": str(exc)})
    return reports


def save_report(report, path: str) -> None:
    """Guarda un reporte (dict o lista de dicts) como JSON."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    logger.info("Reporte guardado en %s", out_path)
