#!/usr/bin/env python3
"""
nokia_compare.py

Assessment de configuracion para pares de equipos Nokia SR OS.

Se conecta por SSH a los equipos definidos en pairs.yaml, baja
'admin display-config' de cada uno, y compara cada par (ej. RDC01 vs RDC02)
en dos modos posibles:

  - policy: compara solo el bloque 'configure policy-options'
            (prefix-lists, community-lists, route-policy).
  - full:   compara toda la configuracion, normalizando antes el
            'system name' (hostname) y las IPs de interfaz, que sabemos
            que deben diferir entre los equipos de un mismo par.

El resultado se guarda en un Excel (.xlsx) con una hoja Resumen y una
hoja por cada combinacion par + modo.

Uso:
    python3 nokia_compare.py --pairs pairs.yaml --mode both
    python3 nokia_compare.py --pairs pairs.yaml --mode policy --output reportes/rdc.xlsx

Requisitos (ver requirements.txt): netmiko, PyYAML, openpyxl
"""
from __future__ import annotations

import argparse
import difflib
import getpass
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

CONFIG_COMMAND = "admin display-config"
READ_TIMEOUT = 180  # segundos; 'admin display-config' puede ser una salida larga

IP_ADDRESS_LINE_RE = re.compile(
    r'^(?P<prefix>\s*address\s+)(?P<ip>\d{1,3}(?:\.\d{1,3}){3})(?P<mask>(?:/\d{1,2})?)(?P<rest>.*)$'
)
SYSTEM_NAME_LINE_RE = re.compile(r'^(?P<prefix>\s*name\s+")(?P<name>[^"]+)(?P<suffix>")')


# ---------------------------------------------------------------------------
# Inventario de pares (pairs.yaml)
# ---------------------------------------------------------------------------

def load_pairs(path: str) -> list[dict]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(
            f"No se encontro '{path}'. Copia pairs.yaml.example a pairs.yaml y ajustalo."
        )
    with file_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    pairs = data.get("pairs", [])
    if not pairs:
        raise ValueError(f"'{path}' no define ningun par bajo la clave 'pairs:'.")
    return pairs


# ---------------------------------------------------------------------------
# Conexion SSH y recoleccion de configuracion
# ---------------------------------------------------------------------------

def fetch_config(host: str, username: str, password: str, port: int = 22) -> str:
    """Se conecta por SSH a un equipo SR OS y devuelve el texto de 'admin display-config'."""
    conn = ConnectHandler(
        device_type="nokia_sros",
        host=host,
        username=username,
        password=password,
        port=port,
    )
    try:
        return conn.send_command(CONFIG_COMMAND, read_timeout=READ_TIMEOUT)
    finally:
        conn.disconnect()


# ---------------------------------------------------------------------------
# Extraccion de bloques y normalizacion
# ---------------------------------------------------------------------------

def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def extract_block(config_text: str, block_keyword: str) -> list[str]:
    """
    Extrae un bloque top-level de 'admin display-config' (ej. 'policy-options'),
    devolviendo sus lineas internas (sin la linea de apertura ni el 'exit' final).

    Se basa en indentacion: SR OS indenta por niveles y cierra cada bloque
    con un 'exit' (o 'exit all') a la misma indentacion de apertura.
    """
    lines = config_text.splitlines()
    start = None
    block_indent = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == block_keyword or stripped.startswith(block_keyword + " "):
            start = i
            block_indent = _indent_of(line)
            break

    if start is None:
        return []

    block_lines = []
    for line in lines[start + 1:]:
        stripped = line.strip()
        if stripped == "":
            block_lines.append(line)
            continue
        indent = _indent_of(line)
        if indent <= block_indent and stripped in ("exit", "exit all"):
            break
        block_lines.append(line)

    return block_lines


