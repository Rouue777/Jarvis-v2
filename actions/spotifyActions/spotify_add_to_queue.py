
import time

from spotipy.exceptions import SpotifyException
from core.spotify_client import get_spotify_client
from actions.spotifyActions.spotify_search import search_tracks



def add_to_queue(parameters):
    query = str((parameters or {}).get("query", "")).strip()

    if not query:
        return "Informe o nome da música e, se possível, o artista."

    try:
        spotify = get_spotify_client()

        # Pesquisa e classifica as faixas
        ranked = search_tracks(spotify, query, limit=10)

        if not ranked:
            return f"Não encontrei músicas para: {query}."

        best = ranked[0]

        # Evita adicionar automaticamente resultados pouco compatíveis
        if best["coverage"] < 0.75:
            return (
                f"Não encontrei uma correspondência confiável para "
                f"'{query}'. Informe também o artista."
            )

        track = best["track"]
        track_uri = track.get("uri")

        if not track_uri:
            return "O Spotify não retornou um identificador válido para essa faixa."

        title = track.get("name", "Título desconhecido")
        artists = ", ".join(
            artist.get("name", "Artista desconhecido")
            for artist in track.get("artists", [])
        )

        # Localiza um dispositivo ativo
        device = None

        for attempt in range(3):
            devices = spotify.devices().get("devices", [])
            active_devices = [
                d for d in devices
                if d.get("is_active") and not d.get("is_restricted")
            ]

            if active_devices:
                device = next(
                    (d for d in active_devices if d.get("type") == "Computer"),
                    active_devices[0]
                )
                break

            if attempt < 2:
                time.sleep(1)

        if not device:
            return (
                "Não encontrei um dispositivo ativo do Spotify. "
                "Abra o Spotify e inicie a reprodução antes de adicionar "
                "uma música à fila."
            )

        # Adiciona sem substituir a música atual
        spotify.add_to_queue(
            uri=track_uri,
            device_id=device["id"]
        )

        return f"Adicionei {title}, de {artists}, à fila do Spotify."

    except SpotifyException as error:
        return f"Erro na API do Spotify: {error}"

    except Exception as error:
        return f"Não consegui adicionar a música à fila: {error}"



TOOL = {
    "name": "spotify_add_to_queue",
    "description": (
        "Pesquisa uma música pelo nome e artista e adiciona a faixa "
        "encontrada à fila de reprodução do Spotify, sem interromper "
        "a música atual."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {
                "type": "STRING",
                "description": "Nome da música e, opcionalmente, o artista."
            }
        },
        "required": ["query"]
    },
    "handler": add_to_queue
}
