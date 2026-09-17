from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from database import db
from modelos.modelos import Usuario

# agrupa todas as rotas de autenticacao neste blueprint
auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/cadastro", methods=["POST"])
def cadastro():
    dados = request.get_json()

    # verifica se o email ja esta cadastrado antes de criar
    if Usuario.query.filter_by(email=dados["email"]).first():
        return jsonify({"erro": "esse email já está em uso"}), 409

    # cria o usuario com a senha ja criptografada, nunca salvamos a senha pura
    novo_usuario = Usuario(
        nome=dados["nome"],
        email=dados["email"],
        senha_hash=generate_password_hash(dados["senha"]),
        renda_mensal=dados.get("renda_mensal", 0.0)
    )

    db.session.add(novo_usuario)
    db.session.commit()

    # gera o token de acesso logo apos o cadastro, nao precisa logar de novo
    token = create_access_token(identity=novo_usuario.id)
    return jsonify({"token": token, "usuario": novo_usuario.para_dict()}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    dados = request.get_json()

    usuario = Usuario.query.filter_by(email=dados["email"]).first()

    # checa se o usuario existe e se a senha bate com o hash salvo
    if not usuario or not check_password_hash(usuario.senha_hash, dados["senha"]):
        return jsonify({"erro": "email ou senha incorretos"}), 401

    token = create_access_token(identity=usuario.id)
    return jsonify({"token": token, "usuario": usuario.para_dict()})


@auth_bp.route("/perfil", methods=["PUT"])
@jwt_required()
def atualizar_perfil():
    usuario_id = get_jwt_identity()
    dados = request.get_json()
    usuario = Usuario.query.get_or_404(usuario_id)

    # atualiza so os campos que foram enviados na requisicao
    if "nome" in dados:
        usuario.nome = dados["nome"]
    if "renda_mensal" in dados:
        usuario.renda_mensal = dados["renda_mensal"]

    db.session.commit()
    return jsonify(usuario.para_dict())