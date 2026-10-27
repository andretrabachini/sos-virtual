import os
from datetime import timedelta

from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from database import db
from extensoes import limiter

# carrega as variaveis do arquivo .env
load_dotenv()

# ---------- configuracao segura ----------
# sem chave secreta forte o app nem inicia: uma chave fraca ou padrao
# permite que qualquer pessoa forje tokens de login
chave_jwt = os.getenv("JWT_SECRET_KEY", "")
if len(chave_jwt) < 32:
    raise RuntimeError(
        "JWT_SECRET_KEY ausente ou curta demais (minimo 32 caracteres). "
        "Gere uma com: python -c \"import secrets; print(secrets.token_urlsafe(64))\" "
        "e coloque no arquivo .env"
    )

app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///sos_virtual.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JWT_SECRET_KEY"] = chave_jwt

# token curto: se for roubado, vale por pouco tempo (padrao 60 minutos)
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(
    minutes=int(os.getenv("JWT_EXPIRES_MINUTES", "60"))
)

# recusa requisicoes grandes demais (protege contra upload abusivo de extratos)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # 2 MB

# so os enderecos listados no .env podem chamar a API pelo navegador
origens = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5500,http://127.0.0.1:5500,http://localhost:3000",
    ).split(",")
    if o.strip()
]
CORS(app, resources={r"/api/*": {"origins": origens}})

db.init_app(app)
jwt = JWTManager(app)
limiter.init_app(app)


# ---------- respostas de erro do JWT (sempre 401 + JSON no padrao do front) ----------
@jwt.unauthorized_loader
def token_ausente(motivo):
    return jsonify({"erro": "faça login para continuar"}), 401


@jwt.invalid_token_loader
def token_invalido(motivo):
    return jsonify({"erro": "sessão inválida, faça login novamente"}), 401


@jwt.expired_token_loader
def token_expirado(cabecalho, dados):
    return jsonify({"erro": "sessão expirada, faça login novamente"}), 401


# ---------- cabecalhos de seguranca em todas as respostas ----------
@app.after_request
def cabecalhos_seguranca(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    # a API so devolve JSON, entao nada de scripts ou recursos externos
    resp.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    # dados financeiros nao devem ficar guardados em cache do navegador
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ---------- erros sempre em JSON, sem vazar detalhes internos ----------
@app.errorhandler(400)
def erro_400(e):
    return jsonify({"erro": "requisição inválida"}), 400


@app.errorhandler(404)
def erro_404(e):
    return jsonify({"erro": "recurso não encontrado"}), 404


@app.errorhandler(405)
def erro_405(e):
    return jsonify({"erro": "método não permitido"}), 405


@app.errorhandler(413)
def erro_413(e):
    return jsonify({"erro": "arquivo ou requisição grande demais (máximo 2 MB)"}), 413


@app.errorhandler(429)
def erro_429(e):
    return jsonify({"erro": "muitas tentativas, aguarde um pouco e tente de novo"}), 429


@app.errorhandler(500)
def erro_500(e):
    # desfaz qualquer transacao pela metade e nao mostra o erro real ao cliente
    db.session.rollback()
    return jsonify({"erro": "erro interno do servidor"}), 500


# ---------- rotas ----------
from rotas.autenticacao import auth_bp
from rotas.transacoes import transacoes_bp
from rotas.metas import metas_bp
from rotas.dashboard import dashboard_bp
from rotas.alertas import alertas_bp
from rotas.simulacoes import simulacoes_bp
from rotas.grafos import grafos_bp
from rotas.parcelamentos import parcelamentos_bp

app.register_blueprint(auth_bp)
app.register_blueprint(transacoes_bp)
app.register_blueprint(metas_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(alertas_bp)
app.register_blueprint(simulacoes_bp)
app.register_blueprint(grafos_bp)
app.register_blueprint(parcelamentos_bp)

if __name__ == "__main__":
    with app.app_context():
        # cria as tabelas no banco se ainda nao existirem
        db.create_all()
        print("banco de dados pronto")

    # debug so liga se o .env pedir (FLASK_DEBUG=1), e o servidor so escuta
    # na propria maquina: o modo debug permite executar codigo remotamente
    app.run(
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
        host="127.0.0.1",
        port=5000,
    )
