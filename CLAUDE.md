# RF Devices — guía para Claude

Integración personalizada de Home Assistant (HACS), dominio `rf_devices`. Crea dispositivos RF (luces,
interruptores, ventiladores con luz, persianas, botoneras) capturando los códigos desde un panel visual,
y controla relés (Shelly…) y los interruptores de pared de cada dispositivo.

Este archivo es **público**. El contexto privado de la instalación del mantenedor (IP, entidades de su
casa, tramas reales) vive en `CLAUDE.local.md` / `.internal/`, que no están en el repositorio: nunca lo
copies aquí ni a código, tests, issues o PRs.

## Ramas y versiones

- `main`: versión estable, la que instala HACS. Releases `vX.Y.Z`.
- `labs`: hardware experimental que el mantenedor **no tiene** (ESPHome `radio_frequency`, ESP32 + CC1101,
  IoTorero, Somfy RTS). Pre-releases `vX.Y.Z-labs.N`. No se fusiona con `main` salvo que lo pida el mantenedor.
- Cambios: rama nueva desde la rama correspondiente → PR contra esa misma rama.
- Versión en **dos sitios** que deben coincidir: `manifest.json` → `version` y `const.py` → `VERSION`.
  Cada versión añade su sección arriba en `CHANGELOG.md` (`## X.Y.Z`), en inglés.
- Publicar = hacer push de un tag `vX.Y.Z` (o `vX.Y.Z-labs.N`): `release.yml` comprueba las versiones y
  crea la release (pre-release si lleva `-`) con las notas del CHANGELOG. Solo cuando el mantenedor lo pida.

## Comandos

```bash
uv venv -p 3.14 .venv
uv pip install -p .venv/bin/python pytest-homeassistant-custom-component broadlink==0.19.0 ruff
.venv/bin/pytest -q
.venv/bin/ruff check custom_components tests --select E,F,W,I,B,UP --ignore E501
node --check custom_components/rf_devices/frontend/rf-devices-panel.js
```

Ejecuta tests y ruff antes de dar un cambio por terminado. La CI (`tests.yml`, `validate.yml` con hassfest
y HACS) corre en cada PR.

## Estructura (`custom_components/rf_devices/`)

- `__init__.py` setup: store, hub, relés, gestos de pared, panel y servicios.
- `const.py` constantes, roles, `VERSION`. `models.py` esquemas voluptuous, roles y `entity_plan`.
- `codec.py` decodificar, analizar, limpiar, huella y `hold` de paquetes Broadlink.
- `store.py` `.storage/rf_devices`, `rev` por dispositivo, exportar/importar.
- `hub.py` cola de envío, aprendizaje con salvaguardas, salud del Broadlink.
- `entity.py`, `onoff.py`, `light.py`, `fan.py`, `cover.py`, `switch.py`, `button.py`, `select.py`,
  `sensor.py`, `binary_sensor.py`: entidades.
- `calibration.py` (calibración por consumo y alineador de estado), `meter.py` (lectura en directo).
- `relay.py` + `relays/` (adaptadores base, genérico, Shelly), `wall.py` (gestos del interruptor de pared).
- `websocket_api.py` comandos del panel (todos exigen administrador). `services.py` servicios.
- `frontend/rf-devices-panel.js` panel: web component **sin compilación**.
- Solo en `labs`: `transmitters/`, `protocols/somfy.py`, `listen.py` (seguir el mando), `debug.py`,
  `docs/esphome/*.yaml`.

## Reglas

- Tests con tramas **sintéticas** o capturas anonimizadas que los usuarios aportan en las issues.
- No uses atributos de clase para `_attr_is_on` / `_attr_has_entity_name`: rompen `cached_property`;
  asígnalos por instancia.
- El guardado del panel usa `rev`: si no coincide, el servidor responde `stale`. Respétalo.
- Broadlink: sondeo de aprendizaje cada 1 s como mínimo y salir siempre del modo aprendizaje.
- Los textos visibles van en `strings.json` y `translations/` (en y es).
- Código, commits, CHANGELOG y PRs en inglés. En issues y discusiones responde en el idioma de quien escribe.

## Issues y hardware de terceros

- El mantenedor no tiene el hardware de las peticiones: pide capturas (exportación del panel,
  `rtl_433 -F json`, `dump: raw` de ESPHome) y el JSON del botón «Diagnóstico». Etiquetas: `needs-capture`,
  `needs-info`, `device-request`, `labs`.
- No prometas compatibilidad sin haberla probado; marca lo que es suposición.
- PRs de terceros: revisa que no metan dependencias nuevas sin motivo, que tengan tests y que no rompan
  la exportación/importación.
