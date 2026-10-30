
from spotipy.exceptions import SpotifyException
from core.spotify_client import get_spotify_client


def spotify_repeat(parameters=None):
    """Controla o modo de repetição do Spotify."""
    try:
        parameters = parameters or {}

        action = parameters.get("action", "").strip().lower()
        repeat_type = parameters.get("repeat_type", "context").strip().lower()

        sp = get_spotify_client()

        if action in ("status", "consultar", "verificar"):
            playback = sp.current_playback()

            if not playback:
                return "Não existe reprodução ativa no Spotify."

            state = playback.get("repeat_state", "off")

            descriptions = {
                "off": "desativado",
                "track": "repetindo a música atual",
                "context": "repetindo a playlist ou álbum",
            }

            return f"Modo de repetição: {descriptions.get(state, state)}."

        if action in ("desativar", "desligar", "off"):
            state = "off"

        elif action in ("ativar", "ligar", "repetir"):
            if repeat_type not in ("track", "context"):
                return "Tipo inválido. Use track ou context."

            state = repeat_type

        elif action in ("musica", "música"):
            state = "track"

        elif action in ("playlist", "album", "álbum"):
            state = "context"

        else:
            return (
                "Informe se deseja ativar, desativar ou consultar "
                "o modo de repetição."
            )

        sp.repeat(state=state)

        descriptions = {
            "off": "desativado",
            "track": "repetição da música atual ativada",
            "context": "repetição da playlist ou álbum ativada",
        }

        return f"Modo de repetição {descriptions[state]}."

    except SpotifyException as e:
        if e.http_status == 403:
            return "O Spotify não autorizou a alteração do modo de repetição."
        return f"Erro do Spotify ao alterar a repetição: {e}"

    except Exception as e:
        return f"Não consegui alterar o modo de repetição: {e}"


TOOL = {
    "name": "spotify_repeat",
    "description": (
        "Controla o modo de repetição do Spotify. "
        "Use para ativar, desativar ou consultar a repetição. "
        "Se o usuário pedir para repetir a música atual, use "
        "action='ativar' e repeat_type='track'. "
        "Se pedir para repetir a playlist ou álbum, use "
        "action='ativar' e repeat_type='context'. "
        "Se pedir apenas para ativar a repetição sem especificar, "
        "use repeat_type='context'. "
        "Para desativar, use action='desativar'. "
        "Para consultar, use action='status'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "ativar, desativar ou status."
            },
            "repeat_type": {
                "type": "STRING",
                "description": "track para música ou context para playlist."
            }
        },
        "required": ["action"]
    },
    "handler": spotify_repeat,
}
