import hashlib
import os
from collections import defaultdict
import re
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required
from flask_limiter.util import get_remote_address
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash

from database import db
from extensoes import limiter, usuario_id_atual
from modelos.modelos import ContaCategoria, No, RedefinicaoSenha, Usuario
from servicos.email_service import enviar_email_redefinicao, enviar_email_senha_alterada

# agrupa todas as rotas de autenticacao neste blueprint
auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SENHA_MIN, SENHA_MAX = 8, 128      # o maximo evita ataques com senhas gigantes (hash e caro)
RENDA_MAX = 10_000_000

# hash de mentira, usado no login quando o email nao existe: assim a resposta
# demora o mesmo tempo e ninguem descobre quais emails estao cadastrados
HASH_FALSO = generate_password_hash("senha-falsa-para-tempo-constante")

# validade do link de redefinicao e endereco do front-end (usado para montar o link do e-mail)
# o endereco vem do .env e nunca do cabecalho da requisicao: assim ninguem consegue fazer o
# sistema mandar e-mails com link para um site falso
RESET_MINUTOS = int(os.getenv("RESET_EXPIRES_MINUTES", "30"))
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://127.0.0.1:5500/sos_virtual_frontend").rstrip("/")
MSG_ESQUECI = ("Se esse e-mail estiver cadastrado, enviamos um link para redefinir a senha. "
               f"Ele vale por {RESET_MINUTOS} minutos.")
MSG_LINK_INVALIDO = "link inválido ou expirado: peça uma nova redefinição de senha"


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


# ---------- recuperacao de senha ----------
# a senha e guardada como hash e nao pode ser "recuperada": o usuario recebe por e-mail um link
# de uso unico, com validade curta, para criar uma nova

def _hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _chave_email():
    # limita tambem por e-mail, para ninguem lotar a caixa de entrada de outra pessoa
    dados = request.get_json(silent=True)
    email = _texto(dados.get("email")).lower() if isinstance(dados, dict) else ""
    return "email:" + (email[:120] or get_remote_address())


@auth_bp.route("/esqueci-senha", methods=["POST"])
@limiter.limit("5 per hour")
@limiter.limit("3 per hour", key_func=_chave_email)
def esqueci_senha():
    dados = _corpo_json()
    if dados is None:
        return _erro("corpo da requisição inválido", 400)

    email = _texto(dados.get("email")).lower()
    if not email or len(email) > 120 or not EMAIL_RE.match(email):
        return _erro("informe um e-mail válido", 400)

    agora = datetime.utcnow()
    usuario = Usuario.query.filter_by(email=email).first()

    if usuario:
        # limpeza: apaga pedidos vencidos ha mais de um dia
        RedefinicaoSenha.query.filter(
            RedefinicaoSenha.expira_em < agora - timedelta(days=1)
        ).delete(synchronize_session=False)

        # um pedido ativo por vez: o link mais novo invalida os anteriores
        RedefinicaoSenha.query.filter_by(usuario_id=usuario.id, usado_em=None).update({"usado_em": agora})

        token = secrets.token_urlsafe(32)  # 256 bits aleatorios
        db.session.add(RedefinicaoSenha(
            usuario_id=usuario.id,
            token_hash=_hash_token(token),
            expira_em=agora + timedelta(minutes=RESET_MINUTOS),
        ))
        db.session.commit()

        # o token vai depois do "#": o navegador nao envia essa parte ao servidor,
        # entao ela nao aparece em logs nem em cabecalhos Referer
        link = f"{FRONTEND_URL}/redefinir.html#token={token}"
        enviar_email_redefinicao(usuario.email, usuario.nome, link, RESET_MINUTOS)

    # mesma resposta exista o e-mail ou nao: ninguem descobre quem tem conta
    return jsonify({"mensagem": MSG_ESQUECI})


