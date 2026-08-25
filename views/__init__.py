"""
Rotas da aplicação, separadas por público.

  publico.py  — site aberto: home e consulta de rastreamento
  admin.py    — painel restrito: login, dashboard e importação de planilha
"""

from views.admin import admin_bp
from views.publico import publico_bp

__all__ = ["admin_bp", "publico_bp"]
