"""
Importação da planilha de clientes (Fase 3).

Lê um .xlsx, valida linha a linha e grava no banco sem duplicar nada.
O código de rastreamento é a chave: se já existe, o registro é ATUALIZADO;
se não existe, é ADICIONADO. Reimportar a mesma planilha não cria cópias.

Devolve um relatório com quantos entraram, quantos foram atualizados e quais
linhas deram problema — com o número da linha como aparece no Excel.
"""

import unicodedata
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import delete, insert
from sqlalchemy.orm import lazyload

from config import Config
from extensions import db
from models import Cliente, Movimentacao, Pedido
from services import gerador_codigo
from services.rastreamento import calcular_previsao, gerar_movimentacoes
from services.rotas import montar_rota

# Colunas sem as quais a planilha não pode ser processada.
COLUNAS_OBRIGATORIAS = ["codigo_rastreio", "nome", "cidade", "estado"]


class ErroDePlanilha(Exception):
    """Problema que invalida o arquivo inteiro (ex.: falta uma coluna)."""


# ----------------------------------------------------------------------
# Leitura e normalização
# ----------------------------------------------------------------------


def ler_arquivo(caminho_arquivo):
    """
    Lê a planilha, seja ela .xlsx, .xls ou .csv.

    CSV brasileiro é traiçoeiro em dois pontos, e os dois são tratados aqui:
    o separador costuma ser ';' em vez de ',' (porque o Excel em português usa
    a vírgula como decimal), e a acentuação vem em UTF-8 ou em Windows-1252
    dependendo de quem exportou. Tentamos as combinações até uma funcionar.
    """
    caminho = Path(caminho_arquivo)
    extensao = caminho.suffix.lower()

    if extensao in (".xlsx", ".xls"):
        return pd.read_excel(caminho, dtype=object)

    if extensao in (".csv", ".txt"):
        ultimo_erro = None
        # utf-8-sig remove o BOM que o Excel adiciona ao salvar como CSV UTF-8.
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                df = pd.read_csv(
                    caminho,
                    dtype=object,
                    sep=None,          # detecta ',' ou ';' sozinho
                    engine="python",
                    encoding=encoding,
                    skip_blank_lines=True,
                )
                # Uma única coluna significa que o separador não foi detectado.
                if len(df.columns) > 1:
                    return df
                ultimo_erro = "só foi encontrada uma coluna — separador incorreto?"
            except Exception as erro:
                ultimo_erro = str(erro)
                continue

        raise ErroDePlanilha("Não foi possível ler o CSV: " + str(ultimo_erro))

    raise ErroDePlanilha(
        "Formato não suportado: " + extensao + ". Use .xlsx, .xls ou .csv."
    )


def _limpar_nome_coluna(nome):
    texto = str(nome).strip().lower().replace(" ", "_")
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c))


# Planilha de operação real raramente usa os nomes de coluna do manual. Aqui
# ficam os apelidos aceitos para cada campo — assim dá para importar o arquivo
# como ele já existe, sem obrigar ninguém a renomear cabeçalho na mão.
SINONIMOS = {
    "codigo_rastreio": [
        "cod_rastreio", "cod_rastreamento", "codigo", "codigo_de_rastreio",
        "codigo_rastreamento", "codigo_de_rastreamento", "rastreio",
        "rastreamento", "cod", "codigo_envio",
    ],
    "nome": [
        "cliente", "nome_cliente", "nome_completo", "destinatario",
        "nome_do_cliente", "comprador",
    ],
    "cpf": ["documento", "cpf_cliente", "doc"],
    "endereco": [
        "endereco_completo", "logradouro", "rua", "endereco_de_entrega",
        "endereco_entrega",
    ],
    "numero": ["num", "n", "numero_casa", "nro"],
    "bairro": ["bairro_entrega"],
    "cidade": ["municipio", "cidade_entrega"],
    "estado": ["uf", "estado_entrega", "sigla_estado"],
    "cep": ["cep_entrega", "codigo_postal"],
    "data_cadastro": [
        "data", "data_pedido", "data_do_pedido", "data_envio", "data_da_compra",
        "data_compra", "criado_em",
    ],
}


