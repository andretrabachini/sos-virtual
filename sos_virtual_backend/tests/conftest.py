# configuracao dos testes: rode `py -m pytest` de dentro de sos_virtual_backend
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# TRAVA DE SEGURANCA: os testes de API usam sempre um banco SQLite em memoria, nunca o do seu .env.
# estas variaveis precisam existir ANTES de importar o app (o app.py nao sobrescreve variaveis ja definidas)
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("JWT_SECRET_KEY", "chave-so-para-testes-" + "x" * 40)
os.environ["SMTP_HOST"] = ""            # nenhum e-mail de verdade sai durante os testes

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine


@event.listens_for(Engine, "connect")
def _chaves_estrangeiras_no_sqlite(conexao, _registro):
    """o SQLite ignora chaves estrangeiras por padrao; o MySQL nao. ligadas aqui, os testes pegam erros de ordem de exclusao"""
    cursor = conexao.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture()
def cliente():
    """cliente HTTP de teste com o banco limpo a cada teste"""
    from app import app, db
    from extensoes import limiter

    assert app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"), "os testes nao podem rodar no banco real"
    with app.app_context():
        db.drop_all()
        db.create_all()
    limiter.enabled = False
    limiter.reset()
    yield app.test_client()
    with app.app_context():
        db.session.remove()
        db.drop_all()
