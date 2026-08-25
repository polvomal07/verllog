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
from datetime import date, datetime, time, timedelta

from config import Config
from services.rotas import montar_rota

# Descrição amigável de cada status do fluxo.
DESCRICOES = {
    "Pedido recebido": "Pedido recebido pela {empresa}",
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
        ("Pedido recebido", origem, cronograma["Pedido recebido"]),
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


def gerar_movimentacoes(codigo_rastreio, data_cadastro, cidade, estado, cep=None):
    """
    Devolve a timeline completa como lista de dicionários, pronta para virar
    registros da tabela `movimentacoes`.

    O dia de cada etapa vem do CRONOGRAMA em config.py. Da postagem à entrega
    são DURACAO_TOTAL_DIAS dias.
    """
    if isinstance(data_cadastro, datetime):
        data_cadastro = data_cadastro.date()

    rota = montar_rota(cidade, estado, cep)
    sequencia = _montar_sequencia(rota)

    eventos = []
    for indice, (status, local, dias) in enumerate(sequencia):
        ordem = indice + 1
        dia = data_cadastro + timedelta(days=dias)
        data_hora = datetime.combine(dia, _hora_deterministica(codigo_rastreio, ordem))

        eventos.append(
            {
                "ordem": ordem,
                "data_hora": data_hora,
                "status": status,
                "local": local,
                "descricao": DESCRICOES.get(status, status).format(
                    empresa=Config.EMPRESA_NOME
                ),
            }
        )

    return eventos


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
