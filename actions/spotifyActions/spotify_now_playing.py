
from core.spotify_client import get_spotify_client
from spotipy.exceptions import SpotifyException


def spotify_now_playing(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    try:
        spotify = get_spotify_client()
        playback = spotify.current_playback()

        if not playback:
            return (
                "Não encontrei uma reprodução ativa no Spotify. "
                "Verifique se há música tocando em algum dispositivo."
            )

        track = playback.get("item")

        if not track:
            return "O Spotify não retornou informações da faixa atual."

        title = track.get("name", "Título desconhecido")
        artists = ", ".join(
            artist.get("name", "Artista desconhecido")
            for artist in track.get("artists", [])
        )
        album = track.get("album", {}).get("name", "Álbum desconhecido")
        is_playing = playback.get("is_playing", False)
        progress_ms = playback.get("progress_ms")
        duration_ms = track.get("duration_ms")

        status = "tocando" if is_playing else "pausada"

        details = [
            f"Música: {title}",
            f"Artista(s): {artists or 'Não informado'}",
            f"Álbum: {album}",
            f"Estado: {status}",
        ]

        if progress_ms is not None and duration_ms:
            progress = progress_ms // 1000
            duration = duration_ms // 1000
            details.append(
                f"Progresso: {progress // 60}:{progress % 60:02d}"
                f" / {duration // 60}:{duration % 60:02d}"
            )

        return ". ".join(details) + "."

    except SpotifyException as e:
        status = getattr(e, "http_status", None)

        if status == 404:
            return "Não encontrei um dispositivo Spotify ativo."

        return f"Erro da API do Spotify (HTTP {status}): {e}"

    except Exception as e:
        return f"Erro ao consultar a reprodução atual: {e}"


TOOL = {
    "name": "spotify_now_playing",
    "description": (
        "Consulta a reprodução atual do Spotify e retorna o título da "
        "música, artistas, álbum, estado de reprodução (tocando ou pausada) "
        "e progresso da faixa, quando disponíveis. "
        "Use quando o usuário perguntar 'qual música está tocando?', "
        "'quem canta essa música?', 'qual é o nome dessa faixa?', "
        "'qual álbum é esse?' ou 'a música está pausada?'. "
        "Use os dados retornados para responder sem inventar informações. "
        "Esta ferramenta é somente de consulta: não inicia, pausa, pula "
        "nem altera o volume. Se não houver reprodução disponível, "
        "explique isso claramente."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {},
        "required": [],
    },
    "handler": spotify_now_playing,
}
