from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from database import db
from modelos.modelos import Meta
from datetime import datetime

metas_bp = Blueprint("metas", __name__, url_prefix="/api/metas")


@metas_bp.route("", methods=["GET"])
@jwt_required()
def listar():
    usuario_id = get_jwt_identity()
    metas = Meta.query.filter_by(usuario_id=usuario_id).all()
    return jsonify([m.para_dict() for m in metas])


@metas_bp.route("", methods=["POST"])
@jwt_required()
def criar():
    usuario_id = get_jwt_identity()
    dados = request.get_json()

    nova_meta = Meta(
        usuario_id=usuario_id,
        titulo=dados["titulo"],
        valor_alvo=dados["valor_alvo"],
        valor_atual=dados.get("valor_atual", 0.0),
        # prazo e opcional, o usuario pode criar a meta sem data limite
        prazo=datetime.fromisoformat(dados["prazo"]) if dados.get("prazo") else None
    )

    db.session.add(nova_meta)
    db.session.commit()
    return jsonify(nova_meta.para_dict()), 201


@metas_bp.route("/<int:meta_id>/depositar", methods=["POST"])
@jwt_required()
def depositar(meta_id):
    usuario_id = get_jwt_identity()
    meta = Meta.query.filter_by(id=meta_id, usuario_id=usuario_id).first_or_404()

    dados = request.get_json()
    meta.valor_atual += dados["valor"]

    # nao deixa o valor atual ultrapassar o alvo
    if meta.valor_atual > meta.valor_alvo:
        meta.valor_atual = meta.valor_alvo

    db.session.commit()
    return jsonify(meta.para_dict())


@metas_bp.route("/<int:meta_id>", methods=["DELETE"])
@jwt_required()
def deletar(meta_id):
    usuario_id = get_jwt_identity()
    meta = Meta.query.filter_by(id=meta_id, usuario_id=usuario_id).first_or_404()

    db.session.delete(meta)
    db.session.commit()
    return jsonify({"mensagem": "meta removida"})