from core.spotify_client import get_spotify_client


def spotify_profile(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    try:
        user = get_spotify_client().current_user()

        nome = user.get("display_name") or user.get("id")
        plano = user.get("product", "não informado")

        return f"Conta Spotify: {nome}. Plano: {plano}."

    except Exception as e:
        return f"Erro ao consultar o Spotify: {e}"


TOOL = {
    "name": "spotify_profile",
    "description": (
           "Consulta os dados da conta Spotify atualmente autenticada no Jarvis, "
    "incluindo nome de exibição, identificador da conta e tipo de plano "
    "(Free ou Premium, quando informado pela API). "
    "Use esta ferramenta quando o usuário perguntar qual conta Spotify "
    "está conectada, qual é o nome do perfil, qual plano possui ou se a "
    "conexão com o Spotify está funcionando. "
    "Também use para verificar a autenticação antes de diagnosticar "
    "problemas de integração com o Spotify. "
    "Esta ferramenta é somente de consulta: não inicia, pausa ou altera "
    "a reprodução, não modifica playlists e não altera configurações "
    "da conta. "
    "Responda com base nos dados retornados pela ferramenta; não presuma "
    "informações que não foram fornecidas pela API."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {},
        "required": [],
    },
    "handler": spotify_profile,
}