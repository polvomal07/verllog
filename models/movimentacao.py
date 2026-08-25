"""
Tabela de movimentações — a timeline logística de cada pedido.

As movimentações são geradas UMA vez, no momento da importação, pelo motor de
rotas. Ficam gravadas no banco com data, hora e local definitivos. É isso que
garante o requisito de determinismo: atualizar a página não muda nada, porque
não há sorteio na hora da consulta.
"""

from extensions import db


class Movimentacao(db.Model):
    __tablename__ = "movimentacoes"

    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(
        db.Integer, db.ForeignKey("pedidos.id"), nullable=False, index=True
    )

    ordem = db.Column(db.Integer, nullable=False)
    data_hora = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(60), nullable=False)
    local = db.Column(db.String(120), nullable=False)
    descricao = db.Column(db.String(200))

    pedido = db.relationship("Pedido", back_populates="movimentacoes")

    __table_args__ = (
        db.UniqueConstraint("pedido_id", "ordem", name="uq_movimentacao_ordem"),
    )

    @property
    def data_formatada(self):
        return self.data_hora.strftime("%d/%m/%Y")

    @property
    def hora_formatada(self):
        return self.data_hora.strftime("%H:%M")

    def __repr__(self):
        return f"<Mov {self.ordem} {self.status} @ {self.local}>"
