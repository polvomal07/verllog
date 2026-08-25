"""
Confere o fluxo real de uso: importar uma planilha sem coluna de data,
deixar o tempo passar e reenviar o MESMO arquivo com clientes novos no fim.

O que precisa acontecer:
  - os pedidos antigos mantêm a data de cadastro original (não voltam ao zero)
  - os pedidos novos entram com a data de hoje
  - nada é duplicado

Uso:
    python scripts/testar_reimportacao.py
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from app import app  # noqa: E402
from config import TestConfig  # noqa: E402
from extensions import db  # noqa: E402
from models import Pedido  # noqa: E402
from services.importador import importar_planilha  # noqa: E402

PASTA = Path(__file__).resolve().parent.parent / "uploads"

# Note que NÃO existe coluna data_cadastro, igual à planilha real.
COLUNAS = ["codigo_rastreio", "nome", "cidade", "estado"]

PRIMEIRO_ENVIO = [
    ("BR900000000001A", "Cliente Um", "Recife", "PE"),
    ("BR900000000002B", "Cliente Dois", "Curitiba", "PR"),
]

SEGUNDO_ENVIO = PRIMEIRO_ENVIO + [
    ("BR900000000003C", "Cliente Tres", "Salvador", "BA"),
]


def gravar(linhas, nome):
    caminho = PASTA / nome
    pd.DataFrame(linhas, columns=COLUNAS).to_excel(caminho, index=False)
    return caminho


def main():
    # Banco em memória: o teste não encosta no banco de verdade.
    app.config.from_object(TestConfig)

    with app.app_context():
        db.drop_all()
        db.create_all()

        print("\n=== 1o envio (2 pedidos) ===")
        r1 = importar_planilha(gravar(PRIMEIRO_ENVIO, "_teste_envio1.xlsx"))
        print(f"  adicionados: {r1['adicionados']}  atualizados: {r1['atualizados']}")

        # Simula que esses pedidos foram cadastrados 12 dias atrás.
        doze_dias_atras = date.today() - timedelta(days=12)
        for pedido in Pedido.query.all():
            pedido.data_cadastro = doze_dias_atras
        db.session.commit()

        print(f"\n  (fingindo que se passaram 12 dias)")
        for p in Pedido.query.order_by(Pedido.codigo_rastreio):
            print(f"  {p.codigo_rastreio}  cadastro {p.data_cadastro.strftime('%d/%m')}  {p.status_atual}")

        print("\n=== 2o envio: MESMO arquivo + 1 cliente novo ===")
        r2 = importar_planilha(gravar(SEGUNDO_ENVIO, "_teste_envio2.xlsx"))
        print(f"  adicionados: {r2['adicionados']}  atualizados: {r2['atualizados']}")

        print("\n=== resultado ===")
        ok = True
        for p in Pedido.query.order_by(Pedido.codigo_rastreio):
            print(f"  {p.codigo_rastreio}  cadastro {p.data_cadastro.strftime('%d/%m')}  {p.status_atual}")

        antigos = Pedido.query.filter(
            Pedido.codigo_rastreio.in_(["BR900000000001A", "BR900000000002B"])
        ).all()
        novo = Pedido.query.filter_by(codigo_rastreio="BR900000000003C").first()

        print("")
        for p in antigos:
            manteve = p.data_cadastro == doze_dias_atras
            ok = ok and manteve
            print(f"  {p.codigo_rastreio} manteve a data original: {'OK' if manteve else 'FALHOU'}")

        novo_hoje = novo is not None and novo.data_cadastro == date.today()
        ok = ok and novo_hoje
        print(f"  BR900000000003C entrou com a data de hoje: {'OK' if novo_hoje else 'FALHOU'}")

        total_certo = Pedido.query.count() == 3
        ok = ok and total_certo
        print(f"  total de 3 pedidos (nada duplicado): {'OK' if total_certo else 'FALHOU'}")

        print("\n" + ("TUDO CERTO." if ok else "ALGUM TESTE FALHOU."))

        for nome in ("_teste_envio1.xlsx", "_teste_envio2.xlsx"):
            (PASTA / nome).unlink(missing_ok=True)

        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
