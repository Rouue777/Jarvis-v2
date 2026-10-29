
from spotipy.exceptions import SpotifyException

from core.spotify_client import get_spotify_client


def spotify_list_playlists(parameters=None):
    """Lista as playlists disponíveis na conta do Spotify."""
    try:
        sp = get_spotify_client()
        results = sp.current_user_playlists(limit=50)

        playlists = []

        while results:
            for playlist in results.get("items", []):
                if playlist:
                    playlists.append(playlist)

            if not results.get("next"):
                break

            results = sp.next(results)

        if not playlists:
            return "Não encontrei playlists na sua biblioteca do Spotify."

        total = len(playlists)
        displayed = playlists[:15]

        lines = [
            f"{i}. {playlist.get('name', 'Playlist sem nome')} "
            f"— {playlist.get('items', {}).get('total', 0)} músicas"
            for i, playlist in enumerate(displayed, start=1)
        ]

        response = (
            f"Encontrei {total} playlists. "
            f"Mostrando {len(displayed)}:\n"
            + "\n".join(lines)
        )

        if total > len(displayed):
            response += (
                "\nExistem mais playlists; esta listagem mostra "
                "apenas as 15 primeiras."
            )

        return response

    except SpotifyException as e:
        if e.http_status == 403:
            return (
                "O Spotify negou o acesso às playlists. "
                "Verifique a permissão playlist-read-private "
                "na autorização da conta."
            )

        return f"Erro do Spotify ao listar playlists: {e}"

    except Exception as e:
        return f"Não consegui listar as playlists: {e}"


TOOL = {
    "name": "spotify_list_playlists",
    "description": (
        "Lista as playlists disponíveis na conta do usuário no Spotify, "
        "informando seus nomes e quantidades de músicas. Use quando "
        "o usuário pedir para listar, mostrar ou consultar suas playlists."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {},
        "required": [],
    },
    "handler": spotify_list_playlists,
}
