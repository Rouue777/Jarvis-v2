
import re
import unicodedata

from spotipy.exceptions import SpotifyException
from core.spotify_client import get_spotify_client


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        c for c in texto
        if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-zA-Z0-9]+", " ", texto).strip().casefold()


def spotify_remove_from_playlist(parameters=None):
    """Remove uma música de uma playlist do Spotify."""
    try:
        parameters = parameters or {}

        playlist_name = parameters.get("playlist_name", "").strip()
        track_name = parameters.get("track_name", "").strip()
        artist_name = parameters.get("artist_name", "").strip()

        if not playlist_name or not track_name:
            return "Informe o nome da playlist e da música que deseja remover."

        sp = get_spotify_client()

        # Localiza a playlist.
        playlists = []
        page = sp.current_user_playlists(limit=50)

        while page:
            playlists.extend(page.get("items", []))
            if not page.get("next"):
                break
            page = sp.next(page)

        nome_playlist = normalizar(playlist_name)

        exatas = [
            p for p in playlists
            if normalizar(p.get("name", "")) == nome_playlist
        ]

        if len(exatas) == 1:
            playlist = exatas[0]
        elif len(exatas) > 1:
            return (
                f"Encontrei mais de uma playlist chamada "
                f"'{playlist_name}'. Informe mais detalhes."
            )
        else:
            semelhantes = [
                p for p in playlists
                if nome_playlist in normalizar(p.get("name", ""))
            ]

            if len(semelhantes) == 1:
                playlist = semelhantes[0]
            elif semelhantes:
                nomes = ", ".join(
                    p.get("name", "") for p in semelhantes[:5]
                )
                return f"Encontrei várias playlists semelhantes: {nomes}."
            else:
                return f"Não encontrei a playlist '{playlist_name}'."

        # Pesquisa a música.
        query = f"track:{track_name}"
        if artist_name:
            query += f" artist:{artist_name}"

        resultado = sp.search(q=query, type="track", limit=10)
        tracks = resultado.get("tracks", {}).get("items", [])
        nome_musica = normalizar(track_name)
        nome_artista = normalizar(artist_name)

        candidatas = [
            t for t in tracks
            if normalizar(t.get("name", "")) == nome_musica
            and (
                not nome_artista
                or any(
                    nome_artista in normalizar(a.get("name", ""))
                    for a in t.get("artists", [])
                )
            )
        ]

        if not candidatas:
            return (
                f"Não encontrei uma correspondência exata para "
                f"'{track_name}'. Confira o nome da música e do artista."
            )

        # Lê os itens da playlist para confirmar que a música está nela.
        itens_playlist = []
        page = sp.playlist_items(playlist["id"], limit=100)

        while page:
            for entry in page.get("items", []):
                item = entry.get("item") or entry.get("track") or entry
                if item and item.get("uri"):
                    itens_playlist.append(item)

            if not page.get("next"):
                break
            page = sp.next(page)

        uris_playlist = {
            item.get("uri") for item in itens_playlist
        }

        encontradas = [
            t for t in candidatas
            if t.get("uri") in uris_playlist
        ]

        if not encontradas:
            return (
                f"Não encontrei '{track_name}' na playlist "
                f"'{playlist['name']}'. Nenhuma música foi removida."
            )

        # Evita escolher entre artistas diferentes sem confirmação.
        artistas = {
            normalizar(a.get("name", ""))
            for t in encontradas
            for a in t.get("artists", [])
        }

        if not artist_name and len(artistas) > 1:
            opcoes = [
                f"{t['name']} — "
                f"{', '.join(a['name'] for a in t.get('artists', []))}"
                for t in encontradas[:5]
            ]
            return (
                "Encontrei músicas com esse nome de artistas diferentes: "
                + "; ".join(opcoes)
                + ". Informe o artista para eu remover a correta."
            )

        if len(encontradas) > 1:
            opcoes = [
                f"{t['name']} — "
                f"{', '.join(a['name'] for a in t.get('artists', []))}"
                for t in encontradas[:5]
            ]
            return (
                "Encontrei mais de uma versão dessa música na playlist: "
                + "; ".join(opcoes)
                + ". Informe melhor qual versão deseja remover."
            )

        track = encontradas[0]

        # Remove todas as ocorrências dessa faixa na playlist.
        sp.playlist_remove_all_occurrences_of_items(
            playlist["id"],
            [track["uri"]],
        )

        artistas = ", ".join(
            a["name"] for a in track.get("artists", [])
        )

        return (
            f"Removi '{track['name']}', de {artistas}, "
            f"da playlist '{playlist['name']}'."
        )

    except SpotifyException as e:
        if e.http_status == 403:
            return (
                "O Spotify negou a remoção. Verifique as permissões "
                "playlist-modify-private e playlist-modify-public."
            )
        return f"Erro do Spotify ao remover a música: {e}"

    except Exception as e:
        return f"Não consegui remover a música da playlist: {e}"


TOOL = {
    "name": "spotify_remove_from_playlist",
    "description": (
        "Remove uma música de uma playlist do Spotify. "
        "Use quando o usuário pedir para remover ou tirar uma música "
        "de uma playlist. Identifique o nome da playlist, da música "
        "e o artista, se informado. Se faltar playlist ou música, "
        "solicite a informação."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "playlist_name": {
                "type": "STRING",
                "description": "Nome da playlist."
            },
            "track_name": {
                "type": "STRING",
                "description": "Nome da música."
            },
            "artist_name": {
                "type": "STRING",
                "description": "Artista da música, se informado."
            }
        },
        "required": ["playlist_name", "track_name"]
    },
    "handler": spotify_remove_from_playlist,
}
