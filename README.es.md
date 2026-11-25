# openlive

**¿Quién de los que sigues está en directo ahora?** `openlive` es un panel en la terminal con los canales de Twitch que sigues y que están emitiendo en este momento. Eliges uno y se abre en tu propio reproductor (mpv, IINA o VLC), no en una pestaña del navegador.

Funciona en tu ordenador y solo habla con Twitch. Para entrar no hacen falta claves, solo un código: abres twitch.tv/activate, compruebas el código y pulsas Activar.

[English](README.md)

![demo de openlive](docs/demo.gif)

## Funciones

- **Lo que está en directo, primero.** Los canales que sigues y están emitiendo, con categoría, espectadores, tiempo en directo y título. Se actualiza solo cada minuto.
- **Sin navegador.** `Enter` abre el directo con streamlink en mpv, IINA o VLC, con baja latencia. `o` abre el canal en Twitch y `c` saca su chat en una ventana.
- **Siguiendo, Explorar y Buscar.** Todos los canales que sigues (primero los que están en directo), los directos más vistos de Twitch y un buscador de canales o juegos.
- **Favoritos arriba.** `f` fija un canal arriba en todas las listas.
- **Entras una vez y sin claves.** Ni cuenta de desarrollador, ni Client ID, ni secretos que copiar. El token se guarda solo en tu ordenador y se renueva solo.
- **Ratón y teclado.** Clic en una cabecera para ordenar, `/` para filtrar. Funciona desde 80 columnas.
- **Inglés y español.**

| Siguiendo | Explorar |
|---|---|
| ![Siguiendo](docs/screenshots/following.svg) | ![Explorar](docs/screenshots/browse.svg) |

## Instalación

Necesitas Python 3.11+ y un reproductor: [mpv](https://mpv.io) (recomendado), [IINA](https://iina.io) en macOS o [VLC](https://www.videolan.org/vlc/). streamlink se instala junto con openlive.

```bash
pipx install openlive        # o: uv tool install openlive
openlive
```

En macOS, `brew install mpv` te instala un reproductor.

Pruébalo sin cuenta de Twitch. La demo usa canales inventados y no lee ni escribe nada:

```bash
openlive --demo
```

Desde el código:

```bash
git clone https://github.com/xlydevs/openlive && cd openlive
uv venv && uv pip install -e ".[dev]"
.venv/bin/openlive
```

## Uso

```text
openlive               abre el panel (la primera vez te pide iniciar sesión)
openlive <canal>       ve un canal directamente
openlive --text        muestra quién está en directo y sale (también al usar tuberías: openlive | less)
openlive --login       inicia sesión desde la terminal, sin el panel
openlive --logout      cierra la sesión y borra el token guardado
openlive --demo        canales inventados
openlive --lang en     idioma de la interfaz (por defecto: el del sistema)
```

**Teclas:**
- `1`–`4` cambian de pestaña: En directo, Siguiendo, Explorar, Buscar.
- `↑`/`↓` moverse, `Enter` ver (los canales offline se abren en Twitch).
- `o` abrir en Twitch, `c` chat, `f` favorito.
- `/` filtrar la lista (en Buscar: escribe un canal o juego y pulsa `Enter`), `Esc` borrar el filtro.
- `r` recargar, `l` iniciar sesión, `Ctrl+P` paleta de comandos (ahí está cerrar sesión), `q` salir.
- Clic en la cabecera de una columna para ordenar; otro clic invierte el orden.

## Cómo funciona

openlive inicia sesión con el [flujo de código de dispositivo](https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/#device-code-grant-flow) de Twitch. Pide un único permiso, `user:read:follows`, para leer a quién sigues y nada más. No puede escribir en el chat, seguir canales ni cambiar nada de tu cuenta.

| Qué | De dónde sale |
|---|---|
| En directo | Helix `streams/followed` |
| Siguiendo | Helix `channels/followed` más quién está en directo |
| Explorar | Helix `streams` (los más vistos; `browse_language` los filtra) |
| Buscar | Helix `search/channels` |
| Reproducción | `streamlink https://twitch.tv/<canal> best --player <el tuyo>` |

Ficheros que guarda:

| Fichero | Qué |
|---|---|
| `~/.config/openlive/config.toml` | ajustes opcionales: reproductor, calidad, idioma… mira [config.example.toml](config.example.toml) |
| `~/.local/share/openlive/auth.json` | tu token de sesión (solo lo puedes leer tú) |
| `~/.local/share/openlive/favourites.json` | tus favoritos |
| `~/.local/share/openlive/cache.json` | la última lista de directos, para que abra al instante |

En Windows están en `%APPDATA%\openlive` y `%LOCALAPPDATA%\openlive`. `$OPENLIVE_CONFIG` y `$OPENLIVE_DATA_DIR` los cambian.

**No incluye:** chat dentro de la terminal, VODs ni clips, otras plataformas (YouTube, Kick). Los anuncios y los directos solo para suscriptores funcionan como en streamlink.

**Privacidad:** no se envía nada a ningún sitio salvo a Twitch. Sin analíticas.

## Desarrollo

```bash
uv venv && uv pip install -e ".[dev]"
.venv/bin/python -m pytest -q        # los tests nunca usan la red ni tu token real
uvx ruff check .
.venv/bin/python scripts/screenshots.py   # docs/screenshots/*.svg con datos de demo
vhs scripts/demo.tape                     # docs/demo.gif
```

Usar tu propia app de Twitch: crea una app **Public** en [dev.twitch.tv](https://dev.twitch.tv/console/apps/create) (redirección `http://localhost`) y pon `client_id` en la configuración o en `$OPENLIVE_CLIENT_ID`.

openlive no está afiliado a Twitch ni cuenta con su respaldo.

## Licencia

[MIT](LICENSE)
