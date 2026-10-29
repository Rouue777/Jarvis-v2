
from spotipy.exceptions import SpotifyException

from core.spotify_client import get_spotify_client


def spotify_save_current_track(parameters=None):
    """Salva a música atual na biblioteca do Spotify."""
    try:
        sp = get_spotify_client()

        playback = sp.current_user_playing_track()

        if not playback or not playback.get("item"):
            return "Não encontrei uma música atual no Spotify."

        track = playback["item"]

        if track.get("type") != "track":
            return "O conteúdo atual não é uma música que possa ser salva."

        track_id = track.get("id")
        name = track.get("name", "Música desconhecida")
        artists = ", ".join(
            artist.get("name", "Artista desconhecido")
            for artist in track.get("artists", [])
        )

        if not track_id:
            return "Não consegui identificar a música atual."

        saved = sp.current_user_saved_tracks_contains([track_id])

        if saved and saved[0]:
            return f"{name}, de {artists}, já está na sua biblioteca."

        sp.current_user_saved_tracks_add([track_id])

        return f"Curti {name}, de {artists}. Música salva na sua biblioteca."

    except SpotifyException as e:
        if e.http_status == 403:
            return (
                "O Spotify negou o acesso. Precisamos verificar as "
                "permissões de leitura e alteração da biblioteca."
            )

        return f"Erro do Spotify ao salvar a música: {e}"

    except Exception as e:
        return f"Não consegui salvar a música atual: {e}"


TOOL = {
    "name": "spotify_save_current_track",
    "description": (
        "Salva a música que está tocando atualmente na biblioteca "
        "do Spotify do usuário. Use quando ele pedir para curtir, "
        "gostar ou salvar a música atual. Se já estiver salva, "
        "informe isso sem adicioná-la novamente."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {},
        "required": [],
    },
    "handler": spotify_save_current_track,
}
