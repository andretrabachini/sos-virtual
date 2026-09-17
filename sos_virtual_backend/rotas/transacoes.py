from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from database import db
from modelos.modelos import Transacao
from servicos.financeiro import detectar_categoria
from datetime import datetime

transacoes_bp = Blueprint("transacoes", __name__, url_prefix="/api/transacoes")


@transacoes_bp.route("", methods=["GET"])
@jwt_required()
def listar():
    usuario_id = get_jwt_identity()

    # filtro opcional por mes — formato esperado: "2026-04"
    mes = request.args.get("mes")

    consulta = Transacao.query.filter_by(usuario_id=usuario_id)

    if mes:
        ano, m = map(int, mes.split("-"))
        inicio = datetime(ano, m, 1)
        # calcula o primeiro dia do mes seguinte para usar como limite
        fim = datetime(ano, m + 1, 1) if m < 12 else datetime(ano + 1, 1, 1)
        consulta = consulta.filter(Transacao.data >= inicio, Transacao.data < fim)

    transacoes = consulta.order_by(Transacao.data.desc()).all()
    return jsonify([t.para_dict() for t in transacoes])


@transacoes_bp.route("", methods=["POST"])
@jwt_required()
def criar():
    usuario_id = get_jwt_identity()
    dados = request.get_json()

    # se a categoria nao vier no body, tenta detectar automaticamente pela descricao
    categoria = dados.get("categoria") or detectar_categoria(dados["descricao"])

    nova = Transacao(
        usuario_id=usuario_id,
        descricao=dados["descricao"],
        valor=dados["valor"],
        categoria=categoria
    )

    db.session.add(nova)
    db.session.commit()
    return jsonify(nova.para_dict()), 201


@transacoes_bp.route("/<int:transacao_id>", methods=["PUT"])
@jwt_required()
def editar(transacao_id):
    usuario_id = get_jwt_identity()

    # garante que o usuario so edita transacoes que sao dele
    t = Transacao.query.filter_by(id=transacao_id, usuario_id=usuario_id).first_or_404()

    dados = request.get_json()

    if "descricao" in dados:
        t.descricao = dados["descricao"]
    if "valor" in dados:
        t.valor = dados["valor"]
    if "categoria" in dados:
        t.categoria = dados["categoria"]

    db.session.commit()
    return jsonify(t.para_dict())


@transacoes_bp.route("/<int:transacao_id>", methods=["DELETE"])
@jwt_required()
def deletar(transacao_id):
    usuario_id = get_jwt_identity()

    # mesma verificacao: so deleta se for do proprio usuario
    t = Transacao.query.filter_by(id=transacao_id, usuario_id=usuario_id).first_or_404()

    db.session.delete(t)
    db.session.commit()
    return jsonify({"mensagem": "transação removida com sucesso"})