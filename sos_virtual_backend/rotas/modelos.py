from flask import Blueprint, Response
from flask_jwt_extended import jwt_required

from extensoes import limiter, usuario_id_atual
from modelos.modelos import No
from servicos.modelos_planilha import NOME_ARQUIVO, gerar_modelo_csv, gerar_modelo_xlsx

modelos_bp = Blueprint("modelos", __name__, url_prefix="/api/modelos")


def _arquivo(conteudo, tipo, extensao):
    return Response(conteudo, mimetype=tipo, headers={"Content-Disposition": f'attachment; filename="{NOME_ARQUIVO}.{extensao}"'})


@modelos_bp.route("/planilha.xlsx", methods=["GET"])
@jwt_required()
@limiter.limit("60 per hour")
def modelo_xlsx():
    """modelo de planilha do Excel, com a lista suspensa das contas e cartoes do proprio usuario"""
    contas = [c.nome for c in No.query.filter_by(usuario_id=usuario_id_atual(), tipo="conta").order_by(No.nome).all()]
    return _arquivo(gerar_modelo_xlsx(contas), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx")


@modelos_bp.route("/planilha.csv", methods=["GET"])
@jwt_required()
@limiter.limit("60 per hour")
def modelo_csv():
    return _arquivo(gerar_modelo_csv(), "text/csv; charset=utf-8", "csv")
