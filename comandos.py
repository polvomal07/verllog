"""
Comandos de terminal do projeto.

Rodam com `python -m flask <comando>` depois de definir FLASK_APP=app.py.
Servem tanto para operar o sistema sem abrir o navegador quanto para conferir
o comportamento durante o desenvolvimento.
"""

import click

from config import Config
from extensions import db


def registrar_comandos(app):
    @app.cli.command("iniciar-banco")
    @click.option("--zerar", is_flag=True, help="Apaga tudo antes de recriar.")
    def iniciar_banco(zerar):
        """Cria as tabelas do banco de dados."""
        if zerar:
            db.drop_all()
            click.echo("Tabelas antigas removidas.")
        db.create_all()
        click.echo("Banco pronto: clientes, pedidos e movimentacoes.")

    @app.cli.command("conferir")
    @click.argument("arquivo", type=click.Path(exists=True, dir_okay=False))
    def conferir(arquivo):
        """Analisa uma planilha SEM gravar nada, para ver se ela está pronta."""
        from services import gerador_codigo
        from services.importador import (
            COLUNAS_OBRIGATORIAS,
            ErroDePlanilha,
            _normalizar_cabecalho,
            _texto,
            ler_arquivo,
        )

        try:
            df = _normalizar_cabecalho(ler_arquivo(arquivo))
        except ErroDePlanilha as erro:
            click.secho(str(erro), fg="red")
            raise SystemExit(1)

        click.echo("")
        click.secho("=== CONFERÊNCIA DA PLANILHA ===", bold=True)
        click.echo(f"Arquivo ....... {arquivo}")
        click.echo(f"Linhas ........ {len(df)}")
        click.echo("")

        click.secho("Colunas encontradas:", bold=True)
        for coluna in df.columns:
            marca = "ok " if coluna in Config.COLUNAS_PLANILHA else "extra"
            click.echo(f"  [{marca}] {coluna}")

        faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in df.columns]
        click.echo("")
        if faltando:
            click.secho("FALTAM colunas obrigatórias: " + ", ".join(faltando), fg="red")
            click.echo("A importação seria cancelada. Renomeie as colunas.")
            click.echo("")
            return

        click.secho("Todas as colunas obrigatórias estão presentes.", fg="green")

        if "codigo_rastreio" in df.columns:
            invalidos = []
            vazios = 0
            vistos = set()
            repetidos = 0

            for indice, linha in df.iterrows():
                bruto = gerador_codigo.limpar(linha.get("codigo_rastreio"))
                if not bruto:
                    vazios += 1
                elif not gerador_codigo.validar_estrito(bruto):
                    invalidos.append(
                        (indice + 2, bruto, gerador_codigo.motivo_invalido(bruto))
                    )
                elif bruto in vistos:
                    repetidos += 1
                else:
                    vistos.add(bruto)

            click.echo("")
            click.secho("Códigos de rastreio:", bold=True)
            click.echo(f"  válidos ........... {len(vistos)}")
            click.echo(f"  serão gerados ..... {vazios}")
            click.echo(f"  repetidos ......... {repetidos}")
            click.echo(f"  inválidos ......... {len(invalidos)}")

            for numero, codigo, motivo in invalidos[:15]:
                click.secho(f"    linha {numero:>3}  {codigo:<18} {motivo}", fg="red")
            if len(invalidos) > 15:
                click.echo(f"    ... e mais {len(invalidos) - 15}")

        click.echo("")
        click.secho("Primeiras linhas:", bold=True)
        for _, linha in df.head(3).iterrows():
            nome = _texto(linha.get("nome"))
            cidade = _texto(linha.get("cidade"))
            estado = _texto(linha.get("estado"))
            click.echo(f"  {nome[:28]:<30} {cidade}/{estado}")
        click.echo("")

    @app.cli.command("importar")
    @click.argument("arquivo", type=click.Path(exists=True, dir_okay=False))
    def importar(arquivo):
        """Importa uma planilha .xlsx, .xls ou .csv de clientes."""
        from services.importador import ErroDePlanilha, importar_planilha

        try:
            relatorio = importar_planilha(arquivo)
        except ErroDePlanilha as erro:
            click.secho(f"Importação cancelada: {erro}", fg="red")
            raise SystemExit(1)

        click.echo("")
        click.secho("=== RELATÓRIO DA IMPORTAÇÃO ===", bold=True)
        click.echo(f"Linhas lidas .......... {relatorio['total_linhas']}")
        click.secho(f"Adicionados ........... {relatorio['adicionados']}", fg="green")
        click.secho(f"Atualizados ........... {relatorio['atualizados']}", fg="yellow")
        click.echo(f"Linhas em branco ...... {relatorio.get('ignoradas', 0)}")
        click.secho(f"Com erro .............. {len(relatorio['erros'])}", fg="red")

        if relatorio["codigos_gerados"]:
            click.echo(
                f"\nCódigos gerados automaticamente: "
                f"{len(relatorio['codigos_gerados'])}"
            )
            for codigo in relatorio["codigos_gerados"][:10]:
                click.echo(f"  {codigo}")

        if relatorio["erros"]:
            click.echo("")
            click.secho("Linhas com problema:", fg="red", bold=True)
            for erro in relatorio["erros"]:
                click.echo(
                    f"  linha {erro['linha']:>3}  {erro['codigo']:<16} {erro['motivo']}"
                )
        click.echo("")

    @app.cli.command("regravar-rotas")
    def regravar_rotas():
        """
        Recalcula o trajeto e a timeline de todos os pedidos.

        Use depois de mexer na malha (services/rotas.py) ou no intervalo entre
        etapas. A data de cadastro de cada pedido é preservada — só o caminho
        e os eventos são refeitos.
        """
        from models import Pedido
        from services.importador import _regravar_movimentacoes

        pedidos = Pedido.query.order_by(Pedido.id).all()
        if not pedidos:
            click.echo("Nenhum pedido no banco.")
            return

        for pedido in pedidos:
            _regravar_movimentacoes(pedido, pedido.cliente)

        db.session.commit()

        exemplo = pedidos[0]
        click.echo("")
        click.secho(f"{len(pedidos)} pedidos recalculados.", fg="green")
        click.echo(f"Origem agora: {exemplo.origem}")
        click.echo("")

    @app.cli.command("espalhar-datas")
    @click.option("--ate", default=20, help="Quantos dias para trás distribuir.")
    def espalhar_datas(ate):
        """
        Distribui a data de cadastro dos pedidos ao longo dos últimos dias.

        Serve para demonstração: a planilha de origem não traz data, então
        todos os pedidos nascem hoje e ficam parados na primeira etapa. Isso
        espalha as datas e regrava a timeline, deixando pedidos em todos os
        estágios — de recém-postado a entregue.
        """
        from datetime import date, timedelta

        from models import Pedido
        from services.importador import _regravar_movimentacoes

        pedidos = Pedido.query.order_by(Pedido.id).all()
        if not pedidos:
            click.echo("Nenhum pedido no banco. Importe uma planilha primeiro.")
            return

        hoje = date.today()
        total = len(pedidos)

        for indice, pedido in enumerate(pedidos):
            # Espalha de forma regular entre 0 e `ate` dias atrás.
            dias_atras = round(indice * ate / max(total - 1, 1))
            pedido.data_cadastro = hoje - timedelta(days=dias_atras)
            _regravar_movimentacoes(pedido, pedido.cliente)

        db.session.commit()

        contagem = {}
        for pedido in pedidos:
            contagem[pedido.status_atual] = contagem.get(pedido.status_atual, 0) + 1

        click.echo("")
        click.secho(f"{total} pedidos redistribuídos nos últimos {ate} dias.", fg="green")
        click.echo("")
        for status in Config.FLUXO_STATUS:
            if status in contagem:
                click.echo(f"  {contagem[status]:>4}  {status}")
        click.echo("")

    @app.cli.command("listar")
    @click.option("--limite", default=20, help="Quantos pedidos mostrar.")
    def listar(limite):
        """Mostra os pedidos cadastrados com o status calculado agora."""
        from models import Pedido

        pedidos = Pedido.query.order_by(Pedido.id).limit(limite).all()
        if not pedidos:
            click.echo("Nenhum pedido cadastrado. Importe uma planilha primeiro.")
            return

        click.echo("")
        cabecalho = (
            f"{'CÓDIGO':<16} {'CLIENTE':<24} {'DESTINO':<22} "
            f"{'STATUS':<24} {'PREVISÃO':<10}"
        )
        click.secho(cabecalho, bold=True)
        click.echo("-" * len(cabecalho))

        for pedido in pedidos:
            previsao = (
                pedido.previsao_entrega.strftime("%d/%m/%Y")
                if pedido.previsao_entrega
                else "-"
            )
            click.echo(
                f"{pedido.codigo_rastreio:<16} "
                f"{pedido.cliente.nome[:23]:<24} "
                f"{pedido.destino[:21]:<22} "
                f"{pedido.status_atual:<24} "
                f"{previsao:<10}"
            )
        click.echo("")

    @app.cli.command("rastrear")
    @click.argument("codigo")
    def rastrear(codigo):
        """Mostra a timeline completa de um código, direto no terminal."""
        from models import Pedido
        from services import gerador_codigo
        from services.rastreamento import resumo_publico

        codigo = gerador_codigo.normalizar(codigo)

        if not gerador_codigo.validar(codigo):
            click.secho(
                f"Código fora do padrão: {gerador_codigo.motivo_invalido(codigo)}",
                fg="red",
            )
            raise SystemExit(1)

        pedido = Pedido.query.filter_by(codigo_rastreio=codigo).first()
        if pedido is None:
            click.secho("Código de rastreamento não encontrado.", fg="red")
            raise SystemExit(1)

        dados = resumo_publico(pedido)

        click.echo("")
        click.secho(f"  {dados['codigo']}", bold=True)
        click.echo(f"  Destinatário .... {dados['destinatario']}")
        click.echo(f"  Destino ......... {dados['destino']}")
        click.secho(f"  Status .......... {dados['status'].upper()}", fg="cyan")
        click.echo(f"  Previsão ........ {dados['previsao_entrega']}")
        click.echo(f"  Progresso ....... {dados['progresso']}%")
        click.echo("")

        for etapa in dados["etapas"]:
            marca = "[x]" if etapa["concluida"] else "[ ]"
            cor = "green" if etapa["concluida"] else None
            click.secho(
                f"  {marca} {etapa['status']:<24} "
                f"{etapa['data']} {etapa['hora']}  {etapa['local']}",
                fg=cor,
            )
        click.echo("")
