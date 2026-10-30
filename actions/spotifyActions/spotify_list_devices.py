
from spotipy.exceptions import SpotifyException
from core.spotify_client import get_spotify_client


def spotify_list_devices(parameters=None):
    """Lista os dispositivos disponíveis no Spotify."""
    try:
        sp = get_spotify_client()
        response = sp.devices()
        devices = response.get("devices", [])

        if not devices:
            return (
                "Não encontrei dispositivos disponíveis. "
                "Abra o Spotify em um dispositivo e tente novamente."
            )

        linhas = []

        for device in devices:
            nome = device.get("name", "Dispositivo desconhecido")
            tipo = device.get("type", "Desconhecido")
            ativo = device.get("is_active", False)
            volume = device.get("volume_percent")

            status = "Em reprodução" if ativo else "Disponível"

            linhas.append(
                f"{nome} ({tipo}) - {status} - Volume: {volume}%"
                if volume is not None
                else f"{nome} ({tipo}) - {status}"
            )

        return "Dispositivos disponíveis:\n" + "\n".join(linhas)

    except SpotifyException as e:
        return f"Erro ao consultar dispositivos Spotify: {e}"

    except Exception as e:
        return f"Não consegui consultar os dispositivos: {e}"


TOOL = {
    "name": "spotify_list_devices",
    "description": (
        "Lista os dispositivos disponíveis na conta Spotify do usuário. "
        "Use quando ele perguntar onde pode reproduzir música ou quais "
        "dispositivos estão disponíveis."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {},
        "required": [],
    },
    "handler": spotify_list_devices,
}
