"""Tabela de clientes (destinatários fictícios)."""

from datetime import datetime

from extensions import db


class Cliente(db.Model):
    __tablename__ = "clientes"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    cpf = db.Column(db.String(14), index=True)
    endereco = db.Column(db.String(200))
    numero = db.Column(db.String(20))
    bairro = db.Column(db.String(100))
    cidade = db.Column(db.String(100), nullable=False, index=True)
    estado = db.Column(db.String(2), nullable=False, index=True)
    cep = db.Column(db.String(9))
    criado_em = db.Column(db.DateTime, default=datetime.now)

    pedidos = db.relationship(
        "Pedido",
        back_populates="cliente",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # ------------------------------------------------------------------
    # Apresentação
    # ------------------------------------------------------------------

    @property
    def cidade_uf(self):
        return f"{self.cidade}/{self.estado}"

    @property
    def endereco_completo(self):
        """Endereço sem máscara — uso exclusivo do painel administrativo."""
        partes = [p for p in [self.endereco, self.numero, self.bairro] if p]
        return f"{', '.join(partes)} — {self.cidade_uf} — CEP {self.cep or 's/ CEP'}"

    @property
    def cpf_mascarado(self):
        """Mostra apenas os dois últimos dígitos: ***.***.***-00"""
        if not self.cpf:
            return "***.***.***-**"
        digitos = "".join(c for c in self.cpf if c.isdigit())
        if len(digitos) < 2:
            return "***.***.***-**"
        return f"***.***.***-{digitos[-2:]}"

    @property
    def endereco_mascarado(self):
        """Versão pública: rua sem o número, para não expor o endereço exato."""
        if not self.endereco:
            return self.cidade_uf
        return f"{self.endereco}, ***"

    @property
    def nome_publico(self):
        """
        Primeiro nome + inicial do sobrenome, como fazem as transportadoras
        reais na tela pública de rastreio.
        """
        partes = self.nome.split()
        if len(partes) == 1:
            return partes[0]
        return f"{partes[0]} {partes[-1][0]}."

    def __repr__(self):
        return f"<Cliente {self.id} {self.nome} — {self.cidade_uf}>"
