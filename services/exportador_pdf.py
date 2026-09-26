"""
Exportação do rastreio em PDF (uso exclusivo do painel).

O histórico reproduz o que o CLIENTE vê em /rastreamento: só as etapas que
já aconteceram, da mais recente para a mais antiga. Por isso vem de
resumo_publico(), a mesma função da página pública, e não da rota completa
que o painel mostra.

Os dados do destinatário (nome, CPF e endereço) saem COMPLETOS, sem a
máscara do site: o PDF só é gerado no painel, para quem está logado.

Usa as fontes padrão do PDF (Helvetica), que cobrem os acentos do português
sem precisar embutir arquivo de fonte. Qualquer caractere fora desse
conjunto (emoji num nome de planilha, por exemplo) vira "?" em vez de
derrubar a exportação.
"""

from datetime import datetime

from fpdf import FPDF

from config import Config
from services.rastreamento import resumo_publico

# Mesmas cores do site (static/css/style.css).
PRIMARIA = (10, 37, 64)
ACENTO = (245, 165, 36)
SUCESSO = (22, 163, 74)
TEXTO = (15, 27, 43)
TEXTO_SUAVE = (91, 107, 127)
BORDA = (226, 232, 240)
FUNDO_SUAVE = (246, 248, 251)

MARGEM = 18


def _t(texto):
    """Deixa o texto dentro do que a fonte padrão do PDF consegue escrever."""
    return str(texto or "").encode("latin-1", "replace").decode("latin-1")


