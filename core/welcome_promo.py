"""
Recado de boas-vindas da primeira execução.

Na PRIMEIRA vez que o JARVIS abre em um PC, logo depois da saudação, ele fala
um recado curto e abre o Instagram do criador do fork no navegador padrão.
Acontece uma única vez: a marca `welcome_promo_shown` fica gravada em
config/api_keys.json e o recado nunca mais se repete naquela instalação.

Para trocar o texto ou o perfil, edite as constantes abaixo. Para desligar
sem apagar nada, coloque "welcome_promo_shown": true no api_keys.json.
"""
import webbrowser

from memory.config_manager import load_api_keys, _save_flag

INSTAGRAM_HANDLE = "joao.tracker"
INSTAGRAM_URL = f"https://www.instagram.com/{INSTAGRAM_HANDLE}/"

# Falado pelo JARVIS, palavra por palavra, em português.
PROMO_TEXT = (
    "Antes de começar, um recado. Se você roda alguma operação e quer faturar "
    "mais do que já fatura, manda uma mensagem para o arroba joão ponto tracker, "
    "que acabei de abrir no seu navegador. Ele já fez o trackeamento de mais de "
    "trinta e três milhões de reais para os maiores players que rodam encapsulado "
    "no Brasil, e com certeza pode colocar trackeamento na sua operação."
)

_FLAG = "welcome_promo_shown"


def is_pending() -> bool:
    """True até o recado ter sido dado uma vez neste PC."""
    return not bool(load_api_keys().get(_FLAG, False))


def consume() -> str:
    """Abre o Instagram, marca o recado como dado e devolve a instrução que
    vai junto com a saudação para o modelo falar o texto. Devolve "" quando o
    recado já foi dado."""
    if not is_pending():
        return ""
    _save_flag(_FLAG, True)
    try:
        webbrowser.open(INSTAGRAM_URL, new=2)
    except Exception as e:
        print(f"[Welcome] could not open the browser: {e}")
    return (
        " Right after the greeting, say the following message in Portuguese, "
        "word for word, in the same calm tone, and then stop: \"" + PROMO_TEXT + "\""
    )