@auth_bp.route("/redefinir-senha", methods=["POST"])
@limiter.limit("10 per hour")
def redefinir_senha():
    dados = _corpo_json()
    if dados is None:
        return _erro("corpo da requisição inválido", 400)

    token = dados.get("token")
    nova_senha = dados.get("nova_senha")
    if not isinstance(token, str) or not 20 <= len(token) <= 200:
        return _erro(MSG_LINK_INVALIDO, 400)
    if not isinstance(nova_senha, str) or not SENHA_MIN <= len(nova_senha) <= SENHA_MAX:
        return _erro(f"a senha deve ter entre {SENHA_MIN} e {SENHA_MAX} caracteres", 400)

    agora = datetime.utcnow()
    pedido = RedefinicaoSenha.query.filter_by(token_hash=_hash_token(token)).first()

    # token inexistente, ja usado ou vencido: sempre a mesma mensagem
    if pedido is None or pedido.usado_em is not None or pedido.expira_em < agora:
        return _erro(MSG_LINK_INVALIDO, 400)

    usuario = db.session.get(Usuario, pedido.usuario_id)
    usuario.senha_hash = generate_password_hash(nova_senha)

    # uso unico: invalida este e qualquer outro pedido pendente da conta
    RedefinicaoSenha.query.filter_by(usuario_id=usuario.id, usado_em=None).update({"usado_em": agora})
    db.session.commit()

    # avisa por e-mail: se nao foi o dono quem trocou, ele fica sabendo
    enviar_email_senha_alterada(usuario.email, usuario.nome)
    return jsonify({"mensagem": "senha alterada com sucesso"})


# ---------- perfil e troca de senha (tela "Minha conta") ----------

@auth_bp.route("/perfil", methods=["GET"])
@jwt_required()
def obter_perfil():
    usuario = db.session.get(Usuario, usuario_id_atual())
    if not usuario:
        return _erro("usuário não encontrado", 404)
    return jsonify(usuario.para_dict())


@auth_bp.route("/senha", methods=["PUT"])
@jwt_required()
@limiter.limit("5 per hour", key_func=lambda: f"senha:{get_jwt_identity()}")
def alterar_senha():
    """troca a senha de quem ja esta logado: exige a senha atual, para um token roubado nao bastar"""
    dados = _corpo_json()
    if dados is None:
        return _erro("corpo da requisição inválido", 400)
    usuario = db.session.get(Usuario, usuario_id_atual())
    if not usuario:
        return _erro("usuário não encontrado", 404)

    atual, nova = dados.get("senha_atual"), dados.get("nova_senha")
    # 403 (e nao 401): o front trata 401 como "sessao expirada" e deslogaria quem so errou a senha
    if not isinstance(atual, str) or len(atual) > SENHA_MAX or not check_password_hash(usuario.senha_hash, atual):
        return _erro("senha atual incorreta", 403)
    if not isinstance(nova, str) or not SENHA_MIN <= len(nova) <= SENHA_MAX:
        return _erro(f"a nova senha deve ter entre {SENHA_MIN} e {SENHA_MAX} caracteres", 400)
    if nova == atual:
        return _erro("a nova senha precisa ser diferente da atual", 400)

    usuario.senha_hash = generate_password_hash(nova)
    # links de redefinicao pedidos antes desta troca deixam de valer
    RedefinicaoSenha.query.filter_by(usuario_id=usuario.id, usado_em=None).update({"usado_em": datetime.utcnow()})
    db.session.commit()
    enviar_email_senha_alterada(usuario.email, usuario.nome)
    return jsonify({"mensagem": "senha alterada com sucesso"})


# ---------- direitos do titular (LGPD, art. 18) ----------

def _contas_para_exportar(usuario_id):
    aceitas = defaultdict(list)
    for linha in ContaCategoria.query.filter_by(usuario_id=usuario_id).all():
        aceitas[linha.conta_id].append(linha.categoria)
    return [{**conta.para_dict(), "categorias_aceitas": sorted(aceitas.get(conta.id, []))}
            for conta in No.query.filter_by(usuario_id=usuario_id, tipo="conta").order_by(No.nome).all()]

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
        "contas": _contas_para_exportar(usuario.id),
        "compras_parceladas": [{
            "descricao": p.descricao, "valor_vista": p.valor_vista, "valor_parcela": p.valor_parcela,
            "valor_total": p.valor_total, "numero_parcelas": p.numero_parcelas, "juros_mensal": p.juros_mensal,
            "conta": p.conta, "categoria": p.categoria,
            "data_inicio": p.data_inicio.isoformat() if p.data_inicio else None,
        } for p in usuario.parcelamentos],
        "parcelas_futuras": [a.para_dict() for a in usuario.arestas if a.projetada],
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
