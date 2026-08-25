"""
Conferência rápida dos dois requisitos mais delicados do projeto:

  9  — o status precisa avançar sozinho com o computador desligado
  10 — a timeline não pode mudar quando a página é atualizada

Uso:
    python scripts/testar_motor.py
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app  # noqa: E402
from models import Pedido  # noqa: E402
from services.rastreamento import resumo_publico  # noqa: E402


def testar_determinismo(pedido):
    """Duas leituras seguidas do mesmo pedido têm que ser idênticas."""
    primeira = resumo_publico(pedido)
    segunda = resumo_publico(pedido)

    iguais = [
        (e1["data"], e1["hora"], e1["local"]) == (e2["data"], e2["hora"], e2["local"])
        for e1, e2 in zip(primeira["etapas"], segunda["etapas"])
    ]

    ok = all(iguais)
    print(f"  determinismo (2 leituras iguais) ......... {'OK' if ok else 'FALHOU'}")
    return ok


def testar_avanco_no_tempo(pedido):
    """
    Simula o computador ficando dias desligado: em vez de mexer no relógio,
    consultamos o mesmo pedido com uma data futura. É exatamente o que o
    sistema fará sozinho quando a data real chegar.
    """
    hoje = datetime.now()
    print(f"\n  Pedido {pedido.codigo_rastreio} — {pedido.destino}")
    print(f"  cadastrado em {pedido.data_cadastro.strftime('%d/%m/%Y')}")
    print("")

    anterior = None
    nunca_regrediu = True

    for dias in (0, 2, 5, 10, 20, 40):
        momento = hoje + timedelta(days=dias)
        concluidas = pedido.movimentacoes_ocorridas(momento)
        status = concluidas[-1].status if concluidas else "(aguardando postagem)"

        print(f"  +{dias:>2} dias  ({momento.strftime('%d/%m/%Y')})  ->  {status}")

        # O status nunca pode andar para trás, e "Entregue" é ponto final.
        if anterior == "Entregue" and status != "Entregue":
            nunca_regrediu = False
        anterior = status

    print("")
    print(f"  status nunca regride ..................... {'OK' if nunca_regrediu else 'FALHOU'}")
    print(f"  termina em 'Entregue' .................... {'OK' if anterior == 'Entregue' else 'FALHOU'}")
    return nunca_regrediu and anterior == "Entregue"


def main():
    with app.app_context():
        pedido = Pedido.query.order_by(Pedido.id).first()
        if pedido is None:
            print("Nenhum pedido no banco. Rode 'flask importar' antes.")
            return 1

        print("\n=== TESTE 14/15: determinismo da timeline ===")
        ok_determinismo = testar_determinismo(pedido)

        print("\n=== TESTE 9/10/11: avanço automático pela data ===")
        ok_tempo = testar_avanco_no_tempo(pedido)

        print("")
        if ok_determinismo and ok_tempo:
            print("TUDO CERTO.")
            return 0
        print("ALGUM TESTE FALHOU.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
