
from core.spotify_client import get_spotify_client
from spotipy.exceptions import SpotifyException


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
        "play" : "play",
        "reproduzir": "play",
        "pausar": "pause",
        "continuar": "resume",
        "retomar": "resume",
    }
    command = aliases.get(command, command)

    if command not in {"play", "pause", "resume"}:
        return (
            "Comando inválido. Informe play para iniciar, "
            "pause para pausar ou resume para retomar."
        )

    try:
        spotify = get_spotify_client()

        if command == "pause":
            spotify.pause_playback()
            return "Reprodução do Spotify pausada."

        spotify.start_playback()

        if command == "resume":
            return "Solicitação enviada para retomar a reprodução."

        return "Solicitação enviada para iniciar a reprodução."

    except SpotifyException as e:
        status = getattr(e, "http_status", None)

        if status == 404:
            return (
                "Não foi possível controlar a reprodução. "
                "Verifique se existe um dispositivo Spotify ativo."
            )

        return f"Erro da API do Spotify (HTTP {status}): {e}"

    except Exception as e:
        return f"Erro ao controlar o Spotify: {e}"


TOOL = {
    "name": "spotify_play_pause",
    "description": (
        "Controla a reprodução atual do Spotify usando a conta autenticada "
        "no Jarvis. Use quando o usuário pedir para pausar a música, "
        "parar temporariamente a reprodução, voltar a tocar, continuar "
        "a música ou retomar a reprodução pausada. "
        "Escolha command='pause' para pausar; command='resume' para "
        "retomar; command='play' para iniciar ou retomar a reprodução "
        "atual. Os comandos play e resume utilizam a API de início/"
        "retomada de reprodução. "
        "Esta ferramenta não pesquisa músicas nem seleciona faixas, "
        "álbuns ou playlists específicos. Não a use para pedidos como "
        "'toque [nome da música]'. "
        "Informe o resultado com base na resposta da API e nunca afirme "
        "que a música começou se a operação retornar um erro."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "command": {
                "type": "STRING",
                "enum": ["play", "pause", "resume"],
                "description": (
                    "Ação desejada: play para iniciar a reprodução atual, "
                    "pause para pausar, resume para retomar."
                ),
            }
        },
        "required": ["command"],
    },
    "handler": spotify_play_pause,
}
