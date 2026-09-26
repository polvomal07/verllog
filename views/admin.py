"""
Painel administrativo (Fase 9).

Login simples, guardado na sessão — suficiente para demonstração acadêmica,
e é assim que está documentado no README. Não é um sistema de autenticação
para uso real: não há hash de senha nem cadastro de usuários.
"""

from datetime import date, datetime
from functools import wraps

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

from config import Config
from extensions import db
from models import Cliente, Pedido
from services import gerador_codigo
from services.exportador_pdf import gerar_pdf
from services.importador import ErroDePlanilha, importar_planilha
from services.rastreamento import resumo_publico

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def login_obrigatorio(funcao):
    """Redireciona para o login quem tentar entrar sem estar autenticado."""

    @wraps(funcao)
    def envolvida(*args, **kwargs):
        if not session.get("admin_logado"):
            return redirect(url_for("admin.login", proxima=request.path))
        return funcao(*args, **kwargs)

    return envolvida


# ----------------------------------------------------------------------
# Autenticação
# ----------------------------------------------------------------------


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        senha = request.form.get("senha", "")

        if (
            usuario == current_app.config["ADMIN_USUARIO"]
            and senha == current_app.config["ADMIN_SENHA"]
        ):
            session["admin_logado"] = True
            destino = request.args.get("proxima") or url_for("admin.painel")
            return redirect(destino)

        flash("Usuário ou senha incorretos.", "erro")

    return render_template("admin/login.html")


@admin_bp.route("/logout")
def logout():
    session.pop("admin_logado", None)
    return redirect(url_for("publico.index"))


# ----------------------------------------------------------------------
# Painel
# ----------------------------------------------------------------------


def _montar_estatisticas(pedidos):
    """
    Conta os pedidos por status.

    Como o status é calculado (e não uma coluna), a contagem é feita em Python.
    Com o volume de um trabalho acadêmico isso é instantâneo, e em troca o
    número nunca fica defasado em relação à data de hoje.
    """
    contagem = {}
    for pedido in pedidos:
        contagem[pedido.status_atual] = contagem.get(pedido.status_atual, 0) + 1

    hoje = date.today()

    return {
        "total": len(pedidos),
        "entregues": contagem.get("Entregue", 0),
        "saiu_para_entrega": contagem.get("Saiu para entrega", 0),
        "em_transferencia": contagem.get("Em transferência", 0),
        "em_transito": sum(
            quantidade
            for status, quantidade in contagem.items()
            if status not in ("Entregue", "Pedido postado")
        ),
        "novos_hoje": sum(1 for p in pedidos if p.data_cadastro == hoje),
        "por_status": contagem,
    }


@admin_bp.route("/")
@login_obrigatorio
def painel():
    busca = request.args.get("busca", "").strip()

    todos = Pedido.query.order_by(Pedido.id.desc()).all()
    estatisticas = _montar_estatisticas(todos)

    # A busca aceita código, nome do cliente ou cidade.
    if busca:
        alvo = busca.lower()
        codigo_buscado = gerador_codigo.normalizar(busca)
        pedidos = [
            p
            for p in todos
            if codigo_buscado and codigo_buscado in p.codigo_rastreio
            or alvo in p.cliente.nome.lower()
            or alvo in p.cliente.cidade.lower()
            or alvo in p.status_atual.lower()
        ]
    else:
        pedidos = todos

    return render_template(
        "admin/painel.html",
        pedidos=pedidos,
        estatisticas=estatisticas,
        busca=busca,
        relatorio=session.pop("ultimo_relatorio", None),
    )


@admin_bp.route("/pedido/<codigo>")
@login_obrigatorio
def detalhe_pedido(codigo):
    codigo = gerador_codigo.normalizar(codigo)
    pedido = Pedido.query.filter_by(codigo_rastreio=codigo).first()

    if pedido is None:
        flash("Pedido não encontrado.", "erro")
        return redirect(url_for("admin.painel"))

    return render_template(
        "admin/pedido.html",
        pedido=pedido,
        cliente=pedido.cliente,
        dados=resumo_publico(pedido, incluir_previstas=True),
    )


# ----------------------------------------------------------------------
# Importação
# ----------------------------------------------------------------------