def _aplicar_sinonimos(colunas):
    """
    Renomeia as colunas conhecidas pelos apelidos, sem tocar nas demais.

    Uma coluna só é renomeada se o nome oficial ainda não estiver presente —
    se a planilha já tem 'nome' E 'cliente', o 'nome' original é preservado.
    """
    resultado = list(colunas)
    presentes = set(resultado)

    for oficial, apelidos in SINONIMOS.items():
        if oficial in presentes:
            continue
        for indice, coluna in enumerate(resultado):
            if coluna in apelidos:
                resultado[indice] = oficial
                presentes.add(oficial)
                break

    return resultado


def _normalizar_cabecalho(df):
    """
    Padroniza o cabeçalho em dois passos: limpa acento/caixa/espaço e depois
    traduz os apelidos conhecidos ('CLIENTE' -> 'nome', 'CÓD RASTREIO' ->
    'codigo_rastreio', 'ENDEREÇO COMPLETO' -> 'endereco').
    """
    df.columns = _aplicar_sinonimos([_limpar_nome_coluna(c) for c in df.columns])
    return df


def _texto(valor):
    """Converte célula do pandas em texto limpo, tratando vazio/NaN como ""."""
    if valor is None:
        return ""
    try:
        if pd.isna(valor):
            return ""
    except (TypeError, ValueError):
        pass

    texto = str(valor).strip()
    # O pandas costuma ler inteiros como 120.0 — corrige para "120".
    if texto.endswith(".0") and texto[:-2].isdigit():
        texto = texto[:-2]
    return texto


def _converter_data(valor):
    """
    Aceita data do Excel, dd/mm/aaaa ou aaaa-mm-dd.

    Devolve None quando a célula está vazia. Quem chama decide o que fazer com
    isso: pedido novo ganha a data de hoje, pedido que já existe mantém a data
    que tinha. Essa distinção é o que impede que reenviar uma planilha sem
    coluna de data zere o progresso de todos os pedidos antigos.
    """
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor

    texto = _texto(valor)
    if not texto:
        return None

    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue

    # Última tentativa: datas que o pandas devolveu como texto ISO com hora.
    try:
        return pd.to_datetime(texto, dayfirst=True).date()
    except Exception as erro:
        raise ValueError(
            "data de cadastro em formato não reconhecido: " + texto
        ) from erro


# ----------------------------------------------------------------------
# Persistência
# ----------------------------------------------------------------------


def _aplicar_dados_cliente(cliente, dados):
    cliente.nome = dados["nome"]
    cliente.cpf = dados["cpf"] or cliente.cpf
    cliente.endereco = dados["endereco"]
    cliente.numero = dados["numero"]
    cliente.bairro = dados["bairro"]
    cliente.cidade = dados["cidade"]
    cliente.estado = dados["estado"]
    cliente.cep = dados["cep"]
    return cliente


def _regravar_movimentacoes(pedido, cliente):
    """
    (Re)gera a timeline do pedido a partir da rota e da data de cadastro.

    Chamado quando o pedido é criado e sempre que o destino ou a data mudarem,
    já que qualquer um dos dois altera o trajeto inteiro.
    """
    Movimentacao.query.filter_by(pedido_id=pedido.id).delete()

    eventos = gerar_movimentacoes(
        pedido.codigo_rastreio,
        pedido.data_cadastro,
        cliente.cidade,
        cliente.estado,
        cliente.cep,
    )

    for evento in eventos:
        db.session.add(Movimentacao(pedido_id=pedido.id, **evento))

    rota = montar_rota(cliente.cidade, cliente.estado, cliente.cep)
    pedido.origem = rota["origem"]
    pedido.destino = rota["destino"]
    pedido.previsao_entrega = calcular_previsao(eventos)


# ----------------------------------------------------------------------
# Importação
#
# O site roda nos EUA e o banco fica em São Paulo: cada ida e volta ao banco
# custa perto de 0,2 s. Gravar linha por linha (como era antes) fazia uns 17
# acessos por pedido, e planilha com mais de umas 40 linhas estourava o tempo
# limite do servidor. Por isso a importação trabalha em três etapas:
#
#   1. valida todas as linhas só em memória, sem tocar no banco;
#   2. carrega de uma vez os clientes e pedidos que já existem;
#   3. grava em blocos, com poucas consultas e um único commit por bloco.
#
# Se um bloco falhar no banco, só ele é refeito linha a linha, para que a
# linha ruim vire erro no relatório sem levar as boas junto.
# ----------------------------------------------------------------------

TAMANHO_DO_BLOCO = 250


