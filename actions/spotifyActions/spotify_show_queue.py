
from spotipy.exceptions import SpotifyException
from core.spotify_client import get_spotify_client


def spotify_show_queue(parameters=None):
    """Retorna apenas a próxima música da fila do Spotify."""
    try:
        sp = get_spotify_client()
        queue_data = sp.queue()
        queue = queue_data.get("queue", [])

        if not queue:
            return "Não há próximas músicas na fila do Spotify."

        track = queue[0]
        name = track.get("name", "Música desconhecida")
        artists = ", ".join(
            artist["name"] for artist in track.get("artists", [])
        )

        return f"A próxima música da fila é {name}, de {artists}."

    except Exception as e:
        return f"Não consegui consultar a fila do Spotify: {e}"


TOOL = {
    "name": "spotify_show_queue",
    "description": (
    "Consulta a fila atual do Spotify e informa somente "
    "o nome e o artista da próxima música. "
    "Use esta ferramenta quando o usuário perguntar "
    "qual é a próxima música da fila."
),
    "parameters": {
        "type": "OBJECT",
        "properties": {},
        "required": [],
    },
    "handler": spotify_show_queue,
}
