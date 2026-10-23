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

from sqlalchemy import func
from sqlalchemy.orm import joinedload, lazyload

from config import Config
from extensions import db
from models import Cliente, Movimentacao, Pedido
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


def _montar_estatisticas(pedidos, status):
    """
    Conta os pedidos por status.

    Como o status é calculado (e não uma coluna), a contagem é feita em Python.
    Com o volume de um trabalho acadêmico isso é instantâneo, e em troca o
    número nunca fica defasado em relação à data de hoje.
    """
    contagem = {}
    for pedido in pedidos:
        contagem[status[pedido.id]] = contagem.get(status[pedido.id], 0) + 1

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


# Traz o cliente na MESMA consulta dos pedidos. Sem isso, cada linha da
# tabela buscava o seu cliente separadamente: com o banco em São Paulo e o
# site em Oregon, mil pedidos levavam quase três minutos para abrir o painel.
# O lazyload impede que, ao trazer o cliente, venham junto de novo todos os
# pedidos dele e as movimentações desses pedidos.
_COM_CLIENTE = (joinedload(Pedido.cliente).lazyload(Cliente.pedidos),)


def _status_dos_pedidos():
    """
    Status atual de cada pedido, {pedido_id: status}, calculado pelo banco.

    Mesma regra de Pedido.status_atual: a última movimentação que já
    aconteceu ou, se nenhuma aconteceu ainda, a primeira. Carregar as
    movimentações de todos os pedidos para isso (45 por pedido) deixava o
    painel lento; aqui o banco devolve uma linha por pedido.
    """
    agora = datetime.now()

    def status_na_ordem(ordem_por_pedido):
        alvo = ordem_por_pedido.subquery()
        linhas = db.session.query(Movimentacao.pedido_id, Movimentacao.status).join(
            alvo,
            (Movimentacao.pedido_id == alvo.c.pedido_id)
            & (Movimentacao.ordem == alvo.c.ordem),
        )
        return dict(linhas.all())

    ultima_ocorrida = status_na_ordem(
        db.session.query(
            Movimentacao.pedido_id, func.max(Movimentacao.ordem).label("ordem")
        )
        .filter(Movimentacao.data_hora <= agora)
        .group_by(Movimentacao.pedido_id)
    )
    primeira = status_na_ordem(
        db.session.query(
            Movimentacao.pedido_id, func.min(Movimentacao.ordem).label("ordem")
        ).group_by(Movimentacao.pedido_id)
    )
    return {**primeira, **ultima_ocorrida}


@admin_bp.route("/")
@login_obrigatorio
def painel():
    busca = request.args.get("busca", "").strip()

    todos = (
        Pedido.query.options(*_COM_CLIENTE, lazyload(Pedido.movimentacoes))
        .order_by(Pedido.id.desc())
        .all()
    )
    status = _status_dos_pedidos()
    for pedido in todos:
        status.setdefault(pedido.id, "Pedido postado")
    estatisticas = _montar_estatisticas(todos, status)

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
            or alvo in status[p.id].lower()
        ]
    else:
        pedidos = todos

    return render_template(
        "admin/painel.html",
        pedidos=pedidos,
        status=status,
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

    # O relatório vai no cookie da sessão, que tem limite de 4 KB. Em planilha
    # grande a lista completa de erros e códigos gerados passaria disso e o
    # navegador descartaria o cookie, então só as primeiras linhas vão junto.
    session["ultimo_relatorio"] = dict(
        relatorio,
        total_erros=len(relatorio["erros"]),
        total_gerados=len(relatorio["codigos_gerados"]),
        erros=relatorio["erros"][:20],
        codigos_gerados=relatorio["codigos_gerados"][:5],
    )

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


def _pedidos_marcados():
    """Pedidos marcados no formulário (a seleção é por pedido, não por cliente)."""
    ids = {int(valor) for valor in request.form.getlist("pedidos") if valor.isdigit()}
    if not ids:
        return []
    return (
        Pedido.query.options(*_COM_CLIENTE)
        .filter(Pedido.id.in_(ids))
        .order_by(Pedido.id.desc())
        .all()
    )


def _voltar_ao_painel():
    busca = request.form.get("busca", "").strip()
    return redirect(url_for("admin.painel", busca=busca) if busca else url_for("admin.painel"))


@admin_bp.route("/exportar", methods=["POST"])
@login_obrigatorio
def exportar():
    """
    Gera um PDF com o rastreio dos pedidos marcados, igual ao que o cliente
    vê no site. Cada pedido começa numa página nova.
    """
    pedidos = _pedidos_marcados()

    if not pedidos:
        flash("Selecione pelo menos um pedido para exportar.", "erro")
        return _voltar_ao_painel()

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
    Apaga só os pedidos marcados, com as movimentações deles.

    Os outros pedidos do mesmo cliente continuam. O cadastro do cliente só
    sai quando o último pedido dele é apagado, para não sobrar cliente vazio.
    A exclusão é definitiva.
    """
    pedidos = _pedidos_marcados()

    if not pedidos:
        flash("Selecione pelo menos um pedido para apagar.", "erro")
        return _voltar_ao_painel()

    clientes = {pedido.cliente for pedido in pedidos}
    for pedido in pedidos:
        # delete() leva as movimentações junto (cascade no model).
        db.session.delete(pedido)
    db.session.flush()

    # Conta no banco, e não pela lista em memória, que ainda traz os
    # pedidos recém-apagados até o commit.
    for cliente in clientes:
        if Pedido.query.filter_by(cliente_id=cliente.id).count() == 0:
            db.session.delete(cliente)
    db.session.commit()

    flash(
        "Apagados: "
        + str(len(pedidos))
        + (" pedido." if len(pedidos) == 1 else " pedidos."),
        "sucesso",
    )
    return _voltar_ao_painel()


@admin_bp.route("/gerar-codigo")
@login_obrigatorio
def gerar_codigo():
    """Gera um código único, para quem precisar cadastrar um pedido à mão."""
    codigo = gerador_codigo.gerar_unico()
    flash("Código gerado: " + codigo, "sucesso")
    return redirect(url_for("admin.painel"))
