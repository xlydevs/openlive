# Privacy policy

*Last updated: 26 November 2026* · [Español](#política-de-privacidad)

openlive is an open-source program that runs on your own computer. It has no server, no accounts of its own and no analytics. The people who make openlive never receive your data.

## What openlive reads

- **Twitch** (if you sign in): your user name and the channels you follow, to show which are live. Scopes: `user:read:follows`, and `user:write:chat` to send chat messages you type yourself.
- **YouTube / Google** (if you sign in): your YouTube subscriptions, to show which channels are live. Scope: `https://www.googleapis.com/auth/youtube.readonly` (read only). openlive never posts, likes, subscribes or changes anything in your Google account.
- **Kick**: only the public pages of the channels you add. No sign-in.

## Where your data goes

Everything stays on your computer: sign-in tokens, your channel lists and settings are saved in openlive's folders in your user account (`~/.local/share/openlive` and `~/.config/openlive`, or `%LOCALAPPDATA%` / `%APPDATA%` on Windows). Token files are readable only by your user where the system allows it.

openlive only talks to Twitch, Kick, YouTube and Google to fetch what it shows, and to GitHub to check for a newer version of openlive. Nothing is sold, shared or sent to anyone else.

## Google user data

openlive's use and transfer of information received from Google APIs adheres to the [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy), including the Limited Use requirements. YouTube data is used only to show you which of your subscriptions are live, inside openlive, on your computer.

## Removing your data

- Sign out in openlive's Settings tab (5): openlive revokes the token and deletes it.
- Revoke access any time at [myaccount.google.com/permissions](https://myaccount.google.com/permissions) (Google) or [twitch.tv/settings/connections](https://www.twitch.tv/settings/connections) (Twitch).
- Uninstall with `uv tool uninstall openlive` and delete the folders above to remove everything.

## Contact

Questions: open an issue at [github.com/xlydevs/openlive/issues](https://github.com/xlydevs/openlive/issues) or write to xlydevs@gmail.com.

---

# Política de privacidad

*Última actualización: 26 de noviembre de 2026*

openlive es un programa de código abierto que se ejecuta en tu propio ordenador. No tiene servidor, ni cuentas propias, ni analíticas. Quienes hacen openlive nunca reciben tus datos.

- **Twitch** (si inicias sesión): tu nombre de usuario y los canales que sigues, para ver cuáles están en directo; y enviar al chat los mensajes que tú escribes.
- **YouTube / Google** (si inicias sesión): tus suscripciones de YouTube, solo lectura (`youtube.readonly`), para ver cuáles están en directo. openlive nunca publica, da me gusta, se suscribe ni cambia nada en tu cuenta.
- **Kick**: solo las páginas públicas de los canales que añades.

Todo se guarda en tu ordenador (tokens, listas de canales y ajustes). openlive solo se conecta a Twitch, Kick, YouTube y Google para obtener lo que muestra, y a GitHub para ver si hay una versión nueva. No se vende, comparte ni envía nada a nadie más. El uso de los datos de las API de Google cumple la [Política de datos de usuario de los servicios de API de Google](https://developers.google.com/terms/api-services-user-data-policy), incluidos los requisitos de Uso Limitado.

Para borrar tus datos: cierra sesión en Ajustes (5), revoca el acceso en [myaccount.google.com/permissions](https://myaccount.google.com/permissions) o en [twitch.tv/settings/connections](https://www.twitch.tv/settings/connections), y desinstala con `uv tool uninstall openlive` borrando las carpetas de openlive.

Contacto: [github.com/xlydevs/openlive/issues](https://github.com/xlydevs/openlive/issues) o xlydevs@gmail.com.
