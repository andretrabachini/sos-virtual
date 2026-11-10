from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from extensoes import usuario_id_atual
from modelos.modelos import Meta, Transacao
from servicos.contas import nomes_das_contas, transacao_com_conta
from servicos.financeiro import gastos_por_categoria, limites_do_mes, resumo_mensal
from servicos.tempo import mes_atual
from validacao import erro, mes_valido

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")


@dashboard_bp.route("", methods=["GET"])
@jwt_required()
def dados_dashboard():
    """resumo de um mes: ?mes=AAAA-MM (padrao: o mes atual)"""
    usuario_id = usuario_id_atual()

    mes = request.args.get("mes") or mes_atual()
    if not mes_valido(mes):
        return erro("mês inválido (use o formato AAAA-MM)")

    # pega o resumo financeiro do mes escolhido
    resumo = resumo_mensal(usuario_id, mes)

    # gasto separado por categoria para montar o grafico no front
    por_categoria = gastos_por_categoria(usuario_id, mes)

    # ultimas 5 transacoes do mes, para mostrar no painel principal
    inicio, fim = limites_do_mes(mes)
    recentes = (
        Transacao.query
        .filter(Transacao.usuario_id == usuario_id, Transacao.data >= inicio, Transacao.data < fim)
        .order_by(Transacao.data.desc())
        .limit(5)
        .all()
    )
    nomes = nomes_das_contas(usuario_id)

    # metas ativas do usuario com o progresso atual (metas nao dependem do mes)
    metas = Meta.query.filter_by(usuario_id=usuario_id).all()

    return jsonify({
        "mes": mes,
        "receita_total": resumo["receita"],
        "despesa_total": resumo["despesa"],
        "saldo": resumo["saldo"],
        "por_categoria": por_categoria,
        "transacoes_recentes": [transacao_com_conta(t, nomes) for t in recentes],
        "metas": [m.para_dict() for m in metas]
    })
