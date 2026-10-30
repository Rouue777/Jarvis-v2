
from spotipy.exceptions import SpotifyException
from core.spotify_client import get_spotify_client


def spotify_select_device(parameters=None):
    """Seleciona um dispositivo Spotify pelo nome."""
    try:
        parameters = parameters or {}
        device_name = parameters.get("device_name", "").strip()

        if not device_name:
            return "Informe o nome do dispositivo que deseja selecionar."

        sp = get_spotify_client()
        response = sp.devices()
        devices = response.get("devices", [])

        if not devices:
            return "Não encontrei dispositivos disponíveis no Spotify."

        # Busca primeiro uma correspondência exata.
        matches = [
            device for device in devices
            if device.get("name", "").casefold() == device_name.casefold()
        ]

        # Se não encontrar, tenta correspondência parcial.
        if not matches:
            matches = [
                device for device in devices
                if device_name.casefold() in device.get("name", "").casefold()
            ]

        if not matches:
            nomes = ", ".join(
                device.get("name", "Desconhecido")
                for device in devices
            )
            return (
                f"Não encontrei o dispositivo '{device_name}'. "
                f"Disponíveis: {nomes}."
            )

        if len(matches) > 1:
            nomes = ", ".join(
                device.get("name", "") for device in matches
            )
            return (
                f"Encontrei mais de um dispositivo correspondente: "
                f"{nomes}. Informe o nome completo."
            )

        device = matches[0]

        sp.transfer_playback(
            device_id=device["id"],
            force_play=False
        )

        return (
            f"Reprodução transferida para "
            f"{device.get('name', 'o dispositivo selecionado')}."
        )

    except SpotifyException as e:
        if e.http_status == 403:
            return "O Spotify não autorizou a transferência de reprodução."
        return f"Erro do Spotify ao selecionar dispositivo: {e}"

    except Exception as e:
        return f"Não consegui selecionar o dispositivo: {e}"


TOOL = {
    "name": "spotify_select_device",
"description": (
    "Seleciona um dispositivo de reprodução do Spotify pelo nome. "
    "Interprete os nomes informais usados pelo usuário: "
    "'computador', 'desktop' ou 'PC' referem-se ao computador "
    "DESKTOP-S38HR31; 'celular' refere-se ao Moto G22; "
    "'iPhone' refere-se ao iPhone. "
    "Converta essas referências para o nome correspondente "
    "antes de chamar a ferramenta."
),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "device_name": {
                "type": "STRING",
                "description": "Nome do dispositivo Spotify."
            }
        },
        "required": ["device_name"]
    },
    "handler": spotify_select_device,
}
