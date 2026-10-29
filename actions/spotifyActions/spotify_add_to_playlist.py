
import re
import unicodedata

from spotipy.exceptions import SpotifyException
from core.spotify_client import get_spotify_client


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )
    return re.sub(r"[^a-zA-Z0-9]+", " ", texto).strip().casefold()


def spotify_add_to_playlist(parameters=None):
    """Adiciona uma música encontrada pelo nome a uma playlist do usuário."""
    try:
        parameters = parameters or {}

        playlist_name = parameters.get("playlist_name", "").strip()
        track_name = parameters.get("track_name", "").strip()
        artist_name = parameters.get("artist_name", "").strip()

        if not playlist_name or not track_name:
            return "Informe o nome da playlist e o nome da música."

        sp = get_spotify_client()

        # Procura as playlists da conta do usuário.
        playlists = []
        page = sp.current_user_playlists(limit=50)

        while page:
            playlists.extend(page.get("items", []))

            if not page.get("next"):
                break

            page = sp.next(page)

        playlist_query = normalizar(playlist_name)

        exact_playlists = [
            playlist
            for playlist in playlists
            if normalizar(playlist.get("name", "")) == playlist_query
        ]

        if len(exact_playlists) == 1:
            playlist = exact_playlists[0]
        elif len(exact_playlists) > 1:
            return (
                f"Encontrei mais de uma playlist chamada "
                f"'{playlist_name}'. Informe mais detalhes."
            )
        else:
            partial_playlists = [
                playlist
                for playlist in playlists
                if playlist_query in normalizar(playlist.get("name", ""))
            ]

            if len(partial_playlists) == 1:
                playlist = partial_playlists[0]
            elif partial_playlists:
                nomes = ", ".join(
                    p.get("name", "Sem nome")
                    for p in partial_playlists[:5]
                )
                return (
                    f"Encontrei várias playlists semelhantes: {nomes}. "
                    "Informe o nome exato."
                )
            else:
                return f"Não encontrei a playlist '{playlist_name}'."

        # Pesquisa a música no catálogo do Spotify.
        query = f"track:{track_name}"

        if artist_name:
            query += f" artist:{artist_name}"

        results = sp.search(q=query, type="track", limit=10)
        tracks = results.get("tracks", {}).get("items", [])

        if not tracks:
            return f"Não encontrei a música '{track_name}' no Spotify."

        track_query = normalizar(track_name)
        artist_query = normalizar(artist_name)

        exact_tracks = [
            track
            for track in tracks
            if normalizar(track.get("name", "")) == track_query
            and (
                not artist_query
                or any(
                    artist_query in normalizar(artist.get("name", ""))
                    for artist in track.get("artists", [])
                )
            )
        ]

        if not exact_tracks:
            sugestoes = [
                f"{track.get('name')} — "
                f"{', '.join(a['name'] for a in track.get('artists', []))}"
                for track in tracks[:3]
            ]
            return (
                f"Não encontrei uma correspondência exata para "
                f"'{track_name}'. Sugestões: {'; '.join(sugestoes)}. "
                "Informe o nome exato ou o artista."
            )

        # Sem artista informado, evita escolher entre músicas homônimas.
        if not artist_name:
            artistas = {
                normalizar(artist.get("name", ""))
                for track in exact_tracks
                for artist in track.get("artists", [])
            }

            if len(artistas) > 1:
                sugestoes = [
                    f"{track.get('name')} — "
                    f"{', '.join(a['name'] for a in track.get('artists', []))}"
                    for track in exact_tracks[:5]
                ]
                return (
                    "Encontrei músicas com esse nome de artistas diferentes: "
                    + "; ".join(sugestoes)
                    + ". Informe o artista para eu escolher corretamente."
                )

        track = exact_tracks[0]

        # Adiciona a faixa à playlist.
        # Spotipy 2.26.0 usa o endpoint atualizado de itens de playlist.
        sp.playlist_add_items(
            playlist["id"],
            [track["uri"]],
        )

        artists = ", ".join(
            artist["name"] for artist in track.get("artists", [])
        )

        return (
            f"Adicionei '{track['name']}', de {artists}, "
            f"à playlist '{playlist['name']}'."
        )

    except SpotifyException as e:
        if e.http_status == 403:
            return (
                "O Spotify negou a operação. Verifique as permissões "
                "playlist-modify-private e playlist-modify-public "
                "e a autorização da conta."
            )

        return f"Erro do Spotify ao adicionar a música: {e}"

    except Exception as e:
        return f"Não consegui adicionar a música à playlist: {e}"


TOOL = {
    "name": "spotify_add_to_playlist",
    "description": (
        "Adiciona uma música a uma playlist do Spotify. "
        "Use quando o usuário pedir para colocar ou adicionar uma música "
        "em uma playlist. Identifique o nome da música, o nome da playlist "
        "e, se informado, o artista. Se faltar o nome da música ou "
        "da playlist, solicite a informação."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "playlist_name": {
                "type": "STRING",
                "description": "Nome da playlist de destino."
            },
            "track_name": {
                "type": "STRING",
                "description": "Nome da música que será adicionada."
            },
            "artist_name": {
                "type": "STRING",
                "description": "Artista da música, se informado."
            }
        },
        "required": ["playlist_name", "track_name"]
    },
    "handler": spotify_add_to_playlist,
}
