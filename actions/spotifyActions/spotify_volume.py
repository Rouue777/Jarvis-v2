
from core.spotify_client import get_spotify_client
from spotipy.exceptions import SpotifyException


def spotify_volume(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    try:
        volume = int(params.get("volume"))

        if not 0 <= volume <= 100:
            return "O volume deve estar entre 0 e 100."

        spotify = get_spotify_client()
        spotify.volume(volume)

        return f"Solicitação enviada para ajustar o volume do Spotify para {volume}%."

    except (TypeError, ValueError):
        return "Informe um volume inteiro entre 0 e 100."

    except SpotifyException as e:
        status = getattr(e, "http_status", None)

        if status == 404:
            return (
                "Não encontrei um dispositivo Spotify ativo. "
                "Abra o Spotify e tente novamente."
            )

        return f"Erro da API do Spotify (HTTP {status}): {e}"

    except Exception as e:
        return f"Erro ao ajustar o volume: {e}"


TOOL = {
    "name": "spotify_volume",
    "description": (
        "Ajusta o volume do dispositivo Spotify ativo para um percentual "
        "entre 0 e 100. Use quando o usuário pedir para aumentar, diminuir, "
        "definir ou colocar o volume em determinado nível. "
        "Interprete expressões como 'volume no máximo' como 100, "
        "'volume pela metade' como 50, 'abaixe um pouco' como um valor "
        "menor que o volume atual, quando este puder ser consultado, "
        "e 'aumente um pouco' como um valor maior que o atual. "
        "Para pedidos relativos, consulte o volume atual antes de calcular "
        "o novo valor; se não puder obtê-lo, pergunte ao usuário qual "
        "percentual deseja. "
        "O parâmetro volume deve ser um número inteiro de 0 a 100. "
        "Esta ferramenta controla o volume do Spotify, não o volume geral "
        "do Windows. A API pode exigir um dispositivo ativo. "
        "Não afirme que o volume foi alterado se a API retornar erro."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "volume": {
                "type": "INTEGER",
                "description": (
                    "Volume desejado em percentual, de 0 a 100. "
                    "Exemplos: 20 para 20%, 50 para metade e 100 para máximo."
                ),
            }
        },
        "required": ["volume"],
    },
    "handler": spotify_volume,
}
