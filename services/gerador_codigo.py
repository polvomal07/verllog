"""
Geração e validação do código de rastreamento (Fase 4).

Padrão obrigatório: BR + 12 números + 1 letra maiúscula  ->  15 caracteres.
Exemplo válido: BR263198595496D

Há uma distinção importante aqui:

  - `validar_estrito()` é usado na IMPORTAÇÃO. Ele respeita a caixa das letras,
    então 'BR263198595496d' é recusado, como manda a especificação.

  - `validar()` é usado na BUSCA do site. Ali o usuário está digitando, e
    exigir Caps Lock seria só maltratar quem consulta — então minúsculas e
    espaços são tolerados e convertidos antes da comparação.
"""

import random
import re
import string

from config import Config

PADRAO = re.compile(Config.CODIGO_REGEX)
PADRAO_LEGADO = re.compile(Config.CODIGO_REGEX_LEGADO)
LETRAS = string.ascii_uppercase

# Valores que planilhas costumam entregar no lugar de uma célula vazia.
VAZIOS = {"", "NAN", "NAT", "NONE", "NULL", "-"}


def limpar(codigo):
    """Remove espaços, hífens e pontos, preservando a caixa das letras."""
    if codigo is None:
        return ""

    # pandas entrega float('nan') em células vazias; nan != nan.
    if isinstance(codigo, float) and codigo != codigo:
        return ""

    texto = str(codigo).strip()
    texto = re.sub(r"[\s\-\.]", "", texto)

    if texto.upper() in VAZIOS:
        return ""
    return texto


def normalizar(codigo):
    """
    Versão para busca: além de limpar, joga para maiúsculas.

    Faz com que 'br 2631-98595496 d' encontre o mesmo pedido que
    'BR263198595496D'.
    """
    return limpar(codigo).upper()


def no_padrao_oficial(codigo):
    """True só para o padrão novo: BR + 12 números + 1 letra maiúscula."""
    return bool(PADRAO.fullmatch(limpar(codigo)))


def eh_legado(codigo):
    """
    True para os códigos antigos que vieram da operação e não seguem o padrão
    novo (terminam em número, usam outro prefixo, têm outro tamanho).
    """
    if not Config.ACEITAR_CODIGOS_LEGADOS:
        return False
    bruto = normalizar(codigo)
    return bool(PADRAO_LEGADO.fullmatch(bruto)) and not PADRAO.fullmatch(bruto)


def validar_estrito(codigo):
    """
    Validação da IMPORTAÇÃO.

    Aceita o padrão oficial e, enquanto ACEITAR_CODIGOS_LEGADOS estiver ligado,
    também os códigos antigos já em uso. Desligar a opção em config.py volta a
    exigir o padrão novo de todo mundo.
    """
    return no_padrao_oficial(codigo) or eh_legado(codigo)


def validar(codigo):
    """
    Validação da BUSCA no site.

    Tolerante com a digitação (caixa, espaços, hífens) e aceita tanto o padrão
    oficial quanto os códigos legados — senão o cliente com um código antigo
    não conseguiria rastrear a própria encomenda.
    """
    bruto = normalizar(codigo)
    return bool(PADRAO.fullmatch(bruto)) or eh_legado(bruto)


def motivo_invalido(codigo):
    """Mensagem explicando por que um código foi recusado (usada na importação)."""
    bruto = limpar(codigo)

    if not bruto:
        return "código vazio"

    prefixo = bruto[:2]
    if not prefixo.isalpha():
        return "os dois primeiros caracteres precisam ser letras"
    if prefixo != prefixo.upper():
        return "o prefixo de duas letras precisa estar em maiúsculas"

    if len(bruto) != Config.CODIGO_TAMANHO:
        return (
            "tem " + str(len(bruto)) + " caracteres, deveria ter "
            + str(Config.CODIGO_TAMANHO)
        )

    miolo = bruto[2:-1]
    if not miolo.isdigit():
        return (
            "os " + str(Config.CODIGO_QTD_DIGITOS)
            + " caracteres do meio precisam ser todos números"
        )

    final = bruto[-1]
    if final.upper() in LETRAS and final not in LETRAS:
        return "a letra final precisa ser maiúscula"
    if final not in LETRAS:
        return "o último caractere precisa ser uma letra maiúscula de A a Z"

    return "fora do padrão 2 letras + 12 números + 1 letra maiúscula"


def gerar():
    """Gera um código no padrão, sem consultar o banco."""
    digitos = "".join(random.choices(string.digits, k=Config.CODIGO_QTD_DIGITOS))
    return Config.CODIGO_PREFIXO + digitos + random.choice(LETRAS)


def gerar_unico(codigos_reservados=None, tentativas_maximas=100):
    """
    Gera um código garantidamente inédito.

    Confere tanto no banco quanto no conjunto `codigos_reservados` — que é
    usado pelo importador para segurar os códigos criados durante a mesma
    planilha, antes do commit.
    """
    from models import Pedido  # importado aqui para evitar ciclo de importação

    reservados = codigos_reservados if codigos_reservados is not None else set()

    for _ in range(tentativas_maximas):
        codigo = gerar()
        if codigo in reservados:
            continue
        if Pedido.query.filter_by(codigo_rastreio=codigo).first() is None:
            reservados.add(codigo)
            return codigo

    raise RuntimeError(
        "Não foi possível gerar um código único depois de "
        + str(tentativas_maximas)
        + " tentativas."
    )