def normalize_full_config(config_text: str) -> list[str]:
    """
    Reemplaza los campos que sabemos de antemano que deben diferir entre los
    dos equipos de un mismo par: el 'system name' (hostname) y las IPs
    configuradas en interfaces (lineas 'address <ip>[/mascara] ...').
    Devuelve la configuracion normalizada como lista de lineas.
    """
    normalized = []
    for line in config_text.splitlines():
        line = SYSTEM_NAME_LINE_RE.sub(lambda m: f'{m.group("prefix")}<SYSTEM_NAME>{m.group("suffix")}', line)

        ip_match = IP_ADDRESS_LINE_RE.match(line)
        if ip_match:
            line = f'{ip_match.group("prefix")}<IP>{ip_match.group("mask")}{ip_match.group("rest")}'

        normalized.append(line)
    return normalized


# ---------------------------------------------------------------------------
# Contexto jerarquico + diff
# ---------------------------------------------------------------------------

def build_contextual_lines(lines: list[str]) -> list[tuple[str, str]]:
    """
    Devuelve una lista de tuplas (contexto, linea) para cada linea no vacia,
    donde 'contexto' es la ruta jerarquica derivada de la indentacion
    (ej. 'router "Base" > bgp > group "PEERS"').
    """
    stack: list[tuple[int, str]] = []  # (indent, label)
    result: list[tuple[str, str]] = []

    for raw_line in lines:
        if not raw_line.strip():
            continue
        indent = _indent_of(raw_line)
        stripped = raw_line.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()

        context = " > ".join(label for _, label in stack)
        result.append((context, stripped))
        stack.append((indent, stripped))

    return result


def diff_lines(context_lines_a: list[tuple[str, str]], context_lines_b: list[tuple[str, str]]) -> list[tuple[str, str, str, str]]:
    """
    Compara dos listas de (contexto, linea) y devuelve las filas de diferencia:
    (contexto, tipo, linea_equipo_a, linea_equipo_b).
    tipo es 'Solo en A', 'Solo en B' o 'Distinto'.
    """
    a_lines = [cl[1] for cl in context_lines_a]
    b_lines = [cl[1] for cl in context_lines_b]

    matcher = difflib.SequenceMatcher(None, a_lines, b_lines, autojunk=False)
    rows: list[tuple[str, str, str, str]] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue

        a_slice = context_lines_a[i1:i2]
        b_slice = context_lines_b[j1:j2]

        if tag == "replace":
            for idx in range(max(len(a_slice), len(b_slice))):
                ctx_a, line_a = a_slice[idx] if idx < len(a_slice) else (None, "")
                ctx_b, line_b = b_slice[idx] if idx < len(b_slice) else (None, "")
                rows.append((ctx_a or ctx_b or "", "Distinto", line_a, line_b))
        elif tag == "delete":
            for ctx_a, line_a in a_slice:
                rows.append((ctx_a, "Solo en A", line_a, ""))
        elif tag == "insert":
            for ctx_b, line_b in b_slice:
                rows.append((ctx_b, "Solo en B", "", line_b))

    return rows


def compare_pair(config_a: str, config_b: str, mode: str) -> list[tuple[str, str, str, str]]:
    """Compara dos configs completas segun el modo ('policy' o 'full')."""
    if mode == "policy":
        lines_a = extract_block(config_a, "policy-options")
        lines_b = extract_block(config_b, "policy-options")
    else:
        lines_a = normalize_full_config(config_a)
        lines_b = normalize_full_config(config_b)

    return diff_lines(build_contextual_lines(lines_a), build_contextual_lines(lines_b))


# ---------------------------------------------------------------------------
# Reporte Excel
# ---------------------------------------------------------------------------

def _style_header(ws, row: int = 1) -> None:
    for cell in ws[row]:
        if cell.value is not None:
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="DDDDDD")


def _autosize_columns(ws, max_width: int = 80) -> None:
    for column_cells in ws.columns:
        length = max((len(str(c.value)) if c.value is not None else 0) for c in column_cells)
        col_letter = get_column_letter(column_cells[0].column)
        ws.column_dimensions[col_letter].width = min(max(length + 2, 10), max_width)


