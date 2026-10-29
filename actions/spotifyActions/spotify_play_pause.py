
import time

from core.spotify_client import get_spotify_client
from spotipy.exceptions import SpotifyException


def find_spotify_device(spotify):
    """Localiza um dispositivo disponível, priorizando o PC."""

    for attempt in range(3):
        devices = spotify.devices().get("devices", [])

        available = [
            device for device in devices
            if device.get("id") and not device.get("is_restricted", False)
        ]

        if available:
            # Prioriza o Spotify no computador.
            computer = next(
                (
                    device for device in available
                    if device.get("type") == "Computer"
                ),
                None,
            )

            if computer:
                return computer

            # Se não houver computador, usa o dispositivo ativo.
            active = next(
                (
                    device for device in available
                    if device.get("is_active")
                ),
                None,
            )

            return active or available[0]

        if attempt < 2:
            time.sleep(1)

    return None


def spotify_play_pause(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    command = str(params.get("command", "")).strip().lower()

    aliases = {
        "tocar": "play",
        "play": "play",
        "reproduzir": "play",
        "pausar": "pause",
        "pause": "pause",
        "continuar": "resume",
        "retomar": "resume",
        "resume": "resume",
    }

    command = aliases.get(command, command)

    if command not in {"play", "pause", "resume"}:
        return (
            "Comando inválido. Informe play para iniciar, "
            "pause para pausar ou resume para retomar."
        )

    try:
        spotify = get_spotify_client()
        device = find_spotify_device(spotify)

        if not device:
            return (
                "Não encontrei dispositivos Spotify disponíveis. "
                "Abra o Spotify no computador, aguarde alguns segundos "
                "e tente novamente."
            )

        device_id = device["id"]
        device_name = device.get("name", "dispositivo desconhecido")

        if command == "pause":
            spotify.pause_playback(device_id=device_id)
            return f"Solicitação para pausar enviada ao Spotify em {device_name}."

        # Informa explicitamente qual dispositivo deve reproduzir.
        spotify.start_playback(device_id=device_id)

        return (
            f"Solicitação para iniciar ou retomar a reprodução "
            f"enviada ao Spotify em {device_name}."
        )

    except SpotifyException as e:
        status = getattr(e, "http_status", None)

        if status == 404:
            return (
                "O Spotify não conseguiu iniciar a reprodução nesse "
                "dispositivo. Verifique se o aplicativo terminou de "
                "abrir e tente novamente."
            )

        if status == 403:
            return (
                "O Spotify recusou o comando. Verifique as permissões "
                "da conta e a disponibilidade do recurso."
            )

        return f"Erro da API do Spotify (HTTP {status}): {e}"

    except Exception as e:
        return f"Erro ao controlar o Spotify: {e}"


TOOL = {
    "name": "spotify_play_pause",
    "description": (
        "Controla a reprodução atual do Spotify. Localiza dispositivos "
        "disponíveis e prioriza o Spotify do computador, mesmo quando "
        "ele não é o dispositivo ativo. Usa o identificador explícito "
        "do dispositivo ao iniciar, retomar ou pausar a reprodução. "
        "Use command='play' para iniciar, command='pause' para pausar "
        "e command='resume' para retomar. Não pesquisa nem seleciona "
        "músicas específicas. Informe erros sem afirmar que a reprodução "
        "começou quando isso não foi confirmado."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "command": {
                "type": "STRING",
                "enum": ["play", "pause", "resume"],
                "description": (
                    "Ação desejada: play para iniciar, "
                    "pause para pausar ou resume para retomar."
                ),
            }
        },
        "required": ["command"],
    },
    "handler": spotify_play_pause,
}
