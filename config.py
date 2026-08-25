"""
Configuração central do sistema Verllog Logística.

Tudo que você pode querer ajustar sem mexer na lógica do sistema mora aqui:
identidade da marca, regras do código de rastreio, fluxo de status e o
intervalo de dias entre cada etapa da entrega.
"""

import os
from pathlib import Path

# Pasta raiz do projeto (onde este arquivo está).
BASE_DIR = Path(__file__).resolve().parent


def _url_do_banco():
    """
    Escolhe o banco de dados.

    Sem a variável DATABASE_URL definida (seu PC), usa SQLite num arquivo
    local. Com ela definida (servidor), usa PostgreSQL, que guarda os dados
    fora da máquina do site e por isso sobrevive a reinícios e atualizações.

    Serviços de hospedagem entregam a URL começando com 'postgres://', que é
    um formato antigo que o SQLAlchemy não aceita mais. A troca abaixo ajusta
    isso e aponta para o driver psycopg 3.
    """
    url = os.environ.get("DATABASE_URL", "").strip()

    if not url:
        return f"sqlite:///{BASE_DIR / 'database.db'}"

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)

    return url


class Config:
    # ------------------------------------------------------------------
    # Flask
    # ------------------------------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY", "verllog-chave-de-desenvolvimento")

    # ------------------------------------------------------------------
    # Banco de dados
    # ------------------------------------------------------------------
    SQLALCHEMY_DATABASE_URI = _url_do_banco()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Conexões de banco gratuito costumam cair depois de alguns minutos
    # ociosas. Isso testa a conexão antes de usar e reconecta sozinho, em vez
    # de devolver erro para quem estava consultando um código.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    # ------------------------------------------------------------------
    # Upload de planilhas (usado a partir da Fase 3)
    # ------------------------------------------------------------------
    UPLOAD_FOLDER = BASE_DIR / "uploads"
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB
    EXTENSOES_PERMITIDAS = {".xlsx", ".xls", ".csv"}

    # Colunas obrigatórias da planilha de clientes.
    COLUNAS_PLANILHA = [
        "codigo_rastreio",
        "nome",
        "cpf",
        "endereco",
        "numero",
        "bairro",
        "cidade",
        "estado",
        "cep",
        "data_cadastro",
    ]

    # ------------------------------------------------------------------
    # Identidade da transportadora fictícia
    # ------------------------------------------------------------------
    EMPRESA_NOME = "Verllog Logística"
    EMPRESA_SLOGAN = "Sua entrega no caminho certo."
    EMPRESA_CNPJ = "00.000.000/0001-00"

    # ------------------------------------------------------------------
    # Código de rastreamento: BR + 12 dígitos + 1 letra maiúscula
    # Ex.: BR263198595496D  (15 caracteres)
    # ------------------------------------------------------------------
    # Como a Verllog é operadora terceirizada, o prefixo de duas letras
    # identifica quem originou a postagem — cada loja parceira tem o seu. Por
    # isso a validação aceita qualquer par de letras, e não um prefixo fixo.
    CODIGO_PREFIXO = "VL"  # usado só quando o sistema precisa GERAR um código
    CODIGO_QTD_DIGITOS = 12
    CODIGO_REGEX = r"^[A-Z]{2}\d{12}[A-Z]$"
    CODIGO_TAMANHO = 15

    # A planilha de operação já em uso traz códigos antigos que não seguem o
    # padrão acima (alguns terminam em número, outros usam outro prefixo).
    # Com ACEITAR_CODIGOS_LEGADOS ligado, esses códigos são importados como
    # estão, para não perder o histórico — mas todo código NOVO que o sistema
    # gerar continua saindo no padrão oficial.
    ACEITAR_CODIGOS_LEGADOS = True
    CODIGO_REGEX_LEGADO = r"^[A-Z]{2}\d{8,20}[A-Z]?$"

    # ------------------------------------------------------------------
    # Motor de rastreamento (Fase 7)
    #
    # O status avança sozinho conforme a diferença entre a data de hoje e a
    # data_cadastro do pedido. Nada precisa rodar em segundo plano.
    #
    # Em vez de um intervalo fixo entre etapas, cada status tem o seu DIA no
    # cronograma, contado a partir do cadastro. Isso permite ritmo desigual:
    # o início anda rápido, a transferência demora, e as duas tentativas de
    # entrega caem em dias exatos. O trajeto inteiro fecha em 35 dias.
    # ------------------------------------------------------------------
    DURACAO_TOTAL_DIAS = 35

    CRONOGRAMA = {
        "Pedido recebido": 0,
        "Pedido processado": 3,
        "Objeto coletado": 6,
        # As etapas "Em transferência" ficam na janela definida abaixo.
        "Centro de distribuição": 20,
        "Unidade de destino": 24,
        "Tentativa de entrega não realizada": 28,
        "Nova tentativa de entrega": 30,
        "Saiu para entrega": 33,
        "Entregue": 35,
    }

    # Janela em que as etapas "Em transferência" são distribuídas. Quantos
    # eventos entram aí depende de quantos centros a rota atravessa, mas o
    # trajeto todo continua terminando em DURACAO_TOTAL_DIAS.
    JANELA_TRANSFERENCIA = (6, 20)

    # Fluxo de status, na ordem. Alterar esta lista muda a timeline inteira.
    FLUXO_STATUS = [
        "Pedido recebido",
        "Pedido processado",
        "Objeto coletado",
        "Em transferência",
        "Centro de distribuição",
        "Unidade de destino",
        "Tentativa de entrega não realizada",
        "Nova tentativa de entrega",
        "Saiu para entrega",
        "Entregue",
    ]
    STATUS_FINAL = "Entregue"

    # ------------------------------------------------------------------
    # Painel administrativo (login simples, apenas para demonstração)
    # ------------------------------------------------------------------
    ADMIN_USUARIO = os.environ.get("ADMIN_USUARIO", "admin")
    ADMIN_SENHA = os.environ.get("ADMIN_SENHA", "verllog2026")


class TestConfig(Config):
    """Configuração usada pelos testes automatizados (Fase 11)."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