def build_report(
    pairs: list[dict],
    modes: list[str],
    device_configs: dict[str, str | None],
    device_errors: dict[str, str],
    output_path: str,
) -> None:
    wb = Workbook()
    summary_ws = wb.active
    summary_ws.title = "Resumen"
    summary_ws.append([f"Assessment Nokia SR OS - generado {datetime.now():%Y-%m-%d %H:%M:%S}"])
    summary_ws.append([])
    summary_ws.append(["Par", "Modo", "Diferencias", "Equipo A", "Equipo B", "Estado"])
    _style_header(summary_ws, row=3)

    for pair in pairs:
        name = pair["name"]
        dev_a, dev_b = pair["a"], pair["b"]
        err_a = device_errors.get(dev_a["name"])
        err_b = device_errors.get(dev_b["name"])

        if err_a or err_b:
            detalles = []
            if err_a:
                detalles.append(f"{dev_a['name']} no accesible: {err_a}")
            if err_b:
                detalles.append(f"{dev_b['name']} no accesible: {err_b}")
            for mode in modes:
                summary_ws.append([name, mode, "N/A", dev_a["name"], dev_b["name"], "; ".join(detalles)])
            continue

        for mode in modes:
            rows = compare_pair(device_configs[dev_a["name"]], device_configs[dev_b["name"]], mode)

            sheet_name = f"{name}_{mode}"[:31]  # Excel limita nombres de hoja a 31 caracteres
            ws = wb.create_sheet(sheet_name)
            ws.append(["Contexto", "Tipo", f"Linea {dev_a['name']}", f"Linea {dev_b['name']}"])
            _style_header(ws)
            for context, tipo, line_a, line_b in rows:
                ws.append([context, tipo, line_a, line_b])
            _autosize_columns(ws)

            estado = "Sin diferencias" if not rows else "OK"
            summary_ws.append([name, mode, len(rows), dev_a["name"], dev_b["name"], estado])

    _autosize_columns(summary_ws)

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pairs", default="pairs.yaml", help="Archivo YAML con los pares a comparar (default: pairs.yaml)")
    parser.add_argument("--mode", choices=["policy", "full", "both"], default="both", help="Que comparar (default: both)")
    parser.add_argument("--port", type=int, default=22, help="Puerto SSH por defecto (default: 22)")
    parser.add_argument("--output", default=None, help="Ruta del Excel de salida (default: reports/assessment_<timestamp>.xlsx)")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    try:
        pairs = load_pairs(args.pairs)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        username = input("Usuario SSH: ").strip()
        password = getpass.getpass("Password SSH: ")
    except (EOFError, KeyboardInterrupt):
        print("\nCancelado por el usuario.", file=sys.stderr)
        return 1

    if not username or not password:
        print("Error: usuario o password vacios, no se intenta ninguna conexion.", file=sys.stderr)
        return 1

    modes = ["policy", "full"] if args.mode == "both" else [args.mode]

    devices = {}
    for pair in pairs:
        devices[pair["a"]["name"]] = pair["a"]
        devices[pair["b"]["name"]] = pair["b"]

    device_configs: dict[str, str | None] = {}
    device_errors: dict[str, str] = {}

    for name, dev in devices.items():
        print(f"Conectando a {name} ({dev['host']})...")
        try:
            device_configs[name] = fetch_config(
                dev["host"], username, password, dev.get("port", args.port)
            )
        except NetmikoAuthenticationException as exc:
            device_errors[name] = f"fallo de autenticacion ({exc})"
            print(f"  ERROR: {device_errors[name]}", file=sys.stderr)
        except NetmikoTimeoutException as exc:
            device_errors[name] = f"timeout de conexion ({exc})"
            print(f"  ERROR: {device_errors[name]}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 - se registra y se sigue con los demas equipos
            device_errors[name] = str(exc)
            print(f"  ERROR inesperado: {exc}", file=sys.stderr)

    output_path = args.output or f"reports/assessment_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    build_report(pairs, modes, device_configs, device_errors, output_path)

    print(f"\nReporte generado: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
