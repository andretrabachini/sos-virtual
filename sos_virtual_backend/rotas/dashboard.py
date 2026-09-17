from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from modelos.modelos import Meta, Transacao
from servicos.financeiro import resumo_mensal, gastos_por_categoria
from datetime import datetime

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")


@dashboard_bp.route("", methods=["GET"])
@jwt_required()
def dados_dashboard():
    usuario_id = get_jwt_identity()

    # pega o resumo financeiro do mes atual
    resumo = resumo_mensal(usuario_id)

    # gasto separado por categoria para montar o grafico no front
    por_categoria = gastos_por_categoria(usuario_id)

    # ultimas 5 transacoes para mostrar no painel principal
    recentes = (
        Transacao.query
        .filter_by(usuario_id=usuario_id)
        .order_by(Transacao.data.desc())
        .limit(5)
        .all()
    )

    # metas ativas do usuario com o progresso atual
    metas = Meta.query.filter_by(usuario_id=usuario_id).all()

    return jsonify({
        "mes": datetime.utcnow().strftime("%Y-%m"),
        "receita_total": resumo["receita"],
        "despesa_total": resumo["despesa"],
        "saldo": resumo["saldo"],
        "por_categoria": por_categoria,
        "transacoes_recentes": [t.para_dict() for t in recentes],
        "metas": [m.para_dict() for m in metas]
    })
