# Diseño: script de assessment de configuración Nokia SR OS (comparación de pares)

**Fecha:** 2026-08-03
**Estado:** aprobado por usuario, pendiente de implementación

## Objetivo

Un único script Python (`nokia-tools/nokia_compare.py`) que se conecta por SSH a 4 equipos Nokia SR OS —dos pares redundantes— y genera un reporte en Excel señalando las diferencias de configuración entre cada par, para validar que los equipos de respaldo estén alineados con el primario.

Pares objetivo (definidos en `pairs.yaml`, sin credenciales):

| Par | Equipo A | Equipo B |
|---|---|---|
| RDC | 080000-RDC01-7s-SANTAFE — 10.155.98.160 | 080000-RDC02-7s-SANTAFE — 10.155.98.161 |
| RTB | 080000-RTB01-SANTAFE — 10.155.108.214 | 080000-RTB02-SANTAFE — 10.155.108.215 |

## Alcance

- **Un solo archivo Python**, standalone (no se integra al paquete `nokia_tools/` existente), con funciones bien separadas y comentado donde ayude a la lectura.
- Dos modos de comparación, seleccionables por parámetro `--mode {policy,full,both}` (default `both`):
  - **`policy`**: compara únicamente el bloque `configure policy-options` de cada equipo (prefix-lists, community-lists, route-policy).
  - **`full`**: compara la configuración completa (`admin display-config`), normalizando antes los campos que sabemos que deben diferir: `system name` (hostname) y las IPs configuradas en interfaces (`address <ip>/<mask>`). Todo lo demás —incluyendo BGP, OSPF, IS-IS, QoS, etc.— se compara tal cual.
- Diff línea por línea, etiquetando cada diferencia con: tipo (`Solo en A` / `Solo en B` / `Distinto`), contexto jerárquico (derivado de la indentación del `display-config`, ej. `router "Base" > bgp > group "PEERS"`), línea del equipo A, línea del equipo B.
- Reporte de salida en **Excel (.xlsx)**, pensado para que se entienda fácil a simple vista:
  - Hoja **Resumen**: par, modo, cantidad de diferencias, timestamp de la corrida, y equipos no accesibles (si hubo fallas de conexión).
  - Una hoja por combinación par+modo (ej. `RDC_policy`, `RDC_full`, `RTB_policy`, `RTB_full`), con columnas: Contexto, Tipo, Línea Equipo A, Línea Equipo B.
- Credenciales SSH: el script pregunta usuario y contraseña **una sola vez** por consola (con `getpass`, sin eco), y las usa para los 4 equipos.

## Fuera de alcance (por ahora)

- Parser estructural completo de la config SR OS (árbol tipo YANG). Se usa diff de líneas con normalización; si en la práctica no alcanza, se revisa después.
- Push/edición de configuración (eso ya existe en `nokia-tools/nokia_tools/configure.py`, no se toca).
- Guardar credenciales en disco.

## Flujo

1. `python3 nokia_compare.py --pairs pairs.yaml --mode both --output reportes/assessment.xlsx`
2. Prompt de usuario/contraseña (una vez).
3. Por cada uno de los 4 equipos: conexión SSH (Netmiko, `device_type=nokia_sros`), ejecuta `admin display-config` con `read_timeout` alto. Si falla la conexión o el login, se registra el error y se continúa con los demás equipos (no aborta la corrida completa).
4. Por cada par con ambos equipos accesibles:
   - Modo `policy`: extrae el bloque `policy-options` de cada config (por indentación) y hace diff.
   - Modo `full`: normaliza `system name` y las IPs de interfaz (reemplazo por placeholder) en ambas configs, y hace diff de todo el resto.
   - Cada línea distinta se etiqueta con contexto jerárquico, tipo de diferencia, y las dos líneas comparadas.
5. Se genera el Excel con hoja Resumen + una hoja por par/modo.
6. Si un par tiene algún equipo no accesible, se omite su diff y queda anotado en Resumen (no rompe el resto de la corrida).

## Manejo de errores

- Timeout/fallo de login en un equipo → no aborta el script; ese equipo se marca "no accesible" en Resumen y su(s) par(es) se omiten del diff, con nota explicando por qué.
- Password vacío o cancelado (Ctrl+C) → error claro, sin intentar conectar a nada.
- `admin display-config` vacío o con salida irregular → se reporta como error para ese equipo en vez de compararlo silenciosamente contra texto vacío.

## Testing

Tests con texto de configuración de ejemplo (sin equipos reales), cubriendo:
- Extracción del bloque `policy-options` por indentación.
- Normalización de `system name` e IPs de interfaz.
- Construcción del contexto jerárquico a partir de la indentación.
- Generación correcta de filas de diferencia (Solo en A / Solo en B / Distinto).
