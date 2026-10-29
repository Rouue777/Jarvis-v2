
from spotipy.exceptions import SpotifyException

from core.spotify_client import get_spotify_client


def spotify_remove_liked_track(parameters=None):
    """Remove a música atual das músicas curtidas do Spotify."""
    try:
        sp = get_spotify_client()
        playback = sp.current_user_playing_track()

        if not playback or not playback.get("item"):
            return "Não encontrei uma música atual no Spotify."

        track = playback["item"]

        if track.get("type") != "track":
            return "O conteúdo atual não é uma música válida."

        track_id = track.get("id")
        name = track.get("name", "Música desconhecida")
        artists = ", ".join(
            artist.get("name", "Artista desconhecido")
            for artist in track.get("artists", [])
        )

        if not track_id:
            return "Não consegui identificar a música atual."

        saved = sp.current_user_saved_tracks_contains([track_id])

        if not saved or not saved[0]:
            return f"{name}, de {artists}, não está nas suas músicas curtidas."

        sp.current_user_saved_tracks_delete([track_id])

        return (
            f"Removi {name}, de {artists}, "
            "das suas músicas curtidas."
        )

    except SpotifyException as e:
        if e.http_status == 403:
            return (
                "O Spotify negou o acesso. Verifique a permissão "
                "user-library-modify da autorização."
            )

        return f"Erro do Spotify ao remover a música: {e}"

    except Exception as e:
        return f"Não consegui remover a música curtida: {e}"


TOOL = {
    "name": "spotify_remove_liked_track",
    "description": (
        "Remove a música que está tocando atualmente das músicas "
        "curtidas do Spotify do usuário. Use quando ele pedir para "
        "descurtir, remover das curtidas ou tirar a música atual "
        "das músicas salvas. Se ela já não estiver salva, informe isso."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {},
        "required": [],
    },
    "handler": spotify_remove_liked_track,
}
