"""
Site público (Fase 8).

Duas telas: a home com o campo de busca e a página de resultado do
rastreamento. O usuário final nunca vê erro técnico — código fora do padrão e
código inexistente caem na mesma mensagem educada.
"""

from flask import Blueprint, jsonify, render_template, request

from models import Cliente, Movimentacao, Pedido
from services import gerador_codigo
from services.rastreamento import resumo_publico

publico_bp = Blueprint("publico", __name__)


@publico_bp.route("/")
def index():
    return render_template("index.html")


@publico_bp.route("/sobre")
def sobre():
    return render_template("sobre.html")


@publico_bp.route("/rastreamento")
def rastreamento():
    """
    Resultado da consulta. O código vem pela URL (?codigo=...) para que a
    página possa ser recarregada e compartilhada, como em transportadora real.
    """
    codigo_digitado = request.args.get("codigo", "").strip()

    # Sem código na URL, a página mostra o formulário de busca. Com código,
    # mostra o resultado. É a mesma rota para o usuário não precisar decorar
    # dois endereços diferentes.
    if not codigo_digitado:
        return render_template("rastrear.html")

    codigo = gerador_codigo.normalizar(codigo_digitado)

    # Formato errado e código inexistente recebem a MESMA resposta. Dizer
    # "esse código não existe no formato certo" só ajudaria quem quisesse
    # descobrir códigos válidos por tentativa.
    if not gerador_codigo.validar(codigo):
        return (
            render_template(
                "rastreamento.html", encontrado=False, codigo=codigo_digitado
            ),
            404,
        )

    pedido = Pedido.query.filter_by(codigo_rastreio=codigo).first()

    if pedido is None:
        return (
            render_template(
                "rastreamento.html", encontrado=False, codigo=codigo_digitado
            ),
            404,
        )

    return render_template(
        "rastreamento.html", encontrado=True, dados=resumo_publico(pedido)
    )


@publico_bp.route("/health")
def health():
    """Checagem rápida do estado do sistema."""
    return jsonify(
        {
            "status": "ok",
            "clientes": Cliente.query.count(),
            "pedidos": Pedido.query.count(),
            "movimentacoes": Movimentacao.query.count(),
        }
    )
