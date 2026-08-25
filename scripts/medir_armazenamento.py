"""
Mede quanto espaço cada pedido ocupa no banco, para saber quantos cabem
no plano gratuito do Neon (0,5 GB).

Cria um banco temporário, enche com pedidos realistas e mede o arquivo.

Uso:
    python scripts/medir_armazenamento.py
"""

import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from config import Config  # noqa: E402
from extensions import db  # noqa: E402
from models import Cliente, Movimentacao, Pedido  # noqa: E402
from services.rastreamento import calcular_previsao, gerar_movimentacoes  # noqa: E402
from services.rotas import montar_rota  # noqa: E402

QUANTIDADE = 2000

# Destinos variados, para o tamanho médio refletir rotas de tamanhos diferentes.
DESTINOS = [
    ("Rio de Janeiro", "RJ"), ("Curitiba", "PR"), ("Manaus", "AM"),
    ("Recife", "PE"), ("Porto Alegre", "RS"), ("Goiânia", "GO"),
    ("São Luís", "MA"), ("Rio Branco", "AC"),
]


def main():
    arquivo = Path(tempfile.gettempdir()) / "verllog_medicao.db"
    try:
        arquivo.unlink(missing_ok=True)
    except OSError:
        pass  # no Windows o arquivo pode ficar preso; nao e problema

    class ConfigMedicao(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{arquivo}"

    app = create_app(ConfigMedicao)

    with app.app_context():
        db.drop_all()
        db.create_all()

        hoje = date.today()
        total_movimentacoes = 0

        for i in range(QUANTIDADE):
            cidade, uf = DESTINOS[i % len(DESTINOS)]
            codigo = f"VL{i:012d}X"

            cliente = Cliente(
                nome=f"Nome Sobrenome Do Cliente Numero {i}",
                cpf=f"{i:03d}.{i:03d}.{i:03d}-{i % 100:02d}",
                endereco=f"Rua de Nome Razoavelmente Longo Numero {i}",
                numero=str(i),
                bairro="Bairro de Teste Com Nome Medio",
                cidade=cidade,
                estado=uf,
                cep=f"{i % 99999:05d}-000",
            )
            db.session.add(cliente)
            db.session.flush()

            eventos = gerar_movimentacoes(
                codigo, hoje - timedelta(days=i % 40), cidade, uf
            )
            rota = montar_rota(cidade, uf)

            pedido = Pedido(
                codigo_rastreio=codigo,
                cliente_id=cliente.id,
                data_cadastro=hoje - timedelta(days=i % 40),
                origem=rota["origem"],
                destino=rota["destino"],
                previsao_entrega=calcular_previsao(eventos),
            )
            db.session.add(pedido)
            db.session.flush()

            for evento in eventos:
                db.session.add(Movimentacao(pedido_id=pedido.id, **evento))
            total_movimentacoes += len(eventos)

            if i % 500 == 0:
                db.session.commit()

        db.session.commit()
        db.session.remove()
        db.engine.dispose()

    tamanho = arquivo.stat().st_size
    por_pedido = tamanho / QUANTIDADE
    limite_neon = 0.5 * 1024 ** 3   # 0,5 GB do plano gratuito

    print("")
    print(f"  pedidos criados ............ {QUANTIDADE:,}".replace(",", "."))
    print(f"  movimentacoes .............. {total_movimentacoes:,}".replace(",", "."))
    print(f"  tamanho do banco ........... {tamanho / 1024 / 1024:.1f} MB")
    print(f"  media por pedido ........... {por_pedido / 1024:.1f} KB")
    print("")
    print(f"  cabem em 0,5 GB (Neon free)  {int(limite_neon / por_pedido):,} pedidos".replace(",", "."))
    print("")

    try:
        arquivo.unlink(missing_ok=True)
    except OSError:
        pass  # no Windows o arquivo pode ficar preso; nao e problema


if __name__ == "__main__":
    main()
