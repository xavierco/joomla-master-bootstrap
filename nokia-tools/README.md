# nokia-tools

Herramienta en Python para **configurar y analizar** equipos Nokia SR OS (series 7750/7450/7250, etc.) vía SSH, usando [Netmiko](https://github.com/ktbyers/netmiko).

## Instalación

```bash
cd nokia-tools
pip install -r requirements.txt
```

## Inventario

Copia el ejemplo y completa las credenciales reales (este archivo está en `.gitignore`, nunca lo subas al repo):

```bash
cp inventory.yaml.example inventory.yaml
```

```yaml
devices:
  R1:
    host: 192.0.2.10
    username: admin
    password: "changeme"
    port: 22
    device_type: nokia_sros
```

## Analizar equipos

Recolecta `show system information`, `show port`, `show router interface` y `show system cpu`, y resume el estado (nombre, versión, uptime, puertos con problemas):

```bash
# un solo equipo, imprime JSON por stdout
python -m nokia_tools analyze --device R1

# toda la flota del inventario, guardando el reporte
python -m nokia_tools analyze --all --output reports/fleet.json
```

## Configurar equipos

Las plantillas de configuración viven en `nokia_tools/templates/*.j2` (Jinja2) y las variables en un YAML aparte:

```bash
# ver la config renderizada sin aplicarla
python -m nokia_tools configure --device R1 --template example.j2 --vars example_vars.yaml --dry-run

# aplicarla de verdad (hace commit automáticamente al final)
python -m nokia_tools configure --device R1 --template example.j2 --vars example_vars.yaml
```

Usa `--no-commit` si querés dejar los cambios pendientes de commit manual en el equipo.

## Estructura

```
nokia-tools/
├── inventory.yaml.example   # plantilla de inventario (copiar a inventory.yaml)
├── example_vars.yaml        # variables de ejemplo para el template
├── requirements.txt
├── nokia_tools/
│   ├── cli.py            # entry point (subcomandos configure / analyze)
│   ├── inventory.py      # carga del inventario YAML
│   ├── connection.py     # apertura de sesión SSH (Netmiko, device_type nokia_sros)
│   ├── configure.py      # renderizado Jinja2 + push de configuración
│   ├── analyze.py        # recolección de show commands + parsing + reporte
│   └── templates/
│       └── example.j2    # plantilla de ejemplo (system name + loopback)
└── tests/
    └── test_analyze.py   # tests del parser, sin necesidad de un equipo real
```

## Tests

```bash
python -m pytest tests/
```

## Próximos pasos sugeridos

- Agregar más plantillas (BGP, interfaces físicas, QoS, etc.) según las necesidades reales.
- Ampliar `analyze.py` con más comandos `show` y parsers (BGP summary, alarmas, LLDP).
- Soporte opcional para NETCONF/YANG si se necesita algo más estructurado que CLI.
- Manejo de secretos vía variables de entorno o un vault en vez de texto plano en `inventory.yaml`.