def _validar_linhas(df, gerar_codigo_se_vazio, relatorio):
    """
    Etapa 1: lê e valida cada linha em memória. Devolve as linhas boas, com
    o código já limpo (os que faltam ficam None para gerar depois).
    """
    linhas_validas = []
    codigos_desta_planilha = set()

    # Colunas que o sistema realmente lê — usadas para detectar linha sem dados.
    campos_uteis = [c for c in Config.COLUNAS_PLANILHA if c in df.columns]

    for indice, linha in df.iterrows():
        # +2 porque o Excel conta a partir de 1 e a primeira linha é o cabeçalho.
        numero_linha = int(indice) + 2

        # Planilha de operação quase sempre termina com dezenas de linhas sem
        # dados. Elas não são erro do usuário — são só o fim do preenchimento.
        # Só olhamos os campos que o sistema usa: colunas de controle como
        # STATUS costumam vir preenchidas até o fim e não significam nada aqui.
        if all(not _texto(linha.get(campo)) for campo in campos_uteis):
            relatorio["ignoradas"] += 1
            continue

        codigo_original = _texto(linha.get("codigo_rastreio")) or "(vazio)"

        try:
            dados = {
                "nome": _texto(linha.get("nome")),
                "cpf": _texto(linha.get("cpf")),
                "endereco": _texto(linha.get("endereco")),
                "numero": _texto(linha.get("numero")),
                "bairro": _texto(linha.get("bairro")),
                "cidade": _texto(linha.get("cidade")),
                "estado": _texto(linha.get("estado")).upper()[:2],
                "cep": _texto(linha.get("cep")),
            }

            if not dados["nome"]:
                raise ValueError("nome em branco")
            if not dados["cidade"] or not dados["estado"]:
                raise ValueError("cidade ou estado em branco")

            data_cadastro = _converter_data(linha.get("data_cadastro"))

            codigo = gerador_codigo.limpar(linha.get("codigo_rastreio"))
            if not codigo:
                if not gerar_codigo_se_vazio:
                    raise ValueError("código de rastreio em branco")
                codigo = None  # gerado na etapa 2, quando já se sabe o que existe
            else:
                if not gerador_codigo.validar_estrito(codigo):
                    raise ValueError(
                        "código inválido ("
                        + gerador_codigo.motivo_invalido(codigo)
                        + ")"
                    )
                # Grava sempre em maiúsculas: a busca do site normaliza o que o
                # usuário digita, então o banco precisa estar na mesma caixa.
                codigo = gerador_codigo.normalizar(codigo)
                if codigo in codigos_desta_planilha:
                    raise ValueError("código repetido dentro da própria planilha")
                codigos_desta_planilha.add(codigo)

        except Exception as erro:
            relatorio["erros"].append(
                {"linha": numero_linha, "codigo": codigo_original, "motivo": str(erro)}
            )
            continue

        linhas_validas.append(
            {
                "numero_linha": numero_linha,
                "codigo_original": codigo_original,
                "dados": dados,
                "data_cadastro": data_cadastro,
                "codigo": codigo,
            }
        )

    return linhas_validas


