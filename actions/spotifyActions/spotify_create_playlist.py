
from spotipy.exceptions import SpotifyException

from core.spotify_client import get_spotify_client


def spotify_create_playlist(parameters=None):
    """Cria uma playlist na conta do usuário do Spotify."""
    try:
        parameters = parameters or {}
        name = parameters.get("name", "").strip()
        description = parameters.get("description", "").strip()
        public = parameters.get("public", False)

        if not name:
            return "Informe o nome da playlist que deseja criar."

        sp = get_spotify_client()
        

        playlist = sp.current_user_playlist_create(
            name=name,
            public=bool(public),
            description=description,
        )

        return f"Playlist '{playlist['name']}' criada com sucesso."

    except SpotifyException as e:
        if e.http_status == 403:
            return (
                "O Spotify negou a criação da playlist. "
                "Verifique a autorização da conta e as permissões necessárias."
            )

        return f"Erro do Spotify ao criar a playlist: {e}"

    except Exception as e:
        return f"Não consegui criar a playlist: {e}"


TOOL = {
    "name": "spotify_create_playlist",
    "description": (
        "Cria uma nova playlist na conta Spotify do usuário. "
        "Use quando ele pedir para criar ou fazer uma playlist. "
        "Solicite o nome se ele não informar. "
        "A playlist deve ser privada por padrão, a menos que o usuário "
        "peça explicitamente uma playlist pública."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "name": {
                "type": "STRING",
                "description": "Nome da nova playlist."
            },
            "description": {
                "type": "STRING",
                "description": "Descrição opcional da playlist."
            },
            "public": {
                "type": "BOOLEAN",
                "description": "Se deve ser pública. Padrão: false."
            },
        },
        "required": ["name"],
    },
    "handler": spotify_create_playlist,
}
