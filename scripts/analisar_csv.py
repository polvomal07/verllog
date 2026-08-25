"""
Analisa um CSV/XLSX qualquer e diz o que precisa ser ajustado antes de importar.

Uso:
    python scripts/analisar_csv.py caminho/do/arquivo.csv
"""

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.importador import ler_arquivo  # noqa: E402

PADRAO = re.compile(r"^BR\d{12}[A-Z]$")


def classificar(codigo):
    bruto = str(codigo or "").strip()
    if not bruto or bruto.lower() == "nan":
        return "vazio"
    if PADRAO.fullmatch(bruto):
        return "valido"
    if not bruto.upper().startswith("BR"):
        return "sem prefixo BR"
    if len(bruto) != 15:
        return f"tamanho {len(bruto)} (deveria ser 15)"
    if bruto[-1].isdigit():
        return "termina em numero (falta a letra)"
    if bruto[-1].islower():
        return "letra final minuscula"
    return "outro problema"


def main():
    if len(sys.argv) < 2:
        print("Informe o caminho do arquivo.")
        return 1

    caminho = sys.argv[1]
    df = ler_arquivo(caminho)

    print("")
    print("=== COLUNAS ENCONTRADAS ===")
    for coluna in df.columns:
        print(f"  {coluna}")

    print("")
    print(f"=== LINHAS: {len(df)} ===")

    # Encontra a coluna de código pelo conteúdo, não pelo nome.
    coluna_codigo = None
    for coluna in df.columns:
        amostra = df[coluna].astype(str).str.strip().str.upper()
        if (amostra.str.startswith("BR")).mean() > 0.5:
            coluna_codigo = coluna
            break

    if coluna_codigo is None:
        print("Nenhuma coluna parece conter códigos de rastreio.")
        return 0

    print("")
    print(f"=== CÓDIGOS (coluna '{coluna_codigo}') ===")

    problemas = Counter()
    exemplos = {}
    vistos = Counter()

    for valor in df[coluna_codigo]:
        tipo = classificar(valor)
        problemas[tipo] += 1
        if tipo != "valido":
            exemplos.setdefault(tipo, str(valor).strip())
        else:
            vistos[str(valor).strip()] += 1

    for tipo, quantidade in problemas.most_common():
        exemplo = exemplos.get(tipo, "")
        sufixo = f"   ex.: {exemplo}" if exemplo else ""
        print(f"  {quantidade:>4}  {tipo}{sufixo}")

    repetidos = [c for c, n in vistos.items() if n > 1]
    print("")
    print(f"  códigos válidos repetidos: {len(repetidos)}")
    if repetidos[:5]:
        print(f"    {', '.join(repetidos[:5])}")

    print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
