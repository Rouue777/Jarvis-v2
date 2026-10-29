
import time

from core.spotify_client import get_spotify_client
from spotipy.exceptions import SpotifyException
from actions.spotifyActions.spotify_search import search_tracks


def find_spotify_device(spotify):
    """Localiza um dispositivo, priorizando o computador."""

    for attempt in range(3):
        devices = spotify.devices().get("devices", [])

        available = [
            device for device in devices
            if device.get("id")
            and not device.get("is_restricted", False)
        ]

        if available:
            computer = next(
                (
                    device for device in available
                    if device.get("type") == "Computer"
                ),
                None,
            )

            if computer:
                return computer

            active = next(
                (
                    device for device in available
                    if device.get("is_active")
                ),
                None,
            )

            return active or available[0]

        if attempt < 2:
            time.sleep(1)

    return None



def spotify_play_track(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    query = str(params.get("query", "")).strip()

    if not query:
        return "Informe o nome da música e, se possível, o artista."

    try:
        spotify = get_spotify_client()

        # Pesquisa e classifica as faixas por correspondência
        ranked = search_tracks(spotify, query, limit=10)

        if not ranked:
            return f"Não encontrei músicas para '{query}'."

        best = ranked[0]

        # Evita reproduzir automaticamente uma correspondência fraca
        if best["coverage"] < 0.75:
            return (
                f"Não encontrei uma correspondência confiável para "
                f"'{query}'. Tente informar o nome da música e do artista."
            )

        track = best["track"]
        uri = track.get("uri")

        if not uri:
            return "O Spotify não retornou um identificador válido para essa faixa."

        album_uri = track.get("album", {}).get("uri")

        if not album_uri:
            return "Não encontrei o álbum associado à faixa."

        device = find_spotify_device(spotify)

        if not device:
            return (
                "Não encontrei um dispositivo Spotify disponível. "
                "Abra o Spotify no computador e tente novamente."
            )

        # Reproduz a faixa dentro do contexto do álbum
        spotify.start_playback(
            device_id=device["id"],
            context_uri=album_uri,
            offset={"uri": uri},
            position_ms=0,
        )

        title = track.get("name", "Título desconhecido")
        artists = ", ".join(
            artist.get("name", "Artista desconhecido")
            for artist in track.get("artists", [])
        )

        return (
            f"Solicitação de reprodução enviada: "
            f"{title}, de {artists}, no dispositivo "
            f"{device.get('name', 'selecionado')}."
        )

    except SpotifyException as e:
        status = getattr(e, "http_status", None)

        if status == 404:
            return (
                "O Spotify não conseguiu iniciar a reprodução. "
                "Verifique se o dispositivo continua disponível."
            )

        if status == 403:
            return (
                "A API do Spotify recusou a reprodução. "
                "Verifique as permissões e as restrições da API."
            )

        return f"Erro da API do Spotify (HTTP {status}): {e}"

    except Exception as e:
        return f"Erro ao reproduzir a música: {e}"



TOOL = {
    "name": "spotify_play_track",
    "description": (
        "Pesquisa e reproduz uma música específica no Spotify. "
        "Use somente quando o usuário pedir para tocar ou reproduzir "
        "uma faixa específica. Recebe o nome da música e, se disponível, "
        "o artista. Pesquisa até cinco resultados e reproduz o primeiro. "
        "Usa o contexto do álbum e o offset da faixa selecionada. "
        "Prioriza o dispositivo do tipo Computer quando disponível. "
        "Não use para pedidos que sejam apenas de pesquisa. "
        "Informe a faixa selecionada e não afirme que o áudio começou "
        "sem confirmação do estado de reprodução."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {
                "type": "STRING",
                "description": (
                    "Nome da música e, se possível, o artista. "
                    "Exemplo: 'Faint Linkin Park'."
                ),
            }
        },
        "required": ["query"],
    },
    "handler": spotify_play_track,
}
