"""Renderizado de plantillas Jinja2 y aplicación de configuración en equipos Nokia SR OS."""
import logging
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .connection import connect

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"


def render_template(template_name: str, variables: dict) -> list[str]:
    """Renderiza un template .j2 y devuelve la lista de líneas de configuración."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        undefined=StrictUndefined,  # falla si falta una variable, en vez de dejarla vacía
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(template_name)
    rendered = template.render(**variables)
    return [line for line in rendered.splitlines() if line.strip()]


def load_vars(vars_path: str) -> dict:
    with Path(vars_path).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def push_config(device: dict, config_lines: list[str], do_commit: bool = True) -> str:
    """Aplica las líneas de configuración al equipo y devuelve la salida cruda."""
    with connect(device) as conn:
        output = conn.send_config_set(config_lines)
        logger.debug("Salida de configuración:\n%s", output)

        if do_commit:
            try:
                commit_output = conn.commit()
                output += "\n" + commit_output
            except AttributeError:
                # El driver de Netmiko en uso no expone commit() explícito
                # (p.ej. CLI clásica de SR OS, donde los cambios aplican al instante).
                logger.info("El driver no soporta commit() explícito; se asume aplicado.")

        return output
