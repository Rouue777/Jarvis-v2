
from core.spotify_client import get_spotify_client
from spotipy.exceptions import SpotifyException


def spotify_search_tracks(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    query = str(params.get("query", "")).strip()

    if not query:
        return "Informe o nome da música ou do artista para pesquisar."

    try:
        spotify = get_spotify_client()

        results = spotify.search(
            q=query,
            type="track",
            limit=5,
        )

        tracks = results.get("tracks", {}).get("items", [])

        if not tracks:
            return f"Nenhuma música encontrada para '{query}'."

        matches = []

        for index, track in enumerate(tracks, start=1):
            title = track.get("name", "Título desconhecido")

            artists = ", ".join(
                artist.get("name", "Artista desconhecido")
                for artist in track.get("artists", [])
            )

            album = track.get("album", {}).get(
                "name", "Álbum desconhecido"
            )

            duration_ms = track.get("duration_ms", 0)
            total_seconds = duration_ms // 1000
            duration = (
                f"{total_seconds // 60}:"
                f"{total_seconds % 60:02d}"
            )

            matches.append(
                f"{index}. {title} — {artists}; "
                f"álbum: {album}; duração: {duration}"
            )

        return (
            f"Resultados para '{query}':\n"
            + "\n".join(matches)
        )

    except SpotifyException as e:
        status = getattr(e, "http_status", None)
        return f"Erro da API do Spotify (HTTP {status}): {e}"

    except Exception as e:
        return f"Erro ao pesquisar no Spotify: {e}"


TOOL = {
    "name": "spotify_search_tracks",
    "description": (
        "Pesquisa faixas no catálogo do Spotify por nome de música, "
        "artista ou combinação dos dois. Retorna até cinco resultados "
        "com título, artistas, álbum e duração. Use quando o usuário "
        "pedir para pesquisar, procurar ou encontrar músicas. "
        "Esta ação apenas consulta o catálogo: não inicia a reprodução "
        "nem adiciona faixas à fila. Não invente resultados."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {
                "type": "STRING",
                "description": (
                    "Nome da música, artista ou combinação. "
                    "Exemplo: 'Bohemian Rhapsody Queen'."
                ),
            }
        },
        "required": ["query"],
    },
    "handler": spotify_search_tracks,
}
