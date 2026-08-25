"""
Motor de rotas (Fase 6).

Dado o destino do cliente (cidade + UF), monta um trajeto logístico coerente
passando pelos centros de distribuição da Verllog.

A malha parte da matriz em MANAUS/AM — porta de entrada da Zona Franca e
principal ponto de recebimento da carga importada. De lá a operação se divide
em dois corredores:

  * Corredor Norte/Nordeste — segue por Belém, aproveitando a ligação fluvial
    do Amazonas, e daí para as capitais nordestinas.

  * Corredor Centro-Sul — segue por Campinas/Viracopos, que é na prática o
    principal terminal de carga aérea ligado a Manaus, e distribui para
    Sudeste, Sul e Centro-Oeste.

Quanto mais longe o destino, mais centros no caminho — e, como cada etapa custa
DIAS_POR_ETAPA dias, o prazo cresce sozinho para destinos distantes.

Não depende de nenhuma API externa. Existe um gancho opcional
(`consultar_api_externa`) para quem quiser plugar geocodificação depois; se ele
devolver None — que é o padrão — a malha interna assume.
"""

# ----------------------------------------------------------------------
# Centros de distribuição
# ----------------------------------------------------------------------

CENTROS = {
    # Matriz
    "MAO": ("CD-MAO", "Manaus",         "AM"),
    # Norte
    "BVB": ("CD-BVB", "Boa Vista",      "RR"),
    "PVH": ("CD-PVH", "Porto Velho",    "RO"),
    "RBR": ("CD-RBR", "Rio Branco",     "AC"),
    "BEL": ("CD-BEL", "Belém",          "PA"),
    "MCP": ("CD-MCP", "Macapá",         "AP"),
    "PMW": ("CD-PMW", "Palmas",         "TO"),
    # Nordeste
    "SLZ": ("CD-SLZ", "São Luís",       "MA"),
    "FOR": ("CD-FOR", "Fortaleza",      "CE"),
    "REC": ("CD-REC", "Recife",         "PE"),
    "SSA": ("CD-SSA", "Salvador",       "BA"),
    # Centro-Oeste
    "BSB": ("CD-BSB", "Brasília",       "DF"),
    "GYN": ("CD-GYN", "Goiânia",        "GO"),
    "CGB": ("CD-CGB", "Cuiabá",         "MT"),
    "CGR": ("CD-CGR", "Campo Grande",   "MS"),
    # Sudeste
    "CPS": ("CD-CPS", "Campinas",       "SP"),
    "SP":  ("CD-SP",  "São Paulo",      "SP"),
    "RJ":  ("CD-RJ",  "Rio de Janeiro", "RJ"),
    "VIX": ("CD-VIX", "Vitória",        "ES"),
    "VGA": ("CD-VGA", "Varginha",       "MG"),
    "BH":  ("CD-BH",  "Belo Horizonte", "MG"),
    # Sul
    "PGZ": ("CD-PGZ", "Ponta Grossa",   "PR"),
    "CTB": ("CD-CTB", "Curitiba",       "PR"),
    "FLN": ("CD-FLN", "Florianópolis",  "SC"),
    "POA": ("CD-POA", "Porto Alegre",   "RS"),
}

CENTRO_MATRIZ = "MAO"

# ----------------------------------------------------------------------
# Malha: caminho de centros até cada estado, começando sempre na matriz.
# ----------------------------------------------------------------------

MALHA = {
    # --- Norte: saída direta da matriz -------------------------------
    "AM": ["MAO"],
    "RR": ["MAO", "BVB"],
    "RO": ["MAO", "PVH"],
    "AC": ["MAO", "PVH", "RBR"],
    "PA": ["MAO", "BEL"],
    "AP": ["MAO", "BEL", "MCP"],
    "TO": ["MAO", "BEL", "PMW"],

    # --- Nordeste: corredor por Belém --------------------------------
    "MA": ["MAO", "BEL", "SLZ"],
    "PI": ["MAO", "BEL", "SLZ", "FOR"],
    "CE": ["MAO", "BEL", "FOR"],
    "RN": ["MAO", "BEL", "FOR", "REC"],
    "PB": ["MAO", "BEL", "FOR", "REC"],
    "PE": ["MAO", "BEL", "REC"],
    "AL": ["MAO", "BEL", "REC", "SSA"],
    "SE": ["MAO", "BEL", "REC", "SSA"],
    "BA": ["MAO", "BSB", "SSA"],

    # --- Centro-Oeste ------------------------------------------------
    "MT": ["MAO", "CGB"],
    "DF": ["MAO", "BSB"],
    "GO": ["MAO", "BSB", "GYN"],
    "MS": ["MAO", "CGB", "CGR"],

    # --- Sudeste: corredor por Campinas ------------------------------
    "SP": ["MAO", "CPS"],
    "RJ": ["MAO", "CPS", "RJ"],
    "ES": ["MAO", "CPS", "RJ", "VIX"],
    "MG": ["MAO", "CPS", "VGA", "BH"],

    # --- Sul ---------------------------------------------------------
    "PR": ["MAO", "CPS", "PGZ", "CTB"],
    "SC": ["MAO", "CPS", "CTB", "FLN"],
    "RS": ["MAO", "CPS", "CTB", "POA"],
}

# Fallback para UF desconhecida: sai da matriz e passa pela triagem principal.
MALHA_PADRAO = ["MAO", "CPS"]


def _formatar_centro(sigla):
    codigo, cidade, uf = CENTROS[sigla]
    return {
        "sigla": sigla,
        "codigo": codigo,
        "cidade": cidade,
        "uf": uf,
        "rotulo": f"CD {cidade}/{uf}",
        "local": f"{cidade}/{uf}",
    }


def consultar_api_externa(cidade, estado, cep=None):
    """
    Gancho opcional para geocodificação/rotas por API.

    Retornar uma lista de siglas de centro faz o sistema usar esse trajeto.
    Retornar None (padrão) mantém a malha interna. O sistema nunca fica
    dependente de internet por causa disso.
    """
    return None


def normalizar_uf(estado):
    return (estado or "").strip().upper()[:2]


def montar_rota(cidade, estado, cep=None):
    """
    Devolve o trajeto até o destino.

    {
      "origem":   "CD Manaus/AM",
      "destino":  "Rio de Janeiro/RJ",
      "centros":  [ {...}, {...} ],   # do primeiro ao último centro
    }
    """
    uf = normalizar_uf(estado)
    cidade = (cidade or "").strip()

    caminho = consultar_api_externa(cidade, uf, cep) or MALHA.get(uf, MALHA_PADRAO)
    caminho = list(caminho)

    # A capital paulista tem centro próprio, depois da triagem de Campinas.
    if uf == "SP" and cidade.lower() in ("sao paulo", "são paulo"):
        caminho = ["MAO", "CPS", "SP"]

    centros = [_formatar_centro(s) for s in caminho]

    return {
        "origem": centros[0]["rotulo"],
        "destino": f"{cidade}/{uf}",
        "centros": centros,
        "uf": uf,
        "cidade": cidade,
    }


def descrever_rota(cidade, estado, cep=None):
    """Versão em texto do trajeto, útil no painel e para conferência."""
    rota = montar_rota(cidade, estado, cep)
    paradas = [c["local"] for c in rota["centros"]]
    if rota["destino"] not in paradas:
        paradas.append(rota["destino"])
    return " -> ".join(paradas)
