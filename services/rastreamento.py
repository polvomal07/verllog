"""
Motor de rastreamento (Fases 5 e 7).

Transforma um pedido em uma timeline logística completa, com data, hora e local
de cada evento. Duas garantias importantes vêm daqui:

1. DETERMINISMO — as horas não são sorteadas na hora da consulta. Elas saem de
   um hash do próprio código de rastreio, então o mesmo pedido mostra sempre os
   mesmos horários, e as movimentações ainda por cima ficam gravadas no banco.

2. FUNCIONA COM O PC DESLIGADO — nenhuma tarefa roda em segundo plano. Cada
   evento tem uma data futura fixa; o "status de hoje" é simplesmente o último
   evento cuja data já passou. Se a máquina ficar cinco dias desligada, ao
   voltar o pedido já aparece cinco dias mais adiante, sozinho.
"""

import hashlib
from datetime import date, datetime, time, timedelta, timezone

from config import Config
from services.rotas import montar_rota

# Descrição amigável de cada status do fluxo.
DESCRICOES = {
    "Pedido postado": "Pedido postado na {empresa}",
    "Pedido processado": "Pedido processado e etiquetado no centro de origem",
    "Objeto coletado": "Objeto coletado e liberado para transporte",
    "Em transferência": "Objeto em trânsito entre centros de distribuição",
    "Centro de distribuição": "Objeto chegou ao centro de distribuição de destino",
    "Unidade de destino": "Objeto encaminhado para a unidade de entrega",
    "Tentativa de entrega não realizada": (
        "O entregador esteve no endereço e não encontrou ninguém para receber "
        "o objeto"
    ),
    "Nova tentativa de entrega": (
        "Uma nova tentativa de entrega será realizada pelo entregador"
    ),
    "Saiu para entrega": "Objeto saiu para entrega ao destinatário",
    "Entregue": "Objeto entregue ao destinatário",
}


def _hora_deterministica(codigo, ordem):
    """
    Hora fictícia, porém sempre a mesma para o par (código, etapa).

    Usa MD5 só como gerador estável de números — não há nada criptográfico aqui.
    """
    semente = hashlib.md5(f"{codigo}:{ordem}".encode("utf-8")).digest()
    hora = 8 + semente[0] % 11        # entre 08h e 18h
    minuto = semente[1] % 60
    return time(hour=hora, minute=minuto)


def _dias_das_transferencias(quantidade):
    """
    Distribui as etapas "Em transferência" dentro da janela configurada.

    Com 2 centros no meio do caminho e a janela (6, 20), por exemplo, as
    transferências caem nos dias 10 e 15. Assim o número de paradas muda de
    acordo com a rota, mas o trajeto inteiro continua fechando no mesmo dia.
    """
    if quantidade <= 0:
        return []

    inicio, fim = Config.JANELA_TRANSFERENCIA
    intervalo = fim - inicio

    return [
        inicio + round(intervalo * (posicao + 1) / (quantidade + 1))
        for posicao in range(quantidade)
    ]


def _montar_sequencia(rota):
    """
    Monta a lista (status, local, dia) do trajeto, na ordem.

    O dia de cada etapa vem do CRONOGRAMA em config.py, contado a partir da
    data de cadastro. As transferências são o único trecho elástico: elas se
    espalham na janela entre a coleta e a chegada ao centro de destino.
    """
    centros = rota["centros"]
    origem = centros[0]["local"]
    destino = rota["destino"]
    cronograma = Config.CRONOGRAMA

    sequencia = [
        ("Pedido postado", origem, cronograma["Pedido postado"]),
        ("Pedido processado", origem, cronograma["Pedido processado"]),
        ("Objeto coletado", origem, cronograma["Objeto coletado"]),
    ]

    # Centros no meio do caminho (exclui a origem e o centro final).
    intermediarios = centros[1:-1]
    for centro, dia in zip(intermediarios, _dias_das_transferencias(len(intermediarios))):
        sequencia.append(("Em transferência", centro["local"], dia))

    # Centro de distribuição que atende o destino.
    sequencia.append(
        ("Centro de distribuição", centros[-1]["local"], cronograma["Centro de distribuição"])
    )

    sequencia.append(("Unidade de destino", destino, cronograma["Unidade de destino"]))

    # Primeira tentativa frustrada, seguida do reagendamento e da entrega.
    sequencia.append(
        (
            "Tentativa de entrega não realizada",
            destino,
            cronograma["Tentativa de entrega não realizada"],
        )
    )
    sequencia.append(
        ("Nova tentativa de entrega", destino, cronograma["Nova tentativa de entrega"])
    )
    sequencia.append(("Saiu para entrega", destino, cronograma["Saiu para entrega"]))
    sequencia.append(("Entregue", destino, cronograma["Entregue"]))

    return sequencia


