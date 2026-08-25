"""
Extensões compartilhadas da aplicação.

Fica em arquivo separado para evitar importação circular: os models importam
`db` daqui, e o app.py conecta o `db` à aplicação com db.init_app(app).
"""

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
