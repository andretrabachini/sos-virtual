from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from database import db
from extensoes import usuario_id_atual
from modelos.modelos import Meta
from validacao import VALOR_MAX, corpo_json, data_iso, erro, numero, texto

metas_bp = Blueprint("metas", __name__, url_prefix="/api/metas")


@metas_bp.route("", methods=["GET"])
@jwt_required()
def listar():
    usuario_id = usuario_id_atual()
    metas = Meta.query.filter_by(usuario_id=usuario_id).all()
    return jsonify([m.para_dict() for m in metas])


@metas_bp.route("", methods=["POST"])
@jwt_required()
def criar():
    usuario_id = usuario_id_atual()
    dados = corpo_json()
    if dados is None:
        return erro("corpo da requisição inválido")

    titulo = texto(dados.get("titulo"), 1, 120)
    if titulo is None:
        return erro("informe o nome da meta (até 120 caracteres)")

    valor_alvo = numero(dados.get("valor_alvo"), 0.01, VALOR_MAX)
    if valor_alvo is None:
        return erro("valor alvo inválido (precisa ser maior que zero)")

    # valor inicial e opcional, mas nunca negativo nem maior que o alvo
    valor_atual = 0.0
    if dados.get("valor_atual") not in (None, ""):
        valor_atual = numero(dados.get("valor_atual"), 0, valor_alvo)
        if valor_atual is None:
            return erro("valor inicial inválido (entre zero e o valor alvo)")

    # prazo e opcional, o usuario pode criar a meta sem data limite
    prazo = None
    if dados.get("prazo"):
        prazo = data_iso(dados["prazo"])
        if prazo is None:
            return erro("prazo inválido (use o formato AAAA-MM-DD)")

    nova_meta = Meta(
        usuario_id=usuario_id,
        titulo=titulo,
        valor_alvo=valor_alvo,
        valor_atual=valor_atual,
        prazo=prazo,
    )

    db.session.add(nova_meta)
    db.session.commit()
    return jsonify(nova_meta.para_dict()), 201


@metas_bp.route("/<int:meta_id>/depositar", methods=["POST"])
@jwt_required()
def depositar(meta_id):
    usuario_id = usuario_id_atual()
    # filtra pelo usuario do token: ninguem deposita na meta de outra pessoa
    meta = Meta.query.filter_by(id=meta_id, usuario_id=usuario_id).first_or_404()

    dados = corpo_json()
    if dados is None:
        return erro("corpo da requisição inválido")

    # deposito sempre positivo: valor negativo serviria para "sacar" da meta escondido
    valor = numero(dados.get("valor"), 0.01, VALOR_MAX)
    if valor is None:
        return erro("valor do depósito inválido (precisa ser maior que zero)")

    # nao deixa o valor atual ultrapassar o alvo
    meta.valor_atual = round(min(meta.valor_atual + valor, meta.valor_alvo), 2)

    db.session.commit()
    return jsonify(meta.para_dict())


@metas_bp.route("/<int:meta_id>", methods=["DELETE"])
@jwt_required()
def deletar(meta_id):
    usuario_id = usuario_id_atual()
    meta = Meta.query.filter_by(id=meta_id, usuario_id=usuario_id).first_or_404()

    db.session.delete(meta)
    db.session.commit()
    return jsonify({"mensagem": "meta removida"})
