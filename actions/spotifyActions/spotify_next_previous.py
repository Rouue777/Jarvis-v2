
from core.spotify_client import get_spotify_client
from spotipy.exceptions import SpotifyException


def spotify_next_previous(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    command = str(params.get("command", "")).strip().lower()

    aliases = {
    # Próxima faixa
    "próxima": "next",
    "proxima": "next",
    "próxima música": "next",
    "proxima musica": "next",
    "passar": "next",
    "pular": "next",
    "pular música": "next",
    "pular musica": "next",
    "avançar": "next",
    "avancar": "next",
    "seguinte": "next",
    "próxima faixa": "next",
    "proxima faixa": "next",
    "skip": "next",
    "next track": "next",

    # Faixa anterior
    "voltar": "previous",
    "anterior": "previous",
    "música anterior": "previous",
    "musica anterior": "previous",
    "faixa anterior": "previous",
    "voltar música": "previous",
    "voltar musica": "previous",
    "música passada": "previous",
    "musica passada": "previous",
    "faixa passada": "previous",
    "retroceder": "previous",
    "previous track": "previous",
}
    command = aliases.get(command, command)

    if command not in {"next", "previous"}:
        return (
            "Comando inválido. Informe next para avançar "
            "ou previous para voltar à faixa anterior."
        )

    try:
        spotify = get_spotify_client()

        if command == "next":
            spotify.next_track()
            return "Solicitação enviada para avançar à próxima faixa."

        spotify.previous_track()
        return "Solicitação enviada para voltar à faixa anterior."

    except SpotifyException as e:
        status = getattr(e, "http_status", None)

        if status == 404:
            return (
                "Não encontrei um dispositivo Spotify ativo. "
                "Abra o Spotify e tente novamente."
            )

        return f"Erro da API do Spotify (HTTP {status}): {e}"

    except Exception as e:
        return f"Erro ao controlar a faixa: {e}"


TOOL = {
    "name": "spotify_next_previous",
    "description": (
        "Avança para a próxima faixa ou volta à faixa anterior na "
        "reprodução atual do Spotify. Use quando o usuário disser "
        "'próxima música', 'pular música', 'avançar faixa', "
        "'música anterior', 'voltar música' ou expressões equivalentes. "
        "Use command='next' para avançar e command='previous' para "
        "voltar. Não use para pesquisar ou reproduzir uma música pelo "
        "nome; esses pedidos exigem uma ferramenta de busca e reprodução. "
        "A API pode exigir um dispositivo Spotify ativo. Informe erros "
        "sem afirmar que a faixa mudou quando a operação falhar."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "command": {
                "type": "STRING",
                "enum": ["next", "previous"],
                "description": (
                    "next avança para a próxima faixa; "
                    "previous volta à faixa anterior."
                ),
            }
        },
        "required": ["command"],
    },
    "handler": spotify_next_previous,
}
