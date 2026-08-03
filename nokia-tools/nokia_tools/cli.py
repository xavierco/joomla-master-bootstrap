"""CLI para configurar y analizar equipos Nokia SR OS.

Ejemplos:
    python -m nokia_tools configure --device R1 --template example.j2 --vars vars.yaml
    python -m nokia_tools analyze --device R1 --output reports/r1.json
    python -m nokia_tools analyze --all --output reports/fleet.json
"""
import argparse
import json
import logging
import sys

from . import configure as configure_mod
from . import analyze as analyze_mod
from .inventory import load_inventory, get_device, InventoryError
from .connection import ConnectionError_

logger = logging.getLogger("nokia_tools")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nokia_tools", description=__doc__)
    parser.add_argument(
        "--inventory", default="inventory.yaml", help="Ruta al archivo de inventario (default: inventory.yaml)"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Logging en modo debug")

    sub = parser.add_subparsers(dest="action", required=True)

    p_conf = sub.add_parser("configure", help="Renderiza y aplica una plantilla de configuración")
    p_conf.add_argument("--device", required=True, help="Nombre del equipo en el inventario")
    p_conf.add_argument("--template", required=True, help="Nombre del template .j2 (dentro de nokia_tools/templates)")
    p_conf.add_argument("--vars", required=True, help="Archivo YAML con las variables del template")
    p_conf.add_argument("--no-commit", action="store_true", help="No ejecutar commit tras aplicar la config")
    p_conf.add_argument("--dry-run", action="store_true", help="Solo mostrar la configuración renderizada, sin aplicarla")

    p_an = sub.add_parser("analyze", help="Recolecta y resume el estado de uno o varios equipos")
    group = p_an.add_mutually_exclusive_group(required=True)
    group.add_argument("--device", help="Nombre del equipo en el inventario")
    group.add_argument("--all", action="store_true", help="Analizar todos los equipos del inventario")
    p_an.add_argument("--output", help="Ruta de archivo para guardar el reporte en JSON")

    return parser


def cmd_configure(args) -> int:
    inventory = load_inventory(args.inventory)
    device = get_device(inventory, args.device)

    variables = configure_mod.load_vars(args.vars)
    config_lines = configure_mod.render_template(args.template, variables)

    print("Configuración a aplicar:")
    print("\n".join(config_lines))

    if args.dry_run:
        print("\n[dry-run] No se aplicó ningún cambio.")
        return 0

    output = configure_mod.push_config(device, config_lines, do_commit=not args.no_commit)
    print("\nSalida del equipo:")
    print(output)
    return 0


def cmd_analyze(args) -> int:
    inventory = load_inventory(args.inventory)

    if args.device:
        device = get_device(inventory, args.device)
        report = analyze_mod.analyze_device(args.device, device)
    else:
        report = analyze_mod.analyze_fleet(inventory, list(inventory.keys()))

    if args.output:
        analyze_mod.save_report(report, args.output)
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False))

    return 0


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        if args.action == "configure":
            return cmd_configure(args)
        if args.action == "analyze":
            return cmd_analyze(args)
    except (InventoryError, ConnectionError_) as exc:
        logger.error(str(exc))
        return 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