class _Cache:
    """
    Etapa 2: tudo o que a importação precisa consultar, carregado em poucas
    consultas grandes em vez de uma consulta por linha.

    As relações são trocadas para carregamento preguiçoso: sem isso, ler os
    clientes puxaria junto todos os pedidos e todas as movimentações do banco.
    """

    def __init__(self, codigos_da_planilha):
        self.codigos_existentes = set(
            db.session.execute(db.select(Pedido.codigo_rastreio)).scalars()
        )

        self.pedidos = {}
        codigos = [c for c in codigos_da_planilha if c in self.codigos_existentes]
        for inicio in range(0, len(codigos), 1000):
            consulta = (
                db.select(Pedido)
                .options(lazyload(Pedido.movimentacoes), lazyload(Pedido.cliente))
                .where(Pedido.codigo_rastreio.in_(codigos[inicio:inicio + 1000]))
            )
            for pedido in db.session.execute(consulta).scalars():
                self.pedidos[pedido.codigo_rastreio] = pedido

        self.pedidos_com_movimentacao = set()
        ids = [p.id for p in self.pedidos.values()]
        for inicio in range(0, len(ids), 1000):
            consulta = (
                db.select(Movimentacao.pedido_id)
                .where(Movimentacao.pedido_id.in_(ids[inicio:inicio + 1000]))
                .distinct()
            )
            self.pedidos_com_movimentacao.update(db.session.execute(consulta).scalars())

        # Mesma regra de antes para achar o cliente: CPF quando existe, senão
        # nome + cidade. Em empate fica o cadastro mais antigo.
        self.por_cpf = {}
        self.por_nome_cidade = {}
        consulta = (
            db.select(Cliente)
            .options(lazyload(Cliente.pedidos))
            .order_by(Cliente.id)
        )
        for cliente in db.session.execute(consulta).scalars():
            if cliente.cpf:
                self.por_cpf.setdefault(cliente.cpf, cliente)
            self.por_nome_cidade.setdefault((cliente.nome, cliente.cidade), cliente)

    def buscar_cliente(self, dados):
        if dados["cpf"] and dados["cpf"] in self.por_cpf:
            return self.por_cpf[dados["cpf"]]
        return self.por_nome_cidade.get((dados["nome"], dados["cidade"]))

    def registrar_cliente(self, cliente):
        """Chamado depois de criar ou alterar um cliente nesta importação."""
        if cliente.cpf:
            self.por_cpf[cliente.cpf] = cliente
        self.por_nome_cidade[(cliente.nome, cliente.cidade)] = cliente

    def gerar_codigo(self, reservados):
        for _ in range(100):
            codigo = gerador_codigo.gerar()
            if codigo not in self.codigos_existentes and codigo not in reservados:
                reservados.add(codigo)
                return codigo
        raise RuntimeError("Não foi possível gerar um código único.")


def _gravar_bloco(linhas, cache):
    """
    Etapa 3: grava um bloco de linhas já validadas numa única transação.
    Devolve (adicionados, atualizados). Se algo falhar, levanta a exceção e
    nada do bloco fica gravado.
    """
    # ---- clientes ----------------------------------------------------
    clientes = []
    for item in linhas:
        cliente = cache.buscar_cliente(item["dados"])
        if cliente is None:
            cliente = Cliente()
            db.session.add(cliente)
        _aplicar_dados_cliente(cliente, item["dados"])
        cache.registrar_cliente(cliente)
        clientes.append(cliente)

    db.session.flush()  # INSERT em lote: garante cliente.id

    # ---- pedidos -----------------------------------------------------
    adicionados = 0
    atualizados = 0
    a_regravar = []  # (pedido, cliente, ja_existia)

    for item, cliente in zip(linhas, clientes):
        codigo = item["codigo"]
        data_cadastro = item["data_cadastro"]
        pedido = cache.pedidos.get(codigo)

        if pedido is None:
            # Pedido novo sem data na planilha entra com a data de hoje:
            # é quando ele de fato passou a existir no sistema.
            pedido = Pedido(
                codigo_rastreio=codigo,
                cliente_id=cliente.id,
                data_cadastro=data_cadastro or date.today(),
            )
            db.session.add(pedido)
            a_regravar.append((pedido, cliente, False))
            adicionados += 1
        else:
            # Pedido que já existe SÓ muda de data se a planilha trouxer
            # uma. Sem isso, reenviar o arquivo completo (o jeito normal
            # de trabalhar) jogaria todo mundo de volta para o dia zero.
            data_final = data_cadastro or pedido.data_cadastro

            destino_novo = cliente.cidade + "/" + cliente.estado
            precisa_regravar = (
                pedido.destino != destino_novo
                or pedido.data_cadastro != data_final
                or pedido.id not in cache.pedidos_com_movimentacao
            )

            pedido.cliente_id = cliente.id
            pedido.data_cadastro = data_final

            if precisa_regravar:
                a_regravar.append((pedido, cliente, True))
            atualizados += 1

    # ---- timelines ---------------------------------------------------
    novas_movimentacoes = []
    for pedido, cliente, _ in a_regravar:
        eventos = gerar_movimentacoes(
            pedido.codigo_rastreio,
            pedido.data_cadastro,
            cliente.cidade,
            cliente.estado,
            cliente.cep,
        )
        rota = montar_rota(cliente.cidade, cliente.estado, cliente.cep)
        pedido.origem = rota["origem"]
        pedido.destino = rota["destino"]
        pedido.previsao_entrega = calcular_previsao(eventos)
        novas_movimentacoes.append((pedido, eventos))

    db.session.flush()  # INSERT/UPDATE dos pedidos em lote: garante pedido.id

    ids_antigos = [pedido.id for pedido, _, ja_existia in a_regravar if ja_existia]
    if ids_antigos:
        db.session.execute(
            delete(Movimentacao).where(Movimentacao.pedido_id.in_(ids_antigos)),
            execution_options={"synchronize_session": False},
        )

    registros = [
        dict(evento, pedido_id=pedido.id)
        for pedido, eventos in novas_movimentacoes
        for evento in eventos
    ]
    if registros:
        db.session.execute(insert(Movimentacao), registros)

    db.session.commit()

    # Só depois do commit o cache passa a considerar estes pedidos gravados.
    for pedido, _, _ in a_regravar:
        cache.codigos_existentes.add(pedido.codigo_rastreio)
        cache.pedidos[pedido.codigo_rastreio] = pedido
        cache.pedidos_com_movimentacao.add(pedido.id)

    return adicionados, atualizados


