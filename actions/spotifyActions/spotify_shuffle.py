from spotipy.exceptions import SpotifyException
from core.spotify_client import get_spotify_client


def spotify_shuffle(parameters=None):
    """Ativa ou desativa o modo aleatório do Spotify."""
    try:
        parameters = parameters or {}
        enabled = parameters.get("enabled")

        if not isinstance(enabled, bool):
            return "Informe se deseja ativar ou desativar o modo aleatório."

        sp = get_spotify_client()
        sp.shuffle(state=enabled)

        if enabled:
            return "Modo aleatório ativado."
        return "Modo aleatório desativado."

    except SpotifyException as e:
        return f"Erro ao alterar modo aleatório: {e}"
    except Exception as e:
        return f"Não consegui alterar o modo aleatório: {e}"


TOOL = {
    "name": "spotify_shuffle",
    "description": (
        "Ativa ou desativa a reprodução aleatória no Spotify. "
        "Use enabled=true para ativar e enabled=false para desativar."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "enabled": {
                "type": "BOOLEAN",
                "description": "Define se o modo aleatório deve ficar ativado."
            }
        },
        "required": ["enabled"]
    },
    "handler": spotify_shuffle,
}