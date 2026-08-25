"""
Gera planilhas propositalmente problemáticas, para provar que a validação
da importação funciona (testes 17 e 18 do roteiro).

Uso:
    python scripts/gerar_planilhas_de_erro.py

Cria em uploads/:
  - clientes_com_erros.xlsx   códigos fora do padrão, duplicados e campos vazios
  - clientes_sem_coluna.xlsx  planilha sem a coluna 'cidade'
  - clientes_novos.xlsx       o segundo upload, com 3 clientes inéditos
"""

import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DESTINO = Path(__file__).resolve().parent.parent / "uploads"
HOJE = date.today().strftime("%d/%m/%Y")


def planilha_com_erros():
    """Cada linha testa um tipo diferente de problema."""
    linhas = [
        # válida — serve de controle, tem que passar no meio dos erros
        ("BR700100200300Z", "Cliente Válido", "111.222.333-44", "Rua Um", "10",
         "Centro", "Goiânia", "GO", "74000-000", HOJE),
        # prefixo errado
        ("TRX849302", "Prefixo Errado", "111.222.333-45", "Rua Dois", "20",
         "Centro", "Natal", "RN", "59000-000", HOJE),
        # números de menos
        ("BR12345", "Curto Demais", "111.222.333-46", "Rua Três", "30",
         "Centro", "Manaus", "AM", "69000-000", HOJE),
        # números de mais
        ("BR1234567890123A", "Longo Demais", "111.222.333-47", "Rua Quatro", "40",
         "Centro", "Belém", "PA", "66000-000", HOJE),
        # sem a letra final
        ("BR263198595496", "Sem Letra", "111.222.333-48", "Rua Cinco", "50",
         "Centro", "Cuiabá", "MT", "78000-000", HOJE),
        # letra minúscula
        ("BR263198595496d", "Letra Minuscula", "111.222.333-49", "Rua Seis", "60",
         "Centro", "Palmas", "TO", "77000-000", HOJE),
        # duplicado dentro da própria planilha
        ("BR700100200300Z", "Codigo Repetido", "111.222.333-50", "Rua Sete", "70",
         "Centro", "Maceió", "AL", "57000-000", HOJE),
        # nome em branco
        ("BR700100200301Y", "", "111.222.333-51", "Rua Oito", "80",
         "Centro", "Aracaju", "SE", "49000-000", HOJE),
        # cidade em branco
        ("BR700100200302X", "Sem Cidade", "111.222.333-52", "Rua Nove", "90",
         "Centro", "", "PB", "58000-000", HOJE),
        # código vazio — deve ser gerado automaticamente, não é erro
        ("", "Codigo Automatico", "111.222.333-53", "Rua Dez", "100",
         "Centro", "Vitória", "ES", "29000-000", HOJE),
    ]

    df = pd.DataFrame(linhas, columns=[
        "codigo_rastreio", "nome", "cpf", "endereco", "numero",
        "bairro", "cidade", "estado", "cep", "data_cadastro",
    ])
    caminho = DESTINO / "clientes_com_erros.xlsx"
    df.to_excel(caminho, index=False)
    return caminho, len(df)


def planilha_sem_coluna():
    """Planilha faltando a coluna obrigatória 'cidade'."""
    df = pd.DataFrame([{
        "codigo_rastreio": "BR900100200300K",
        "nome": "Cliente Sem Coluna",
        "estado": "SP",
        "data_cadastro": HOJE,
    }])
    caminho = DESTINO / "clientes_sem_coluna.xlsx"
    df.to_excel(caminho, index=False)
    return caminho, len(df)


def planilha_segundo_upload():
    """Simula o segundo envio: clientes inéditos que devem ser só adicionados."""
    linhas = [
        ("BR500600700800A", "Novo Cliente Um", "222.333.444-55", "Rua Nova", "11",
         "Jardins", "São Paulo", "SP", "01400-000", HOJE),
        ("BR500600700801B", "Novo Cliente Dois", "222.333.444-56", "Rua Nova", "22",
         "Boa Vista", "Recife", "PE", "50060-000", HOJE),
        ("BR500600700802C", "Novo Cliente Três", "222.333.444-57", "Rua Nova", "33",
         "Centro", "Manaus", "AM", "69005-000", HOJE),
    ]
    df = pd.DataFrame(linhas, columns=[
        "codigo_rastreio", "nome", "cpf", "endereco", "numero",
        "bairro", "cidade", "estado", "cep", "data_cadastro",
    ])
    caminho = DESTINO / "clientes_novos.xlsx"
    df.to_excel(caminho, index=False)
    return caminho, len(df)


if __name__ == "__main__":
    DESTINO.mkdir(parents=True, exist_ok=True)
    for gerar in (planilha_com_erros, planilha_sem_coluna, planilha_segundo_upload):
        caminho, total = gerar()
        print(f"{caminho.name:<28} {total} linhas")
