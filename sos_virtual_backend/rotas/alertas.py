from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from database import db
from modelos.modelos import Alerta
from servicos.financeiro import gastos_por_categoria

alertas_bp = Blueprint("alertas", __name__, url_prefix="/api/alertas")


@alertas_bp.route("", methods=["GET"])
@jwt_required()
def listar():
    usuario_id = get_jwt_identity()

    alertas = Alerta.query.filter_by(usuario_id=usuario_id).all()

    # pega os gastos do mes para verificar se algum alerta foi disparado
    gastos = gastos_por_categoria(usuario_id)

    resultado = []
    for a in alertas:
        info = a.para_dict()

        # gasto_atual mostra quanto ja foi gasto na categoria desse alerta
        info["gasto_atual"] = gastos.get(a.categoria, 0.0)

        # disparado indica se o limite ja foi ultrapassado
        info["disparado"] = info["gasto_atual"] >= a.limite

        resultado.append(info)

    return jsonify(resultado)


@alertas_bp.route("", methods=["POST"])
@jwt_required()
def criar():
    usuario_id = get_jwt_identity()
    dados = request.get_json()

    novo = Alerta(
        usuario_id=usuario_id,
        categoria=dados["categoria"],
        limite=dados["limite"]
    )

    db.session.add(novo)
    db.session.commit()
    return jsonify(novo.para_dict()), 201


@alertas_bp.route("/<int:alerta_id>", methods=["PUT"])
@jwt_required()
def editar(alerta_id):
    usuario_id = get_jwt_identity()

    alerta = Alerta.query.filter_by(id=alerta_id, usuario_id=usuario_id).first_or_404()
    dados = request.get_json()

    # permite atualizar o limite ou ativar/desativar o alerta
    if "limite" in dados:
        alerta.limite = dados["limite"]
    if "ativo" in dados:
        alerta.ativo = dados["ativo"]

    db.session.commit()
    return jsonify(alerta.para_dict())


@alertas_bp.route("/<int:alerta_id>", methods=["DELETE"])
@jwt_required()
def deletar(alerta_id):
    usuario_id = get_jwt_identity()

    alerta = Alerta.query.filter_by(id=alerta_id, usuario_id=usuario_id).first_or_404()
    db.session.delete(alerta)
    db.session.commit()
    return jsonify({"mensagem": "alerta removido"})