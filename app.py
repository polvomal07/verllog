"""
Verllog Logística — ponto de entrada da aplicação.

Este arquivo só monta a aplicação. As rotas moram em views/ e os comandos de
terminal em comandos.py, para nenhum arquivo virar um depósito de tudo.

Rodar o servidor:
    .\\.venv\\Scripts\\Activate.ps1
    python app.py

Rodar um comando:
    $env:FLASK_APP = "app.py"
    python -m flask importar uploads\\clientes.csv
"""

from flask import Flask, render_template

from comandos import registrar_comandos
from config import Config
from extensions import db


def create_app(config_object=Config):
    """Cria e configura a aplicação Flask."""
    app = Flask(__name__)
    app.config.from_object(config_object)

    # Garante que a pasta de uploads exista antes do primeiro envio.
    app.config["UPLOAD_FOLDER"].mkdir(parents=True, exist_ok=True)

    db.init_app(app)

    # Importar os models registra as tabelas; create_all é seguro de repetir.
    with app.app_context():
        import models  # noqa: F401

        db.create_all()
        restaurar_coluna_codigo()

    registrar_context_processors(app)
    registrar_blueprints(app)
    registrar_erros(app)
    registrar_comandos(app)

    return app


def restaurar_coluna_codigo():
    """
    Por um deploy o código chegou a ser VARCHAR(32) no Postgres. O padrão é
    15 caracteres, então a coluna volta a 15 aqui, uma vez só. SQLite não
    impõe tamanho de VARCHAR, por isso só o Postgres precisa disso.
    """
    if db.engine.dialect.name != "postgresql":
        return
    with db.engine.begin() as conexao:
        tamanho = conexao.exec_driver_sql(
            "SELECT character_maximum_length FROM information_schema.columns"
            " WHERE table_name = 'pedidos' AND column_name = 'codigo_rastreio'"
        ).scalar()
        if tamanho is None or tamanho <= 15:
            return
        # Com algum código maior já gravado, o ALTER falharia e o site não
        # subiria. Nesse caso a coluna fica como está até o pedido sair.
        maiores = conexao.exec_driver_sql(
            "SELECT count(*) FROM pedidos WHERE length(codigo_rastreio) > 15"
        ).scalar()
        if maiores:
            print(
                "codigo_rastreio segue em VARCHAR(" + str(tamanho) + "): "
                + str(maiores) + " pedido(s) com código acima de 15 caracteres."
            )
            return
        conexao.exec_driver_sql(
            "ALTER TABLE pedidos ALTER COLUMN codigo_rastreio TYPE VARCHAR(15)"
        )


def registrar_context_processors(app):
    """Deixa os dados da marca disponíveis em todos os templates."""

    @app.context_processor
    def injetar_identidade():
        from datetime import date

        return {
            "empresa": {
                "nome": app.config["EMPRESA_NOME"],
                "slogan": app.config["EMPRESA_SLOGAN"],
            },
            "ano": date.today().year,
        }


def registrar_blueprints(app):
    from views import admin_bp, publico_bp

    app.register_blueprint(publico_bp)
    app.register_blueprint(admin_bp)


def registrar_erros(app):
    @app.errorhandler(404)
    def pagina_nao_encontrada(_erro):
        return render_template("404.html"), 404

    @app.errorhandler(413)
    def arquivo_grande_demais(_erro):
        return (
            render_template(
                "404.html",
                mensagem="O arquivo enviado passou do limite de 10 MB.",
            ),
            413,
        )


app = create_app()


if __name__ == "__main__":
    # Este bloco só roda no seu computador. Em produção quem sobe a aplicação
    # é o gunicorn (veja o Procfile), que importa o `app` acima e ignora isto.
    import os

    porta = int(os.environ.get("PORT", 5000))

    # host 0.0.0.0 deixa o site acessível também pelo celular na mesma rede.
    app.run(debug=True, host="0.0.0.0", port=porta)
