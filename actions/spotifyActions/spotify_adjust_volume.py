
from spotipy.exceptions import SpotifyException
from core.spotify_client import get_spotify_client


def spotify_adjust_volume(parameters=None):
    """Ajusta o volume do Spotify de maneira relativa."""
    try:
        parameters = parameters or {}

        direction = parameters.get("direction")
        amount = parameters.get("amount", 10)

        if direction not in ("up", "down"):
            return "Informe se deseja aumentar ou diminuir o volume."

        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            return "Informe uma quantidade válida para ajustar o volume."

        sp = get_spotify_client()
        playback = sp.current_playback()

        if not playback:
            return "Não há reprodução ativa no Spotify."

        device = playback.get("device")

        if not device:
            return "Não consegui identificar o dispositivo de reprodução."

        current_volume = device.get("volume_percent")

        if current_volume is None:
            return "Não consegui consultar o volume atual."

        if direction == "up":
            new_volume = min(100, current_volume + amount)
        else:
            new_volume = max(0, current_volume - amount)

        sp.volume(new_volume)

        return f"Volume ajustado para {new_volume}%."

    except SpotifyException as e:
        return f"Erro ao ajustar volume: {e}"
    except Exception as e:
        return f"Não consegui ajustar o volume: {e}"


TOOL = {
    "name": "spotify_adjust_volume",
    "description": (
        "Ajusta o volume do Spotify relativamente ao volume atual. "
        "Use direction='up' para aumentar e direction='down' para diminuir. "
        "Use amount=10 para um ajuste pequeno e amount=20 para um ajuste maior. "
        "Para aumentar ao máximo use amount=100 com direction='up'. "
        "Para diminuir ao mínimo use amount=100 com direction='down'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "direction": {
                "type": "STRING",
                "enum": ["up", "down"],
                "description": "Direção do ajuste."
            },
            "amount": {
                "type": "INTEGER",
                "description": "Quantidade de pontos percentuais do ajuste."
            }
        },
        "required": ["direction"]
    },
    "handler": spotify_adjust_volume,
}