def importar_planilha(caminho_arquivo, gerar_codigo_se_vazio=True):
    """
    Importa a planilha e devolve o relatório:

    {
      "total_linhas": 20,
      "adicionados": 18,
      "atualizados": 1,
      "erros": [{"linha": 7, "codigo": "BR12345", "motivo": "..."}],
      "codigos_gerados": ["BR..."],
    }
    """
    try:
        df = ler_arquivo(caminho_arquivo)
    except ErroDePlanilha:
        raise
    except Exception as erro:
        raise ErroDePlanilha("Não foi possível ler o arquivo: " + str(erro)) from erro

    df = _normalizar_cabecalho(df)

    faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in df.columns]
    if faltando:
        raise ErroDePlanilha(
            "A planilha está sem a(s) coluna(s): " + ", ".join(faltando)
        )

    relatorio = {
        "total_linhas": int(len(df)),
        "adicionados": 0,
        "atualizados": 0,
        "ignoradas": 0,
        "erros": [],
        "codigos_gerados": [],
    }

    linhas = _validar_linhas(df, gerar_codigo_se_vazio, relatorio)

    codigos_da_planilha = {item["codigo"] for item in linhas if item["codigo"]}
    cache = _Cache(codigos_da_planilha)

    reservados = set(codigos_da_planilha)
    for item in linhas:
        if item["codigo"] is None:
            item["codigo"] = cache.gerar_codigo(reservados)
            relatorio["codigos_gerados"].append(item["codigo"])

    # Depois de cada commit o SQLAlchemy marcaria clientes e pedidos como
    # desatualizados e voltaria ao banco para reler um por um no bloco
    # seguinte. Durante a importação só ela mexe nesses registros, então o
    # que está em memória continua valendo.
    sessao = db.session()
    expirar_antes = sessao.expire_on_commit
    sessao.expire_on_commit = False
    try:
        for inicio in range(0, len(linhas), TAMANHO_DO_BLOCO):
            bloco = linhas[inicio:inicio + TAMANHO_DO_BLOCO]
            try:
                adicionados, atualizados = _gravar_bloco(bloco, cache)
                relatorio["adicionados"] += adicionados
                relatorio["atualizados"] += atualizados
                continue
            except Exception:
                db.session.rollback()

            # O bloco falhou no banco. O rollback deixou o cache com objetos que
            # nunca foram gravados, então ele é recarregado e o bloco é refeito
            # uma linha por vez para isolar a(s) linha(s) problemática(s).
            cache = _Cache(codigos_da_planilha)
            for item in bloco:
                try:
                    adicionados, atualizados = _gravar_bloco([item], cache)
                    relatorio["adicionados"] += adicionados
                    relatorio["atualizados"] += atualizados
                except Exception as erro:
                    db.session.rollback()
                    cache = _Cache(codigos_da_planilha)
                    relatorio["erros"].append(
                        {
                            "linha": item["numero_linha"],
                            "codigo": item["codigo_original"],
                            "motivo": str(erro).splitlines()[0],
                        }
                    )
    finally:
        sessao.expire_on_commit = expirar_antes

    relatorio["erros"].sort(key=lambda erro: erro["linha"])

    # Os objetos carregados aqui vieram com as relações em modo preguiçoso;
    # tirá-los da sessão evita que alguém os reaproveite achando que vieram
    # completos.
    db.session.expunge_all()

    return relatorio
