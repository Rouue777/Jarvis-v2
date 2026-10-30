
from spotipy.exceptions import SpotifyException
from core.spotify_client import get_spotify_client


def spotify_get_shuffle(parameters=None):
    """Consulta se o modo aleatório está ativado no Spotify."""
    try:
        sp = get_spotify_client()
        playback = sp.current_playback()

        if not playback:
            return "Não há reprodução ativa no Spotify para consultar."

        shuffle_state = playback.get("shuffle_state")

        if shuffle_state is True:
            return "O modo aleatório está ativado."
        elif shuffle_state is False:
            return "O modo aleatório está desativado."

        return "Não foi possível identificar o estado do modo aleatório."

    except SpotifyException as e:
        return f"Erro ao consultar modo aleatório: {e}"
    except Exception as e:
        return f"Não consegui consultar o modo aleatório: {e}"


TOOL = {
    "name": "spotify_get_shuffle",
    "description": (
        "Consulta se a reprodução aleatória está ativada ou desativada "
        "no Spotify. Não altera nenhuma configuração. "
        "Use quando o usuário perguntar se está no aleatório, "
        "se a reprodução aleatória está ligada ou desligada."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {},
        "required": []
    },
    "handler": spotify_get_shuffle,
}
