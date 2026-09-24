"""Tabela de pedidos — um pedido por código de rastreamento."""

from datetime import datetime

from extensions import db


class Pedido(db.Model):
    __tablename__ = "pedidos"

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(
        db.Integer, db.ForeignKey("clientes.id"), nullable=False, index=True
    )

    # Chave natural do sistema: único, no padrão BR + 12 dígitos + 1 letra.
    codigo_rastreio = db.Column(db.String(15), unique=True, nullable=False, index=True)

    data_cadastro = db.Column(db.Date, nullable=False)
    previsao_entrega = db.Column(db.Date)

    origem = db.Column(db.String(120))
    destino = db.Column(db.String(120))

    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    cliente = db.relationship("Cliente", back_populates="pedidos")
    movimentacoes = db.relationship(
        "Movimentacao",
        back_populates="pedido",
        cascade="all, delete-orphan",
        order_by="Movimentacao.ordem",
        lazy="selectin",
    )

    # ------------------------------------------------------------------
    # Estado da entrega
    #
    # O status NÃO é uma coluna gravada. Ele é lido das movimentações: é o
    # último evento cuja data/hora já passou. Assim ninguém precisa atualizar
    # nada à mão, o computador pode ficar dias desligado, e o valor nunca fica
    # dessincronizado do histórico.
    # ------------------------------------------------------------------

    def movimentacoes_ocorridas(self, agora=None):
        agora = agora or datetime.now()
        return [m for m in self.movimentacoes if m.data_hora <= agora]

    def movimentacoes_previstas(self, agora=None):
        agora = agora or datetime.now()
        return [m for m in self.movimentacoes if m.data_hora > agora]

    @property
    def status_atual(self):
        ocorridas = self.movimentacoes_ocorridas()
        if ocorridas:
            return ocorridas[-1].status
        # Pedido com data futura: ainda não teve nenhum evento.
        return self.movimentacoes[0].status if self.movimentacoes else "Pedido recebido"

    @property
    def movimentacao_atual(self):
        ocorridas = self.movimentacoes_ocorridas()
        return ocorridas[-1] if ocorridas else None

    @property
    def entregue(self):
        return self.status_atual == "Entregue"

    @property
    def progresso(self):
        """Percentual concluído da rota, para a barra do site (0 a 100)."""
        total = len(self.movimentacoes)
        if not total:
            return 0
        return round(len(self.movimentacoes_ocorridas()) / total * 100)

    def __repr__(self):
        return f"<Pedido {self.codigo_rastreio} — {self.status_atual}>"
