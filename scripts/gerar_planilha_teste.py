"""
Gera a planilha de teste com 20 clientes fictícios.

Uso:
    python scripts/gerar_planilha_teste.py

Cria o arquivo `uploads/clientes.xlsx`, espalhado pelas dez capitais pedidas e
com datas de cadastro variadas — de recém-postado a já entregue — para dar o que
mostrar na apresentação.

Todos os dados são inventados. Os CPFs são numeração de demonstração e não
pertencem a nenhuma pessoa real.
"""

import random
import string
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

# Permite rodar o script direto da raiz do projeto.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SAIDA = Path(__file__).resolve().parent.parent / "uploads" / "clientes.xlsx"

# Semente fixa: rodar de novo gera exatamente a mesma planilha.
random.seed(2026)

CLIENTES = [
    ("Maria Oliveira",     "Rua das Flores",        "120",  "Centro",         "Rio de Janeiro", "RJ", "20040-002"),
    ("João Pedro Almeida", "Avenida Paulista",      "1578", "Bela Vista",     "São Paulo",      "SP", "01310-200"),
    ("Ana Beatriz Souza",  "Rua XV de Novembro",    "455",  "Centro",         "Curitiba",       "PR", "80020-310"),
    ("Carlos Henrique Lima", "Avenida Afonso Pena", "2300", "Funcionários",   "Belo Horizonte", "MG", "30130-007"),
    ("Fernanda Ribeiro",   "Avenida Sete de Setembro", "890", "Vitória",      "Salvador",       "BA", "40080-002"),
    ("Rafael Monteiro",    "SQN 210 Bloco C",       "45",   "Asa Norte",      "Brasília",       "DF", "70862-030"),
    ("Juliana Castro",     "Rua dos Andradas",      "1234", "Centro Histórico", "Porto Alegre", "RS", "90020-008"),
    ("Bruno Cavalcanti",   "Avenida Boa Viagem",    "3200", "Boa Viagem",     "Recife",         "PE", "51020-000"),
    ("Larissa Fontes",     "Avenida Beira Mar",     "1010", "Meireles",       "Fortaleza",      "CE", "60165-121"),
    ("Diego Marchetti",    "Rua Bocaiúva",          "760",  "Centro",         "Florianópolis",  "SC", "88015-530"),
    ("Patrícia Nogueira",  "Rua Barata Ribeiro",    "302",  "Copacabana",     "Rio de Janeiro", "RJ", "22040-002"),
    ("Eduardo Tavares",    "Rua Augusta",           "2100", "Consolação",     "São Paulo",      "SP", "01412-100"),
    ("Camila Rezende",     "Avenida Batel",         "1680", "Batel",          "Curitiba",       "PR", "80420-090"),
    ("Marcos Vinícius Paiva", "Rua da Bahia",       "1148", "Centro",         "Belo Horizonte", "MG", "30160-011"),
    ("Tatiane Barros",     "Rua Chile",             "27",   "Pelourinho",     "Salvador",       "BA", "40020-000"),
    ("Rodrigo Sampaio",    "CLS 405 Bloco B",       "12",   "Asa Sul",        "Brasília",       "DF", "70239-520"),
    ("Vanessa Klein",      "Avenida Ipiranga",      "6681", "Partenon",       "Porto Alegre",   "RS", "90619-900"),
    ("Felipe Andrade",     "Rua da Aurora",         "555",  "Santo Amaro",    "Recife",         "PE", "50050-000"),
    ("Isabela Prado",      "Avenida Dom Luís",      "300",  "Aldeota",        "Fortaleza",      "CE", "60160-230"),
    ("Gustavo Menezes",    "Avenida Mauro Ramos",   "1420", "Centro",         "Florianópolis",  "SC", "88020-302"),
]

# Quantos dias atrás cada pedido foi cadastrado. Com 2 dias por etapa, isso
# distribui os 20 pedidos por todos os estágios da entrega.
DIAS_ATRAS = [0, 1, 3, 5, 7, 9, 11, 13, 15, 18, 2, 4, 6, 8, 10, 12, 14, 16, 20, 25]


def gerar_codigo():
    digitos = "".join(random.choices(string.digits, k=12))
    return "BR" + digitos + random.choice(string.ascii_uppercase)


def gerar_cpf_ficticio():
    numeros = "".join(random.choices(string.digits, k=11))
    return f"{numeros[:3]}.{numeros[3:6]}.{numeros[6:9]}-{numeros[9:]}"


def main():
    hoje = date.today()
    codigos = set()
    linhas = []

    for indice, cliente in enumerate(CLIENTES):
        nome, endereco, numero, bairro, cidade, estado, cep = cliente

        codigo = gerar_codigo()
        while codigo in codigos:
            codigo = gerar_codigo()
        codigos.add(codigo)

        data_cadastro = hoje - timedelta(days=DIAS_ATRAS[indice])

        linhas.append(
            {
                "codigo_rastreio": codigo,
                "nome": nome,
                "cpf": gerar_cpf_ficticio(),
                "endereco": endereco,
                "numero": numero,
                "bairro": bairro,
                "cidade": cidade,
                "estado": estado,
                "cep": cep,
                "data_cadastro": data_cadastro.strftime("%d/%m/%Y"),
            }
        )

    df = pd.DataFrame(linhas)
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(SAIDA, index=False, sheet_name="clientes")

    print(f"Planilha gerada: {SAIDA}")
    print(f"{len(df)} clientes ficticios em 10 capitais.")
    print("\nAlguns codigos para testar:")
    for linha in linhas[:5]:
        print(f"  {linha['codigo_rastreio']}  {linha['nome']} - {linha['cidade']}")


if __name__ == "__main__":
    main()
