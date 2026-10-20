import re
from datetime import datetime

from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash

from database import db
from extensoes import limiter, usuario_id_atual
from modelos.modelos import Usuario

# agrupa todas as rotas de autenticacao neste blueprint
auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SENHA_MIN, SENHA_MAX = 8, 128      # o maximo evita ataques com senhas gigantes (hash e caro)
RENDA_MAX = 10_000_000

# hash de mentira, usado no login quando o email nao existe: assim a resposta
# demora o mesmo tempo e ninguem descobre quais emails estao cadastrados
HASH_FALSO = generate_password_hash("senha-falsa-para-tempo-constante")


def _erro(mensagem, status):
    return jsonify({"erro": mensagem}), status


def _corpo_json():
    # get_json(silent=True) nao estoura erro se o corpo vier quebrado ou vazio
    dados = request.get_json(silent=True)
    return dados if isinstance(dados, dict) else None


def _texto(valor):
    # so aceita texto de verdade (nada de listas, numeros ou objetos disfarçados)
    return valor.strip() if isinstance(valor, str) else ""


def _numero(valor, minimo, maximo):
    # bool e subclasse de int em Python, por isso rejeitamos explicitamente
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    # valor != valor detecta NaN
    if valor != valor or valor < minimo or valor > maximo:
        return None
    return float(valor)


@auth_bp.route("/cadastro", methods=["POST"])
@limiter.limit("10 per hour")
def cadastro():
    dados = _corpo_json()
    if dados is None:
        return _erro("corpo da requisição inválido", 400)

    nome = _texto(dados.get("nome"))
    email = _texto(dados.get("email")).lower()
    senha = dados.get("senha")

    if not 2 <= len(nome) <= 120:
        return _erro("informe seu nome (2 a 120 caracteres)", 400)
    if len(email) > 120 or not EMAIL_RE.match(email):
        return _erro("e-mail inválido", 400)
    if not isinstance(senha, str) or not SENHA_MIN <= len(senha) <= SENHA_MAX:
        return _erro(f"a senha deve ter entre {SENHA_MIN} e {SENHA_MAX} caracteres", 400)

    # renda e opcional; se vier, precisa ser numero valido
    renda = 0.0
    if dados.get("renda_mensal") not in (None, ""):
        renda = _numero(dados.get("renda_mensal"), 0, RENDA_MAX)
        if renda is None:
            return _erro("renda mensal inválida", 400)

    # a LGPD exige consentimento: sem o aceite explicito nao criamos a conta
    if dados.get("lgpd_aceito") is not True:
        return _erro("é necessário aceitar o tratamento de dados (LGPD)", 400)

    # verifica se o email ja esta cadastrado antes de criar
    if Usuario.query.filter_by(email=email).first():
        return _erro("esse email já está em uso", 409)

    # cria o usuario com a senha ja criptografada, nunca salvamos a senha pura
    novo_usuario = Usuario(
        nome=nome,
        email=email,
        senha_hash=generate_password_hash(senha),
        renda_mensal=renda,
        lgpd_aceito_em=datetime.utcnow(),  # registra quando o consentimento foi dado
    )

    db.session.add(novo_usuario)
    try:
        db.session.commit()
    except IntegrityError:
        # duas requisicoes simultaneas com o mesmo email: o banco barra a segunda
        db.session.rollback()
        return _erro("esse email já está em uso", 409)

    # o token guarda o id como texto (exigencia das versoes novas do JWT)
    token = create_access_token(identity=str(novo_usuario.id))
    return jsonify({"token": token, "usuario": novo_usuario.para_dict()}), 201


@auth_bp.route("/login", methods=["POST"])
@limiter.limit("5 per minute; 30 per hour")
def login():
    dados = _corpo_json()
    if dados is None:
        return _erro("corpo da requisição inválido", 400)

    email = _texto(dados.get("email")).lower()
    senha = dados.get("senha")
    if not isinstance(senha, str) or len(senha) > SENHA_MAX:
        return _erro("email ou senha incorretos", 401)

    usuario = Usuario.query.filter_by(email=email).first() if email else None

    # sempre confere um hash (o verdadeiro ou o falso), para o tempo de resposta
    # nao revelar se o email existe
    senha_ok = check_password_hash(usuario.senha_hash if usuario else HASH_FALSO, senha)

    # mensagem unica para email inexistente e senha errada
    if not usuario or not senha_ok:
        return _erro("email ou senha incorretos", 401)

    token = create_access_token(identity=str(usuario.id))
    return jsonify({"token": token, "usuario": usuario.para_dict()})


@auth_bp.route("/perfil", methods=["PUT"])
@jwt_required()
def atualizar_perfil():
    dados = _corpo_json()
    if dados is None:
        return _erro("corpo da requisição inválido", 400)

    usuario = db.session.get(Usuario, usuario_id_atual())
    if not usuario:
        return _erro("usuário não encontrado", 404)

    # atualiza so os campos que foram enviados, validando cada um
    if "nome" in dados:
        nome = _texto(dados["nome"])
        if not 2 <= len(nome) <= 120:
            return _erro("nome inválido (2 a 120 caracteres)", 400)
        usuario.nome = nome

    if "renda_mensal" in dados:
        renda = _numero(dados["renda_mensal"], 0, RENDA_MAX)
        if renda is None:
            return _erro("renda mensal inválida", 400)
        usuario.renda_mensal = renda

    db.session.commit()
    return jsonify(usuario.para_dict())


# ---------- direitos do titular (LGPD, art. 18) ----------

@auth_bp.route("/meus-dados", methods=["GET"])
@jwt_required()
def exportar_dados():
    """devolve todos os dados que o sistema guarda sobre o usuario (portabilidade e acesso)"""
    usuario = db.session.get(Usuario, usuario_id_atual())
    if not usuario:
        return _erro("usuário não encontrado", 404)

    return jsonify({
        "usuario": {
            **usuario.para_dict(),
            "criado_em": usuario.criado_em.isoformat() if usuario.criado_em else None,
            "lgpd_aceito_em": usuario.lgpd_aceito_em.isoformat() if usuario.lgpd_aceito_em else None,
        },
        "transacoes": [t.para_dict() for t in usuario.transacoes],
        "metas": [m.para_dict() for m in usuario.metas],
        "alertas": [a.para_dict() for a in usuario.alertas],
    })


@auth_bp.route("/conta", methods=["DELETE"])
@jwt_required()
@limiter.limit("5 per hour")
def excluir_conta():
    """apaga a conta e todos os dados do usuario (direito de eliminacao)"""
    dados = _corpo_json() or {}
    usuario = db.session.get(Usuario, usuario_id_atual())
    if not usuario:
        return _erro("usuário não encontrado", 404)

    # pede a senha de novo: um token roubado sozinho nao basta para apagar a conta
    senha = dados.get("senha")
    if not isinstance(senha, str) or not check_password_hash(usuario.senha_hash, senha):
        return _erro("senha incorreta", 403)

    db.session.delete(usuario)  # o cascade do modelo apaga transacoes, metas e alertas
    db.session.commit()
    return jsonify({"mensagem": "conta e dados removidos"})