@admin_bp.route("/importar", methods=["POST"])
@login_obrigatorio
def importar():
    arquivo = request.files.get("planilha")

    if arquivo is None or not arquivo.filename:
        flash("Escolha um arquivo antes de clicar em importar.", "erro")
        return redirect(url_for("admin.painel"))

    nome_seguro = secure_filename(arquivo.filename)
    extensao = "." + nome_seguro.rsplit(".", 1)[-1].lower() if "." in nome_seguro else ""

    if extensao not in Config.EXTENSOES_PERMITIDAS:
        flash(
            "Formato não aceito: "
            + (extensao or "sem extensão")
            + ". Use .xlsx, .xls ou .csv.",
            "erro",
        )
        return redirect(url_for("admin.painel"))

    # Guarda o arquivo com carimbo de data para manter o histórico de envios.
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    destino = current_app.config["UPLOAD_FOLDER"] / (carimbo + "_" + nome_seguro)
    arquivo.save(destino)

    try:
        relatorio = importar_planilha(destino)
    except ErroDePlanilha as erro:
        flash(str(erro), "erro")
        return redirect(url_for("admin.painel"))

    relatorio["arquivo"] = nome_seguro
    session["ultimo_relatorio"] = relatorio

    resumo = (
        str(relatorio["adicionados"])
        + " adicionados, "
        + str(relatorio["atualizados"])
        + " atualizados, "
        + str(len(relatorio["erros"]))
        + " com erro."
    )
    flash("Importação concluída: " + resumo, "sucesso")

    return redirect(url_for("admin.painel"))


# ----------------------------------------------------------------------
# Exportação em PDF
# ----------------------------------------------------------------------


@admin_bp.route("/exportar", methods=["POST"])
@login_obrigatorio
def exportar():
    """
    Gera um PDF com o rastreio dos clientes marcados, igual ao que eles veem
    no site. Cada pedido começa numa página nova.
    """
    ids = {int(valor) for valor in request.form.getlist("clientes") if valor.isdigit()}
    busca = request.form.get("busca", "").strip()

    pedidos = (
        Pedido.query.filter(Pedido.cliente_id.in_(ids)).order_by(Pedido.id.desc()).all()
        if ids
        else []
    )

    if not pedidos:
        flash("Selecione pelo menos um cliente para exportar.", "erro")
        return redirect(url_for("admin.painel", busca=busca) if busca else url_for("admin.painel"))

    if len(pedidos) == 1:
        nome_arquivo = "rastreio-" + pedidos[0].codigo_rastreio + ".pdf"
    else:
        nome_arquivo = "rastreios-" + datetime.now().strftime("%Y%m%d-%H%M") + ".pdf"

    return Response(
        gerar_pdf(pedidos),
        mimetype="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="' + nome_arquivo + '"'},
    )


# ----------------------------------------------------------------------
# Exclusão
# ----------------------------------------------------------------------


@admin_bp.route("/apagar", methods=["POST"])
@login_obrigatorio
def apagar():
    """
    Apaga os clientes marcados, com todos os pedidos e movimentações deles.

    A exclusão é definitiva. Pedidos e movimentações saem junto por causa do
    cascade="all, delete-orphan" nos models, então não sobra nada solto.
    """
    ids = {int(valor) for valor in request.form.getlist("clientes") if valor.isdigit()}
    busca = request.form.get("busca", "").strip()
    destino = url_for("admin.painel", busca=busca) if busca else url_for("admin.painel")

    if not ids:
        flash("Selecione pelo menos um cliente para apagar.", "erro")
        return redirect(destino)

    clientes = Cliente.query.filter(Cliente.id.in_(ids)).all()

    if not clientes:
        flash("Os clientes selecionados não existem mais.", "erro")
        return redirect(destino)

    total_pedidos = sum(len(cliente.pedidos) for cliente in clientes)
    for cliente in clientes:
        db.session.delete(cliente)
    db.session.commit()

    flash(
        "Apagados: "
        + str(len(clientes))
        + (" cliente" if len(clientes) == 1 else " clientes")
        + " e "
        + str(total_pedidos)
        + (" pedido." if total_pedidos == 1 else " pedidos."),
        "sucesso",
    )
    return redirect(destino)


@admin_bp.route("/gerar-codigo")
@login_obrigatorio
def gerar_codigo():
    """Gera um código único, para quem precisar cadastrar um pedido à mão."""
    codigo = gerador_codigo.gerar_unico()
    flash("Código gerado: " + codigo, "sucesso")
    return redirect(url_for("admin.painel"))
