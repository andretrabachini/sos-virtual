from flask_sqlalchemy import SQLAlchemy

# instancia unica do ORM, usada pelo app e pelos modelos
# a conexao (URL, usuario e senha) vem do .env e e configurada no app.py,
# nunca escreva senha de banco direto no codigo
db = SQLAlchemy()