class _Documento(FPDF):
    def __init__(self):
        super().__init__(format="A4")
        self.gerado_em = datetime.now()
        self.set_margins(MARGEM, MARGEM, MARGEM)
        self.set_auto_page_break(auto=True, margin=22)
        self.set_title("Rastreamento " + Config.EMPRESA_NOME)
        self.set_author(Config.EMPRESA_NOME)

    def header(self):
        self.set_fill_color(*PRIMARIA)
        self.rect(0, 0, self.w, 24, "F")
        self.set_fill_color(*ACENTO)
        self.rect(0, 24, self.w, 1.2, "F")

        self.set_xy(MARGEM, 8)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 15)
        self.cell(0, 8, _t(Config.EMPRESA_NOME))
        self.set_xy(MARGEM, 8)
        self.set_font("Helvetica", "", 9)
        self.cell(0, 8, _t(Config.EMPRESA_SLOGAN), align="R")
        self.set_y(34)

    def footer(self):
        self.set_y(-14)
        self.set_draw_color(*BORDA)
        self.line(MARGEM, self.get_y() - 2, self.w - MARGEM, self.get_y() - 2)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*TEXTO_SUAVE)
        self.cell(
            0,
            6,
            _t(
                "Uso interno  ·  Gerado em "
                + self.gerado_em.strftime("%d/%m/%Y às %H:%M")
                + "  ·  verllog.com"
            ),
        )
        self.set_x(MARGEM)
        self.cell(0, 6, "Página " + str(self.page_no()), align="R")

    # ------------------------------------------------------------------
    # Blocos
    # ------------------------------------------------------------------

    def _rotulo(self, texto):
        self.set_font("Helvetica", "B", 7.5)
        self.set_text_color(*TEXTO_SUAVE)
        self.cell(0, 5, _t(texto.upper()), new_x="LMARGIN", new_y="NEXT")

    def cabecalho_pedido(self, dados):
        largura = self.w - 2 * MARGEM

        self._rotulo("Código de rastreamento")
        topo = self.get_y()
        self.set_font("Helvetica", "B", 22)
        self.set_text_color(*PRIMARIA)
        self.cell(0, 10, _t(dados["codigo"]))

        # Etiqueta do status, alinhada à direita na mesma linha do código.
        self.set_font("Helvetica", "B", 9)
        texto_status = _t(dados["status"])
        largura_etiqueta = self.get_string_width(texto_status) + 10
        self.set_fill_color(*(SUCESSO if dados["entregue"] else ACENTO))
        self.set_text_color(*((255, 255, 255) if dados["entregue"] else (35, 24, 10)))
        self.set_xy(self.w - MARGEM - largura_etiqueta, topo + 1.5)
        self.cell(largura_etiqueta, 7, texto_status, align="C", fill=True)

        self.set_xy(MARGEM, topo + 11)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*TEXTO_SUAVE)
        self.cell(0, 6, _t("Destino: " + dados["destino"]), new_x="LMARGIN", new_y="NEXT")

        # Barra de progresso.
        self.ln(3)
        y = self.get_y()
        self.set_fill_color(*BORDA)
        self.rect(MARGEM, y, largura, 2.5, "F")
        self.set_fill_color(*(SUCESSO if dados["entregue"] else ACENTO))
        self.rect(MARGEM, y, largura * dados["progresso"] / 100, 2.5, "F")
        self.set_y(y + 7)

        self.set_font("Helvetica", "", 9.5)
        self.set_text_color(*TEXTO_SUAVE)
        self.cell(
            0,
            5,
            _t("Origem: " + dados["origem"] + "  ·  Postado em " + dados["data_cadastro"]),
            new_x="LMARGIN",
            new_y="NEXT",
        )
        self.ln(5)

    def linha_do_tempo(self, dados):
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(*TEXTO)
        self.cell(0, 8, _t("Histórico da encomenda"), new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

        x_marcador = MARGEM + 3
        x_texto = MARGEM + 11
        largura_texto = self.w - MARGEM - x_texto
        altura_etapa = 15

        etapas = dados["etapas"]
        for indice, etapa in enumerate(etapas):
            if self.get_y() + altura_etapa > self.page_break_trigger:
                self.add_page()

            y = self.get_y()

            # Traço ligando à próxima etapa (não atravessa a quebra de página).
            if indice < len(etapas) - 1:
                self.set_draw_color(*BORDA)
                self.set_line_width(0.6)
                self.line(x_marcador, y + 3, x_marcador, y + altura_etapa)

            self.set_fill_color(*(ACENTO if etapa["atual"] else SUCESSO))
            raio = 2.2 if etapa["atual"] else 1.7
            self.ellipse(x_marcador - raio, y + 3 - raio, raio * 2, raio * 2, "F")

            self.set_xy(x_texto, y)
            self.set_font("Helvetica", "B", 10.5)
            self.set_text_color(*TEXTO)
            self.cell(largura_texto, 5, _t(etapa["status"]), new_x="LEFT", new_y="NEXT")
            self.set_font("Helvetica", "", 9)
            self.set_text_color(*TEXTO_SUAVE)
            self.cell(
                largura_texto,
                4,
                _t(etapa["data"] + " às " + etapa["hora"] + "  ·  " + etapa["local"]),
                new_x="LEFT",
                new_y="NEXT",
            )
            self.set_text_color(*TEXTO)
            self.multi_cell(largura_texto, 4, _t(etapa["descricao"]), new_x="LMARGIN", new_y="NEXT")
            self.set_y(max(self.get_y() + 2, y + altura_etapa))

        if not dados["entregue"]:
            self.set_font("Helvetica", "I", 9)
            self.set_text_color(*TEXTO_SUAVE)
            self.multi_cell(
                0,
                5,
                _t(
                    "As próximas movimentações serão exibidas na página de "
                    "rastreamento assim que forem registradas."
                ),
                new_x="LMARGIN",
                new_y="NEXT",
            )
            self.ln(3)

    def _campo(self, x, y, largura, rotulo, valor):
        """Rótulo pequeno em cima e valor embaixo; a fonte encolhe se não couber."""
        self.set_xy(x, y)
        self.set_font("Helvetica", "B", 7.5)
        self.set_text_color(*TEXTO_SUAVE)
        self.cell(largura, 4.5, _t(rotulo.upper()))

        valor = _t(valor)
        tamanho = 10
        self.set_font("Helvetica", "B", tamanho)
        while tamanho > 7 and self.get_string_width(valor) > largura:
            tamanho -= 0.5
            self.set_font("Helvetica", "B", tamanho)
        self.set_xy(x, y + 4.5)
        self.set_text_color(*TEXTO)
        self.cell(largura, 5.5, valor)

    def destinatario(self, cliente):
        """Dados completos, sem máscara: o PDF é de uso exclusivo do painel."""
        altura = 44
        if self.get_y() + altura + 4 > self.page_break_trigger:
            self.add_page()

        largura = self.w - 2 * MARGEM
        y = self.get_y() + 2
        self.set_draw_color(*BORDA)
        self.set_line_width(0.3)
        self.set_fill_color(*FUNDO_SUAVE)
        self.rect(MARGEM, y, largura, altura, "DF")

        self.set_xy(MARGEM + 5, y + 4)
        self.set_font("Helvetica", "B", 10.5)
        self.set_text_color(*TEXTO)
        self.cell(0, 5.5, "Dados do destinatário")

        rua = ", ".join(parte for parte in (cliente.endereco, cliente.numero) if parte)
        linhas = [
            (("Nome", cliente.nome), ("CPF", cliente.cpf_formatado or "não informado")),
            (("Endereço de entrega", rua or "não informado"), ("CEP", cliente.cep or "não informado")),
            (("Bairro", cliente.bairro or "não informado"), ("Cidade / UF", cliente.cidade_uf)),
        ]
        interno = largura - 10
        larga, estreita = interno * 0.66, interno * 0.34
        for indice, (esquerda, direita) in enumerate(linhas):
            linha_y = y + 11 + indice * 10.5
            self._campo(MARGEM + 5, linha_y, larga - 6, *esquerda)
            self._campo(MARGEM + 5 + larga, linha_y, estreita, *direita)

        self.set_y(y + altura + 8)


def gerar_pdf(pedidos, agora=None):
    """Um pedido por página (ou mais, se o histórico for longo). Devolve bytes."""
    documento = _Documento()
    for pedido in pedidos:
        dados = resumo_publico(pedido, agora=agora)
        documento.add_page()
        documento.cabecalho_pedido(dados)
        documento.destinatario(pedido.cliente)
        documento.linha_do_tempo(dados)
    return bytes(documento.output())
