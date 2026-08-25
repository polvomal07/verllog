"""
Modelos do banco de dados (Fase 2).

Importar este pacote registra as três tabelas no SQLAlchemy:
    clientes  ->  pedidos  ->  movimentacoes
"""

from models.cliente import Cliente
from models.pedido import Pedido
from models.movimentacao import Movimentacao

__all__ = ["Cliente", "Pedido", "Movimentacao"]
