
from spotipy.exceptions import SpotifyException
from core.spotify_client import get_spotify_client


def spotify_play_album(parameters=None):
    """Pesquisa e reproduz um álbum completo no Spotify."""
    try:
        parameters = parameters or {}
        album_name = parameters.get("album_name")
        artist_name = parameters.get("artist_name")

        if not album_name:
            return "Informe o nome do álbum."

        query = f"album:{album_name}"
        if artist_name:
            query += f" artist:{artist_name}"

        sp = get_spotify_client()
        results = sp.search(q=query, type="album", limit=5)
        albums = results.get("albums", {}).get("items", [])

        if not albums:
            return f"Não encontrei o álbum '{album_name}'."

        album = albums[0]
        album_uri = album["uri"]

        sp.start_playback(context_uri=album_uri)

        artist = ", ".join(
            artist["name"] for artist in album.get("artists", [])
        )

        return (
            f"Tocando o álbum '{album['name']}', "
            f"de {artist}."
        )

    except SpotifyException as e:
        return f"Erro ao reproduzir álbum: {e}"
    except Exception as e:
        return f"Não consegui reproduzir o álbum: {e}"


TOOL = {
    "name": "spotify_play_album",
    "description": (
        "Pesquisa e reproduz um álbum completo no Spotify. "
        "Use album_name para o nome do álbum e artist_name "
        "para identificar o artista, quando informado. "
        "Não utilize esta ação para reproduzir uma música isolada."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "album_name": {
                "type": "STRING",
                "description": "Nome do álbum que o usuário deseja ouvir."
            },
            "artist_name": {
                "type": "STRING",
                "description": "Artista responsável pelo álbum."
            }
        },
        "required": ["album_name"]
    },
    "handler": spotify_play_album,
}
