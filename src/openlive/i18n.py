"""Tiny i18n: English by default, Spanish when the locale (or config/flag) says so.

Strings in the code are English; `t()` swaps them for the Spanish entry in ES when LANG == "es".
"""
import locale
import os

from . import config

SUPPORTED = ("en", "es")


def detect():
    v = os.environ.get("OPENLIVE_LANG") or config.CONFIG.get("lang")
    if not v:
        for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
            if os.environ.get(var):
                v = os.environ[var]
                break
    if not v:
        try:
            v = locale.getlocale()[0] or ""
        except ValueError:
            v = ""
    v = (v or "en").lower()[:2]
    return v if v in SUPPORTED else "en"


LANG = detect()


def set_lang(lang):
    global LANG
    LANG = lang if lang in SUPPORTED else "en"


def t(s, **kw):
    if LANG == "es":
        s = ES.get(s, s)
    return s.format(**kw) if kw else s


ES = {
    # cli
    "Who you watch is live on Twitch, Kick and YouTube, in the terminal.": "Quién de los que ves está en directo en Twitch, Kick y YouTube, en la terminal.",
    "print who is live and exit, no TUI": "muestra quién está en directo y sale, sin TUI",
    "explore with made-up channels (reads nothing, writes nothing)": "prueba con canales inventados (no lee ni escribe nada)",
    "interface language": "idioma de la interfaz",
    "Nobody you follow is live right now.": "Ninguno de los canales que sigues está en directo ahora.",
    "error": "error",
    # login
    "Signed in as {login}": "Sesión iniciada como {login}",
    "The code expired. Try again.": "El código ha caducado. Vuelve a intentarlo.",
    "Sign in with Twitch": "Inicia sesión con Twitch",
    "openlive only asks to read who you follow. It can't chat, follow or change anything.": "openlive solo pide leer a quién sigues. No puede escribir en el chat, seguir canales ni cambiar nada.",
    "1. Open the link (o) and log in to Twitch if asked.": "1. Abre el enlace (o) e inicia sesión en Twitch si te lo pide.",
    "2. Check that this code matches and press Activate:": "2. Comprueba que el código coincide y pulsa Activar:",
    "Getting a code…": "Pidiendo un código…",
    "Waiting for you to authorise on Twitch…": "Esperando a que autorices en Twitch…",
    "Couldn't reach Twitch: {err}": "No se pudo conectar con Twitch: {err}",
    "Sign-in failed: {err}. Press Cancel and try again.": "Falló el inicio de sesión: {err}. Pulsa Cancelar y vuelve a intentarlo.",
    "No Twitch Client ID set. Create a Public app at {url} and put its Client ID in the config file as client_id.": "No hay Client ID de Twitch. Crea una app de tipo Public en {url} y pon su Client ID en el fichero de configuración como client_id.",
    "Cancel": "Cancelar",
    "Copy link": "Copiar enlace",
    "Open Twitch": "Abrir Twitch",
    "Copied to the clipboard": "Copiado al portapapeles",
    # tui
    "Live": "En directo",
    "Following": "Siguiendo",
    "Browse": "Explorar",
    "Search": "Buscar",
    "Channel": "Canal",
    "Category": "Categoría",
    "Viewers": "Espect.",
    "Uptime": "Tiempo",
    "Title": "Título",
    "offline": "offline",
    "live": "en directo",
    "viewers": "espectadores",
    "for {time}": "desde hace {time}",
    "Quit": "Salir",
    "Watch": "Ver",
    "Open on Twitch": "Abrir en Twitch",
    "Chat": "Chat",
    "Favourite": "Favorito",
    "Refresh": "Recargar",
    "Refresh now": "Recargar ahora",
    "Sign in": "Iniciar sesión",
    "Sign out": "Cerrar sesión",
    "{n} live now": "{n} en directo",
    "demo data": "datos de demo",
    "not signed in · press l": "sin sesión · pulsa l",
    "loading…": "cargando…",
    "Loading…": "Cargando…",
    "filter by channel, game or title": "filtra por canal, categoría o título",
    "search any channel or game on Twitch, then Enter": "busca cualquier canal o juego en Twitch y pulsa Enter",
    "Nothing matches the filter.": "Nada coincide con el filtro.",
    "Sign in with Twitch to see who you follow (press l).": "Inicia sesión con Twitch para ver a quién sigues (pulsa l).",
    "Nobody you follow is live right now. Browse (3) shows the top streams.": "Ninguno de los canales que sigues está en directo. Explorar (3) muestra los directos más vistos.",
    "You don't follow any channel yet.": "Todavía no sigues ningún canal.",
    "No streams found.": "No se encontraron directos.",
    "Type a channel or game above and press Enter.": "Escribe un canal o un juego arriba y pulsa Enter.",
    "↑↓ move · Enter watch · o open on Twitch · c chat · f favourite · click a header to sort": "↑↓ moverse · Enter ver · o abrir en Twitch · c chat · f favorito · clic en una cabecera para ordenar",
    "Enter opens the channel on Twitch.": "Enter abre el canal en Twitch.",
    "Demo mode: nothing to refresh.": "Modo demo: no hay nada que recargar.",
    "Demo mode: would open {name} in your player.": "Modo demo: aquí se abriría {name} en tu reproductor.",
    "Opening {name}…": "Abriendo {name}…",
    "streamlink isn't installed. Reinstall openlive or run: pipx install streamlink": "streamlink no está instalado. Reinstala openlive o ejecuta: pipx install streamlink",
    "No video player found. Install mpv (https://mpv.io), IINA or VLC, or set player in the config.": "No se encontró ningún reproductor. Instala mpv (https://mpv.io), IINA o VLC, o configura player en el fichero de configuración.",
    # platforms
    "Twitch: not signed in. Open openlive and press l to sign in.": "Twitch: sin sesión. Abre openlive y pulsa l para entrar.",
    "Add": "Añadir",
    "Add Kick or YouTube channels": "Añadir canales de Kick o YouTube",
    "Add channels": "Añadir canales",
    "Add the Kick / YouTube channels you watch with a.": "Añade con la tecla a los canales de Kick / YouTube que ves.",
    "Added {n}: {names}": "Añadidos {n}: {names}",
    "Browser": "Navegador",
    "Channel name or link. Several at once: separate them with commas.": "Nombre o enlace del canal. Para añadir varios, sepáralos con comas.",
    "Checking…": "Comprobando…",
    "Choose platforms": "Elegir plataformas",
    "Close": "Cerrar",
    "Couldn't add: {items}": "No se pudo añadir: {items}",
    "Demo mode: nothing to remove.": "Modo demo: no hay nada que quitar.",
    "Enter opens the channel in the browser.": "Enter abre el canal en el navegador.",
    "In Takeout pick only YouTube → subscriptions, export, unzip, then paste the path of subscriptions.csv here.": "En Takeout marca solo YouTube → suscripciones, exporta, descomprime y pega aquí la ruta de subscriptions.csv.",
    "Kick and YouTube don't share who you follow, so openlive keeps its own list.": "Kick y YouTube no dicen a quién sigues, así que openlive guarda su propia lista.",
    "No channels yet. Follow some on Twitch, or press a to add Kick / YouTube channels.": "Todavía no hay canales. Sigue alguno en Twitch o pulsa a para añadir canales de Kick / YouTube.",
    "Nobody on your lists is live right now.": "Ningún canal de tus listas está en directo ahora.",
    "Nobody you follow is live right now. Browse (3) shows the top streams on Twitch.": "Ninguno de tus canales está en directo. Explorar (3) muestra los directos más vistos de Twitch.",
    "Nothing matches the filter, or its platform is hidden.": "Nada coincide con el filtro, o su plataforma está oculta.",
    "Nothing new added.": "No se añadió nada nuevo.",
    "Open Takeout": "Abrir Takeout",
    "Or import your YouTube subscriptions: path to subscriptions.csv from Google Takeout": "O importa tus suscripciones de YouTube: ruta a subscriptions.csv de Google Takeout",
    "Pick at least one platform.": "Elige al menos una plataforma.",
    "Platforms": "Plataformas",
    "Remove": "Quitar",
    "Removed {name} from your {platform} list.": "{name} quitado de tu lista de {platform}.",
    "Save": "Guardar",
    "Search needs a Twitch sign-in": "Buscar necesita la sesión de Twitch",
    "Sign in with Twitch (l) or add Kick / YouTube channels (a).": "Inicia sesión en Twitch (l) o añade canales de Kick / YouTube (a).",
    "Sign out of Twitch": "Cerrar sesión de Twitch",
    "This tab needs a Twitch sign-in (press l).": "Esta pestaña necesita la sesión de Twitch (pulsa l).",
    "Twitch: not signed in · l": "Twitch: sin sesión · l",
    "Which platforms do you watch?": "¿Qué plataformas ves?",
    "You can change this any time with the p key.": "Puedes cambiarlo cuando quieras con la tecla p.",
    "add the channels you watch (no sign-in)": "añade los canales que ves (sin iniciar sesión)",
    "press {key} to show or hide": "pulsa {key} para mostrar u ocultar",
    "sign in once; your follows come from your account": "inicias sesión una vez; tus seguidos salen de tu cuenta",
    "x removes it from your list.": "x lo quita de tu lista.",
    "{n} channel(s) couldn't be read": "{n} canal(es) no se pudieron leer",
    "↑↓ move · Enter watch · o open in browser · c chat · f favourite · a add channel · click a header to sort": "↑↓ moverse · Enter ver · o abrir en el navegador · c chat · f favorito · a añadir canal · clic en una cabecera para ordenar",
    "e.g. @LofiGirl, youtube.com/@mkbhd": "p. ej. @LofiGirl, youtube.com/@mkbhd",
    "e.g. xqc, kick.com/trainwreckstv": "p. ej. xqc, kick.com/trainwreckstv",
    "Kick doesn't share who you follow, so openlive keeps its own list.": "Kick no dice a quién sigues, así que openlive guarda su propia lista.",
    "Signed in with Google, your subscriptions come on their own. Here you can add others.": "Con la sesión de Google, tus suscripciones salen solas. Aquí puedes añadir otros canales.",
    "Type a channel name: results show up as you type.": "Escribe el nombre de un canal: los resultados salen mientras escribes.",
    "↑↓ pick · Enter add · Esc close": "↑↓ elegir · Enter añadir · Esc cerrar",
    "followers": "seguidores",
    "added": "añadido",
    "{name} is already on your list.": "{name} ya está en tu lista.",
    # player
    "Back 10 s": "Atrás 10 s",
    "Forward 10 s": "Adelante 10 s",
    "Back to live": "Volver al directo",
    "Going back…": "Retrocediendo…",
    "This stream can't go back further.": "Este directo no deja retroceder más.",
    "← → 10 s · Shift ← → 5 min · End back to live": "← → 10 s · Mayús ← → 5 min · Fin vuelve al directo",
    # google
    "Sign in with Google": "Inicia sesión con Google",
    "For your YouTube subscriptions. openlive only asks to read them: it can't comment, subscribe or change anything.": "Para tus suscripciones de YouTube. openlive solo pide leerlas: no puede comentar, suscribirse ni cambiar nada.",
    "1. Open the link (o) and choose your YouTube account.": "1. Abre el enlace (o) y elige tu cuenta de YouTube.",
    "2. Type this code there and allow access:": "2. Escribe allí este código y permite el acceso:",
    "Open Google": "Abrir Google",
    "Waiting for you to allow access on Google…": "Esperando a que permitas el acceso en Google…",
    "Couldn't reach Google: {err}": "No se pudo conectar con Google: {err}",
    "Skip": "Omitir",
    "Sign in with Google (YouTube subscriptions)": "Iniciar sesión con Google (suscripciones de YouTube)",
    "Sign out of Google": "Cerrar sesión de Google",
    "YouTube: sign in · g": "YouTube: inicia sesión · g",
    "Sign in with Google (g) to bring your subscriptions, or add channels here.": "Inicia sesión con Google (g) para traer tus suscripciones, o añade canales aquí.",
    "live only; sign in with Google for your subscriptions": "solo directos; inicia sesión con Google para tus suscripciones",
    "Your YouTube channels come from your Google subscriptions.": "Tus canales de YouTube salen de tus suscripciones de Google.",
    "That channel comes from your YouTube subscriptions.": "Ese canal viene de tus suscripciones de YouTube.",
}
