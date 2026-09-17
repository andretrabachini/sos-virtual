from flask import Flask
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from dotenv import load_dotenv
from datetime import timedelta
import os

from database import db

# carrega as variaveis do arquivo .env
load_dotenv()

# instancia principal do flask
app = Flask(__name__)

# permite que o frontend acesse o backend sem erro de CORS
CORS(app, origins=["http://localhost:3000", "http://127.0.0.1:5500"])

# configuracoes gerais da aplicacao
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///sos_virtual.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "troque-em-producao")

# token de login expira em 7 dias, depois o usuario precisa logar de novo
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(days=7)

# inicializa banco de dados e autenticacao
db.init_app(app)
jwt = JWTManager(app)

# importa e registra as rotas separadas por funcionalidade
from rotas.autenticacao import auth_bp
from rotas.transacoes import transacoes_bp
from rotas.metas import metas_bp
from rotas.dashboard import dashboard_bp
from rotas.alertas import alertas_bp

app.register_blueprint(auth_bp)
app.register_blueprint(transacoes_bp)
app.register_blueprint(metas_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(alertas_bp)

if __name__ == "__main__":
    with app.app_context():
        # cria as tabelas no banco se ainda nao existirem
        db.create_all()
        print("banco de dados pronto")
    app.run(debug=True, port=5000)
