
import unicodedata

from spotipy.exceptions import SpotifyException

from core.spotify_client import get_spotify_client


def normalize_name(name):
    """Normaliza nomes para comparar sem diferenciar acentos ou caixa."""
    normalized = unicodedata.normalize("NFKD", name.casefold())
    return "".join(
        char for char in normalized
        if not unicodedata.combining(char)
    ).strip()


def spotify_play_playlist(parameters=None):
    """Encontra e reproduz uma playlist pelo nome."""
    try:
        parameters = parameters or {}
        playlist_name = parameters.get("playlist_name", "").strip()

        if not playlist_name:
            return "Informe o nome da playlist que deseja reproduzir."

        sp = get_spotify_client()
        results = sp.current_user_playlists(limit=50)
        playlists = []

        while results:
            playlists.extend(
                playlist
                for playlist in results.get("items", [])
                if playlist and playlist.get("uri")
            )

            if not results.get("next"):
                break

            results = sp.next(results)

        target = normalize_name(playlist_name)

        exact_matches = [
            playlist for playlist in playlists
            if normalize_name(playlist.get("name", "")) == target
        ]

        if exact_matches:
            matches = exact_matches
        else:
            matches = [
                playlist for playlist in playlists
                if target in normalize_name(playlist.get("name", ""))
            ]

        if not matches:
            return (
                f"Não encontrei uma playlist chamada "
                f"{playlist_name} na sua conta."
            )

        if len(matches) > 1:
            names = "\n".join(
                f"- {playlist.get('name', 'Playlist sem nome')}"
                for playlist in matches[:5]
            )
            return (
                "Encontrei várias playlists correspondentes. "
                "Informe o nome completo de uma delas:\n" + names
            )

        playlist = matches[0]
        sp.start_playback(context_uri=playlist["uri"])

        return (
            f"Reproduzindo a playlist "
            f"{playlist.get('name', playlist_name)}."
        )

    except SpotifyException as e:
        if e.http_status == 403:
            return (
                "O Spotify negou a reprodução. Verifique as permissões "
                "de controle de reprodução e a autorização da conta."
            )

        if e.http_status == 404:
            return (
                "Não encontrei um dispositivo Spotify ativo. "
                "Abra o Spotify em um dispositivo disponível e tente novamente."
            )

        return f"Erro do Spotify ao reproduzir a playlist: {e}"

    except Exception as e:
        return f"Não consegui reproduzir a playlist: {e}"


TOOL = {
    "name": "spotify_play_playlist",
    "description": (
        "Reproduz uma playlist da conta Spotify do usuário pelo nome. "
        "Use quando o usuário pedir para tocar ou reproduzir uma playlist. "
        "Se houver várias correspondências, solicite o nome completo."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "playlist_name": {
                "type": "STRING",
                "description": "Nome da playlist que o usuário deseja reproduzir."
            }
        },
        "required": ["playlist_name"],
    },
    "handler": spotify_play_playlist,
}
