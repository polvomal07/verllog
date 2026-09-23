"""
Gera os ícones do site (favicon) a partir da marca da Verllog.

A marca é a mesma do cabeçalho em templates/base.html: quadrado azul-marinho
com o "V" branco e a bolinha laranja. Se a logo mudar lá, mude aqui também e
rode de novo:

    python scripts/gerar_favicons.py

Precisa do Pillow (pip install pillow). Ele não está no requirements.txt
porque o site não usa: só este script, rodado no seu computador.

Saída em static/img/:
    favicon.svg           navegadores modernos (fica nítido em qualquer tamanho)
    favicon.ico           navegadores antigos e o pedido automático de /favicon.ico
    apple-touch-icon.png  atalho na tela inicial do iPhone
    icon-192.png          atalho na tela inicial do Android
    icon-512.png          tela de abertura no Android
"""

from pathlib import Path

from PIL import Image, ImageDraw

PASTA = Path(__file__).resolve().parent.parent / "static" / "img"

AZUL = "#0a2540"  # --cor-primaria
LARANJA = "#f5a524"  # --cor-acento
BRANCO = "#ffffff"

# Coordenadas no mesmo grid 40x40 do SVG do cabeçalho.
V = [(10, 12.5), (20, 27.5), (30, 12.5)]
TRACO = 3.4
BOLINHA = (30, 12.5, 3.6)
CANTO = 11

SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40">
  <rect width="40" height="40" rx="{CANTO}" fill="{AZUL}"/>
  <path d="M10 12.5 L20 27.5 L30 12.5" fill="none" stroke="{BRANCO}"
        stroke-width="{TRACO}" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="30" cy="12.5" r="3.6" fill="{LARANJA}"/>
</svg>
"""


def desenhar(tamanho, arredondado=True, traco=TRACO):
    """Desenha a marca em 8x o tamanho final e reduz, para bordas suaves."""
    escala = 8
    lado = tamanho * escala
    u = lado / 40  # quanto vale 1 unidade do grid 40x40

    img = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    raio = CANTO * u if arredondado else 0
    d.rounded_rectangle((0, 0, lado - 1, lado - 1), radius=raio, fill=AZUL)

    pontos = [(x * u, y * u) for x, y in V]
    largura = round(traco * u)
    d.line(pontos, fill=BRANCO, width=largura)
    # Pontas e dobra arredondadas, como stroke-linecap/linejoin="round".
    r = largura / 2
    for x, y in pontos:
        d.ellipse((x - r, y - r, x + r, y + r), fill=BRANCO)

    cx, cy, rb = (v * u for v in BOLINHA)
    d.ellipse((cx - rb, cy - rb, cx + rb, cy + rb), fill=LARANJA)

    return img.resize((tamanho, tamanho), Image.LANCZOS)


def main():
    PASTA.mkdir(parents=True, exist_ok=True)

    (PASTA / "favicon.svg").write_text(SVG, encoding="utf-8")

    # Em 16 e 32 px o traço original some; engrossa um pouco para ler na aba.
    icones = [desenhar(t, traco=4.4 if t <= 32 else TRACO) for t in (16, 32, 48)]
    icones[-1].save(
        PASTA / "favicon.ico",
        sizes=[(16, 16), (32, 32), (48, 48)],
        append_images=icones[:-1],
    )

    # O iPhone arredonda os cantos sozinho; entregar quadrado evita borda dupla.
    desenhar(180, arredondado=False).save(PASTA / "apple-touch-icon.png")
    desenhar(192).save(PASTA / "icon-192.png")
    desenhar(512).save(PASTA / "icon-512.png")

    for arquivo in sorted(PASTA.iterdir()):
        print(f"  {arquivo.name:22} {arquivo.stat().st_size:>6} bytes")


if __name__ == "__main__":
    main()
