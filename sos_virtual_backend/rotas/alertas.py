from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from database import db
from extensoes import usuario_id_atual
from modelos.modelos import Alerta
from servicos.financeiro import CATEGORIAS, gastos_por_categoria
from validacao import VALOR_MAX, corpo_json, erro, numero

alertas_bp = Blueprint("alertas", __name__, url_prefix="/api/alertas")


@alertas_bp.route("", methods=["GET"])
@jwt_required()
def listar():
    usuario_id = usuario_id_atual()

    alertas = Alerta.query.filter_by(usuario_id=usuario_id).all()

    # pega os gastos do mes para verificar se algum alerta foi disparado
    gastos = gastos_por_categoria(usuario_id)

    resultado = []
    for a in alertas:
        info = a.para_dict()

        # gasto_atual mostra quanto ja foi gasto na categoria desse alerta
        info["gasto_atual"] = gastos.get(a.categoria, 0.0)

        # disparado so vale para alertas ligados: alerta desativado nao dispara
        info["disparado"] = a.ativo and info["gasto_atual"] >= a.limite

        resultado.append(info)

    return jsonify(resultado)


@alertas_bp.route("", methods=["POST"])
@jwt_required()
def criar():
    usuario_id = usuario_id_atual()
    dados = corpo_json()
    if dados is None:
        return erro("corpo da requisição inválido")

    categoria = dados.get("categoria")
    if not isinstance(categoria, str) or categoria not in CATEGORIAS:
        return erro("categoria inválida")

    # limite precisa ser positivo (o front divide o gasto pelo limite)
    limite = numero(dados.get("limite"), 0.01, VALOR_MAX)
    if limite is None:
        return erro("limite inválido (precisa ser maior que zero)")

    # um alerta por categoria: evita duplicados que confundem o painel
    if Alerta.query.filter_by(usuario_id=usuario_id, categoria=categoria).first():
        return erro("já existe um alerta para essa categoria", 409)

    novo = Alerta(
        usuario_id=usuario_id,
        categoria=categoria,
        limite=limite
    )

    db.session.add(novo)
    db.session.commit()
    return jsonify(novo.para_dict()), 201


@alertas_bp.route("/<int:alerta_id>", methods=["PUT"])
@jwt_required()
def editar(alerta_id):
    usuario_id = usuario_id_atual()

    alerta = Alerta.query.filter_by(id=alerta_id, usuario_id=usuario_id).first_or_404()
    dados = corpo_json()
    if dados is None:
        return erro("corpo da requisição inválido")

    # permite atualizar o limite ou ativar/desativar o alerta
    if "limite" in dados:
        limite = numero(dados["limite"], 0.01, VALOR_MAX)
        if limite is None:
            return erro("limite inválido (precisa ser maior que zero)")
        alerta.limite = limite

    if "ativo" in dados:
        # so aceita true/false de verdade, nada de "sim", 1 ou texto
        if not isinstance(dados["ativo"], bool):
            return erro("o campo 'ativo' deve ser verdadeiro ou falso")
        alerta.ativo = dados["ativo"]

    db.session.commit()
    return jsonify(alerta.para_dict())


@alertas_bp.route("/<int:alerta_id>", methods=["DELETE"])
@jwt_required()
def deletar(alerta_id):
    usuario_id = usuario_id_atual()

    alerta = Alerta.query.filter_by(id=alerta_id, usuario_id=usuario_id).first_or_404()
    db.session.delete(alerta)
    db.session.commit()
    return jsonify({"mensagem": "alerta removido"})
