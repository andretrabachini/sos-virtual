from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from extensoes import usuario_id_atual
from servicos.saldo import resumo_com_saldo
from servicos.tempo import mes_atual
from validacao import erro, mes_valido

saldo_bp = Blueprint("saldo", __name__, url_prefix="/api/saldo")


@saldo_bp.route("", methods=["GET"])
@jwt_required()
def saldo_do_mes():
    """
    saldo de um mes: ?mes=AAAA-MM (padrao: o mes atual)
    {"mes", "saldo_anterior", "receita", "despesa", "saldo_do_mes", "saldo_final", "saldo_inicial_informado"}
    saldo_anterior e saldo_final sao null quando o mes e anterior ao saldo inicial que o usuario informou
    """
    mes = request.args.get("mes") or mes_atual()
    if not mes_valido(mes):
        return erro("mês inválido (use o formato AAAA-MM)")
    return jsonify(resumo_com_saldo(usuario_id_atual(), mes))
