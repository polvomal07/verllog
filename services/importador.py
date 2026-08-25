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


def _buscar_cliente(dados):
    """
    Procura um cliente já cadastrado. O CPF é a chave natural quando existe;
    sem CPF, cai para nome + cidade.
    """
    if dados["cpf"]:
        cliente = Cliente.query.filter_by(cpf=dados["cpf"]).first()
        if cliente:
            return cliente

    return Cliente.query.filter_by(nome=dados["nome"], cidade=dados["cidade"]).first()


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
# ----------------------------------------------------------------------


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

            # ---- código de rastreio ------------------------------------
            codigo = gerador_codigo.limpar(linha.get("codigo_rastreio"))

            if not codigo:
                if not gerar_codigo_se_vazio:
                    raise ValueError("código de rastreio em branco")
                # gerar_unico já registra o código em codigos_desta_planilha,
                # então a checagem de duplicidade abaixo não se aplica a ele.
                codigo = gerador_codigo.gerar_unico(codigos_desta_planilha)
                relatorio["codigos_gerados"].append(codigo)
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

            # ---- cliente -----------------------------------------------
            cliente = _buscar_cliente(dados)
            if cliente is None:
                cliente = Cliente()
                db.session.add(cliente)
            _aplicar_dados_cliente(cliente, dados)
            db.session.flush()  # garante cliente.id

            # ---- pedido ------------------------------------------------
            pedido = Pedido.query.filter_by(codigo_rastreio=codigo).first()

            if pedido is None:
                # Pedido novo sem data na planilha entra com a data de hoje:
                # é quando ele de fato passou a existir no sistema.
                pedido = Pedido(
                    codigo_rastreio=codigo,
                    cliente_id=cliente.id,
                    data_cadastro=data_cadastro or date.today(),
                )
                db.session.add(pedido)
                db.session.flush()
                _regravar_movimentacoes(pedido, cliente)
                relatorio["adicionados"] += 1
            else:
                # Pedido que já existe SÓ muda de data se a planilha trouxer
                # uma. Sem isso, reenviar o arquivo completo (o jeito normal
                # de trabalhar) jogaria todo mundo de volta para o dia zero.
                data_final = data_cadastro or pedido.data_cadastro

                destino_novo = cliente.cidade + "/" + cliente.estado
                precisa_regravar = (
                    pedido.destino != destino_novo
                    or pedido.data_cadastro != data_final
                    or not pedido.movimentacoes
                )

                pedido.cliente_id = cliente.id
                pedido.data_cadastro = data_final

                if precisa_regravar:
                    _regravar_movimentacoes(pedido, cliente)

                relatorio["atualizados"] += 1

            # Cada linha é confirmada individualmente: um erro na linha 7 não
            # desfaz as seis linhas boas que vieram antes.
            db.session.commit()

        except Exception as erro:
            db.session.rollback()
            relatorio["erros"].append(
                {
                    "linha": numero_linha,
                    "codigo": _texto(linha.get("codigo_rastreio")) or "(vazio)",
                    "motivo": str(erro),
                }
            )
            continue

    return relatorio