# ----------------------------------------------------------------------
# Cronograma de 45 dias
# ----------------------------------------------------------------------

# Atualizações de espera, usadas para preencher os dias em que o objeto
# fica parado num centro (rotas curtas têm menos paradas, mas o mesmo
# número de atualizações). Ficam em ciclo para não repetir em seguida.
_ESPERAS = [
    ("Objeto em processamento", "Objeto em processamento no centro de distribuição"),
    ("Aguardando transferência", "Objeto aguardando janela de transporte"),
    ("Objeto em conferência", "Conferência operacional dos volumes"),
    ("Consolidação de carga", "Objeto incluído em carga consolidada para transporte"),
    ("Objeto em separação", "Separação regional dos volumes"),
]

# Marcador de "trecho em trânsito": vira 1 ou 2 atualizações conforme o
# ritmo daquele trecho do cronograma (ver _distribuir_nos_dias).
_TRANSITO = object()


def _plano_45(rota, esperas):
    """
    Lista, na ordem, as etapas até a triagem no centro que atende o destino.

    `esperas` é quantas atualizações de espera entram no meio. Elas são
    divididas entre os centros por onde o objeto passa, sobrando mais para
    os mais próximos do destino.
    """
    centros = rota["centros"]
    origem = centros[0]["local"]

    por_centro = [esperas // len(centros)] * len(centros)
    for posicao in range(esperas % len(centros)):
        por_centro[-1 - posicao] += 1

    ciclo = iter(_ESPERAS * (esperas // len(_ESPERAS) + 1))

    def esperar(indice, local):
        return [(s, local, d) for s, d in (next(ciclo) for _ in range(por_centro[indice]))]

    plano = [
        ("Objeto coletado", origem, "Objeto coletado e liberado para transporte"),
        ("Objeto recebido na unidade de origem", origem,
         "Objeto recebido no centro de distribuição de origem"),
        ("Objeto em triagem", origem, "Objeto em triagem e conferência dos volumes"),
    ]
    plano += esperar(0, origem)
    plano.append(("Objeto liberado para transporte", origem,
                  "Objeto etiquetado e liberado para transferência"))

    for indice in range(1, len(centros)):
        saida, chegada = centros[indice - 1]["local"], centros[indice]["local"]
        ultimo = indice == len(centros) - 1

        plano.append(("Em transferência", saida,
                      f"Objeto saiu de {saida} com destino a {chegada}"))
        plano.append((_TRANSITO, saida, chegada))

        if ultimo:
            plano.append(("Centro de distribuição", chegada,
                          "Objeto chegou ao centro de distribuição de destino"))
            plano.append(("Objeto em triagem", chegada,
                          "Objeto em triagem e separação por área de entrega"))
            plano += esperar(indice, chegada)
        else:
            plano.append(("Objeto recebido no centro de distribuição", chegada,
                          "Objeto chegou ao centro de distribuição"))
            plano.append(("Objeto em triagem", chegada,
                          "Objeto em triagem e separação por destino"))
            plano += esperar(indice, chegada)
            plano.append(("Objeto liberado para transporte", chegada,
                          "Objeto liberado para transferência regional"))

    return plano


def _distribuir_nos_dias(plano, dias):
    """
    Encaixa cada etapa do plano num dia de atualização, em ordem.

    O trânsito entre estados dura no mínimo DIAS_EM_TRANSITO dias: na fase
    de atualização diária ele aparece duas vezes, na fase de 2 em 2 dias,
    uma. Devolve None se o plano não couber nos dias disponíveis.
    """
    sequencia = []
    posicao = 0

    for etapa in plano:
        if posicao >= len(dias):
            return None

        if etapa[0] is _TRANSITO:
            _, saida, chegada = etapa
            inicio = dias[posicao]
            sequencia.append(("Em trânsito", f"{saida} > {chegada}",
                              "Objeto em trânsito entre centros de distribuição", inicio))
            posicao += 1
            while posicao < len(dias) and dias[posicao] < inicio + Config.DIAS_EM_TRANSITO:
                sequencia.append(("Em trânsito", f"{saida} > {chegada}",
                                  f"Objeto segue em trânsito para {chegada}", dias[posicao]))
                posicao += 1
        else:
            status, local, descricao = etapa
            sequencia.append((status, local, descricao, dias[posicao]))
            posicao += 1

    return sequencia


def _montar_sequencia_45(rota):
    """Monta a lista (status, local, descrição, dia) do cronograma de 45 dias."""
    destino = rota["destino"]
    final = [
        ("Unidade de destino", "Objeto encaminhado para a unidade de entrega"),
        ("Objeto em conferência", "Conferência do endereço de entrega"),
        ("Aguardando roteirização", "Objeto aguardando definição da rota de entrega"),
        ("Saiu para entrega", "Objeto saiu para entrega ao destinatário"),
        ("Tentativa de entrega não realizada", DESCRICOES["Tentativa de entrega não realizada"]),
        ("Aguardando nova tentativa", "Objeto retornou à unidade e aguarda nova rota de entrega"),
        ("Nova tentativa de entrega", DESCRICOES["Nova tentativa de entrega"]),
        ("Saiu para entrega", "Objeto saiu para entrega ao destinatário"),
        ("Entregue", "Objeto entregue ao destinatário"),
    ]

    dias = Config.DIAS_ATUALIZACAO_45
    dias_iniciais = dias[: -len(final)]

    # Rotas curtas têm menos paradas: completa com atualizações de espera
    # até preencher todos os dias. Cada espera a mais pode tirar um dia de
    # trânsito duplo, então o total cresce de 0 em 0 ou de 1 em 1.
    for esperas in range(len(dias_iniciais) + 1):
        inicio = _distribuir_nos_dias(_plano_45(rota, esperas), dias_iniciais)
        if inicio is not None and len(inicio) == len(dias_iniciais):
            break
    else:
        raise RuntimeError("Rota não cabe no cronograma de 45 dias.")

    fim = [
        (status, destino, descricao, dia)
        for (status, descricao), dia in zip(final, dias[-len(final):])
    ]
    return inicio + fim


def _montar_sequencia_35(rota):
    """Cronograma antigo, no mesmo formato (status, local, descrição, dia)."""
    empresa = Config.EMPRESA_NOME
    return [
        (status, local, DESCRICOES.get(status, status).format(empresa=empresa), dia)
        for status, local, dia in _montar_sequencia(rota)
    ]


def gerar_movimentacoes(
    codigo_rastreio,
    data_cadastro,
    cidade,
    estado,
    cep=None,
    modelo_35_dias=False,
    coleta_18h=False,
):
    """
    Devolve a timeline completa como lista de dicionários, pronta para virar
    registros da tabela `movimentacoes`.

    Pedido novo usa o cronograma de 45 dias. `modelo_35_dias` mantém no
    cronograma antigo os pedidos que já foram cadastrados com ele.
    `coleta_18h` fixa a primeira atualização às 18:00 (pedido importado de
    noite ou de madrugada); as demais seguem o horário de sempre.
    """
    if isinstance(data_cadastro, datetime):
        data_cadastro = data_cadastro.date()

    rota = montar_rota(cidade, estado, cep)
    if modelo_35_dias:
        sequencia = _montar_sequencia_35(rota)
    else:
        sequencia = _montar_sequencia_45(rota)

    eventos = []
    for indice, (status, local, descricao, dias) in enumerate(sequencia):
        ordem = indice + 1
        dia = data_cadastro + timedelta(days=dias)
        if ordem == 1 and coleta_18h:
            hora = HORA_COLETA_NOITE
        else:
            hora = _hora_deterministica(codigo_rastreio, ordem)
        data_hora = datetime.combine(dia, hora)

        eventos.append(
            {
                "ordem": ordem,
                "data_hora": data_hora,
                "status": status,
                "local": local,
                "descricao": descricao,
            }
        )

    return eventos


HORA_COLETA_NOITE = time(hour=Config.HORA_COLETA_NOITE)


def data_de_cadastro_agora(agora_utc=None):
    """
    Data de cadastro de um pedido importado agora sem data na planilha.

    Devolve (data, coleta_18h). De dia: hoje, horário de sempre. De noite:
    hoje, coleta às 18:00. De madrugada: ontem, coleta às 18:00. A conta é
    feita no horário de Brasília, não no relógio do servidor.
    """
    agora_utc = agora_utc or datetime.now(timezone.utc)
    agora = agora_utc.astimezone(timezone(timedelta(hours=Config.FUSO_BRASILIA_UTC)))

    if agora.hour < Config.HORA_FIM_MADRUGADA:
        return agora.date() - timedelta(days=1), True
    if agora.hour >= Config.HORA_INICIO_NOITE:
        return agora.date(), True
    return agora.date(), False


def coleta_foi_as_18h(data_hora_primeira):
    """Pedido que já nasceu com coleta às 18:00 continua assim ao ser regravado."""
    return data_hora_primeira is not None and data_hora_primeira.time() == HORA_COLETA_NOITE


def usa_modelo_35_dias(pedido):
    """
    Diz se o pedido foi cadastrado no cronograma antigo de 35 dias.

    A previsão de entrega gravada denuncia o modelo: no antigo ela cai 35
    dias depois do cadastro. Pedido ainda sem timeline entra no modelo novo.
    """
    if not pedido.previsao_entrega or not pedido.data_cadastro:
        return False
    return (pedido.previsao_entrega - pedido.data_cadastro).days == Config.DURACAO_TOTAL_DIAS


def calcular_previsao(eventos):
    """A previsão de entrega é a data do último evento da timeline."""
    return eventos[-1]["data_hora"].date() if eventos else None


def resumo_publico(pedido, agora=None, incluir_previstas=False):
    """
    Monta o que a tela precisa mostrar, com os dados sensíveis mascarados.

    `incluir_previstas` separa os dois públicos:

      False (site) — o cliente só vê os eventos que JÁ aconteceram, como em
        qualquer transportadora real. Mostrar a rota inteira com data e hora
        futuras entregaria que o histórico é calculado, além de virar promessa
        de horário que ninguém fez.

      True (painel) — a operação vê a rota completa, incluindo o que ainda
        está por vir, que é justamente o que ela precisa para acompanhar.
    """
    agora = agora or datetime.now()
    cliente = pedido.cliente

    etapas = []
    for movimentacao in pedido.movimentacoes:
        concluida = movimentacao.data_hora <= agora

        if not concluida and not incluir_previstas:
            continue

        etapas.append(
            {
                "ordem": movimentacao.ordem,
                "status": movimentacao.status,
                "local": movimentacao.local,
                "descricao": movimentacao.descricao,
                "data": movimentacao.data_formatada,
                "hora": movimentacao.hora_formatada,
                "concluida": concluida,
            }
        )

    # Marca qual é a etapa atual (a última concluída).
    concluidas = [e for e in etapas if e["concluida"]]
    for etapa in etapas:
        etapa["atual"] = bool(concluidas) and etapa is concluidas[-1]

    # A timeline do cliente fica mais natural do mais recente para o mais
    # antigo — é assim que Correios e afins apresentam.
    if not incluir_previstas:
        etapas.reverse()

    return {
        "codigo": pedido.codigo_rastreio,
        "destinatario": cliente.nome,
        "destino": cliente.cidade_uf,
        "endereco": cliente.endereco_mascarado,
        "cpf": cliente.cpf_mascarado,
        "status": pedido.status_atual,
        "entregue": pedido.entregue,
        "progresso": pedido.progresso,
        "previsao_entrega": (
            pedido.previsao_entrega.strftime("%d/%m/%Y")
            if pedido.previsao_entrega
            else "a definir"
        ),
        "data_cadastro": pedido.data_cadastro.strftime("%d/%m/%Y"),
        "origem": pedido.origem,
        "etapas": etapas,
    }
