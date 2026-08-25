"""
Testa o fluxo do painel pelo navegador simulado: login, upload de CSV e
consulta pública do código importado.

Uso:
    python scripts/testar_upload_web.py
"""

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app  # noqa: E402
from config import Config  # noqa: E402
from models import Pedido  # noqa: E402

CSV_TESTE = """codigo_rastreio;nome;cpf;endereco;numero;bairro;cidade;estado;cep;data_cadastro
BR880011223344J;Teste Upload Web;123.456.789-00;Rua do Teste;99;Centro;Curitiba;PR;80010-000;15/08/2026
"""


def main():
    app.config["WTF_CSRF_ENABLED"] = False
    cliente = app.test_client()

    print("\n=== 1. Painel sem login ===")
    resposta = cliente.get("/admin/", follow_redirects=False)
    print(f"  /admin/ -> HTTP {resposta.status_code} (esperado 302, manda pro login)")

    print("\n=== 2. Login com senha errada ===")
    resposta = cliente.post(
        "/admin/login", data={"usuario": "admin", "senha": "errada"}
    )
    negou = "incorretos" in resposta.get_data(as_text=True)
    print(f"  recusou o acesso: {'OK' if negou else 'FALHOU'}")

    print("\n=== 3. Login correto ===")
    resposta = cliente.post(
        "/admin/login",
        data={
            "usuario": Config.ADMIN_USUARIO,
            "senha": Config.ADMIN_SENHA,
        },
        follow_redirects=True,
    )
    entrou = "Painel administrativo" in resposta.get_data(as_text=True)
    print(f"  entrou no painel: {'OK' if entrou else 'FALHOU'}")

    print("\n=== 4. Upload de CSV pelo painel ===")
    arquivo = (io.BytesIO(CSV_TESTE.encode("utf-8")), "clientes_teste.csv")
    resposta = cliente.post(
        "/admin/importar",
        data={"planilha": arquivo},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    html = resposta.get_data(as_text=True)
    importou = "Importação concluída" in html
    print(f"  HTTP {resposta.status_code}")
    print(f"  importou: {'OK' if importou else 'FALHOU'}")

    print("\n=== 5. Arquivo com extensão proibida ===")
    ruim = (io.BytesIO(b"nada"), "virus.exe")
    resposta = cliente.post(
        "/admin/importar",
        data={"planilha": ruim},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    recusou = "Formato não aceito" in resposta.get_data(as_text=True)
    print(f"  recusou .exe: {'OK' if recusou else 'FALHOU'}")

    print("\n=== 6. Consulta pública do código importado ===")
    resposta = cliente.get("/rastreamento?codigo=BR880011223344J")
    html = resposta.get_data(as_text=True)
    achou = "Pedido encontrado" in html
    tem_timeline = "linha-tempo" in html
    print(f"  HTTP {resposta.status_code}")
    print(f"  encontrou o pedido: {'OK' if achou else 'FALHOU'}")
    print(f"  renderizou a timeline: {'OK' if tem_timeline else 'FALHOU'}")

    print("\n=== 7. Código inexistente ===")
    resposta = cliente.get("/rastreamento?codigo=BR111111111111A")
    educado = "não encontrado" in resposta.get_data(as_text=True)
    print(f"  HTTP {resposta.status_code} (esperado 404)")
    print(f"  mensagem amigável: {'OK' if educado else 'FALHOU'}")

    print("\n=== 8. Busca em minúscula (usuário digitando) ===")
    resposta = cliente.get("/rastreamento?codigo=br880011223344j")
    achou_min = "Pedido encontrado" in resposta.get_data(as_text=True)
    print(f"  aceitou minúscula: {'OK' if achou_min else 'FALHOU'}")

    with app.app_context():
        total = Pedido.query.count()
    print(f"\nTotal de pedidos no banco: {total}")
    print("")


if __name__ == "__main__":
    main()
