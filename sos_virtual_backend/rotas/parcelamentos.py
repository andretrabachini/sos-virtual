from datetime import datetime

from dateutil.relativedelta import relativedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from database import db
from extensoes import limiter, usuario_id_atual
from modelos.modelos import No
from servicos.alertas_service import alertas_ultrapassados, fotografar_alertas
from servicos.categorizacao import detectar_categoria_com_motivo
from servicos.financeiro import CATEGORIAS
from servicos.parcelamento import (
    JUROS_MAX, MAX_PARCELAS, MIN_PARCELAS, criar_parcelamento, excluir_parcelamento, listar_parcelamentos,
    resumo_parcelamento,
)
from validacao import VALOR_MAX, corpo_json, data_iso, erro, numero, texto

parcelamentos_bp = Blueprint("parcelamentos", __name__, url_prefix="/api/parcelamentos")

MAX_CONTAS = 20


def _inteiro(valor):
    """aceita 10 ou 10.0, recusa texto, True/False e fracoes"""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return int(valor) if float(valor).is_integer() else None


def _ler_calculo(dados):
    """valida os 3 campos que definem as parcelas; devolve ((valor_vista, parcelas, juros), None) ou (None, erro)"""
    vista = numero(dados.get("valor_vista"), 0.01, VALOR_MAX)
    if vista is None:
        return None, "informe o valor da compra à vista (maior que zero)"
    parcelas = _inteiro(dados.get("parcelas"))
    if parcelas is None or not MIN_PARCELAS <= parcelas <= MAX_PARCELAS:
        return None, f"o número de parcelas deve ser um inteiro entre {MIN_PARCELAS} e {MAX_PARCELAS}"
    juros = 0.0
    if dados.get("juros_mensal") not in (None, ""):
        juros = numero(dados["juros_mensal"], 0, JUROS_MAX)
        if juros is None:
            return None, f"juros inválidos (informe a taxa ao mês, de 0 a {JUROS_MAX:g}%)"
    return (vista, parcelas, juros), None


@parcelamentos_bp.route("/simular", methods=["POST"])
@jwt_required()
@limiter.limit("120 per minute")
def simular():
    """previa para a tela: quanto fica cada parcela, o total pago e quanto sao os juros"""
    dados = corpo_json()
    if dados is None:
        return erro("corpo da requisição inválido")
    calculo, mensagem = _ler_calculo(dados)
    if calculo is None:
        return erro(mensagem)
    return jsonify(resumo_parcelamento(*calculo))


@parcelamentos_bp.route("", methods=["POST"])
@jwt_required()
def criar():
    usuario_id = usuario_id_atual()
    dados = corpo_json()
    if dados is None:
        return erro("corpo da requisição inválido")

    descricao = texto(dados.get("descricao"), 1, 200)    # 200: sobra espaco para o sufixo " (3/12)"
    if descricao is None:
        return erro("informe a descrição da compra (até 200 caracteres)")

    calculo, mensagem = _ler_calculo(dados)
    if calculo is None:
        return erro(mensagem)
    vista, parcelas, juros = calculo

    conta = texto(dados.get("conta") or "Conta Principal", 1, 100)
    if conta is None:
        return erro("nome do cartão ou conta inválido (até 100 caracteres)")
    if not No.query.filter_by(usuario_id=usuario_id, nome=conta, tipo="conta").first() \
            and No.query.filter_by(usuario_id=usuario_id, tipo="conta").count() >= MAX_CONTAS:
        return erro(f"limite de {MAX_CONTAS} contas atingido")

    categoria = dados.get("categoria")
    if categoria in (None, ""):
        categoria, _ = detectar_categoria_com_motivo(descricao, -vista)
    elif not isinstance(categoria, str) or categoria not in CATEGORIAS:
        return erro("categoria inválida")

    # data da primeira parcela: padrao hoje; aceita de 24 meses atras ate 12 meses a frente
    hoje = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    inicio = hoje
    if dados.get("data_inicio") not in (None, ""):
        inicio = data_iso(dados["data_inicio"])
        if inicio is None:
            return erro("data inválida (use o formato AAAA-MM-DD)")
        inicio = inicio.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
        if not hoje - relativedelta(months=24) <= inicio <= hoje + relativedelta(months=12):
            return erro("a data da primeira parcela deve estar entre 24 meses atrás e 12 meses à frente")

    antes = fotografar_alertas(usuario_id)
    try:
        resumo = criar_parcelamento(usuario_id, descricao, vista, parcelas, juros, conta, categoria, inicio)
        db.session.commit()        # um unico commit: ou grava tudo ou nao grava nada
    except Exception:
        db.session.rollback()
        raise
    resumo.update({"descricao": descricao, "conta": conta, "categoria": categoria,
                   "alertas": alertas_ultrapassados(usuario_id, antes)})
    return jsonify(resumo), 201


@parcelamentos_bp.route("", methods=["GET"])
@jwt_required()
def listar():
    """compras parceladas em andamento: de onde vem cada parcela futura que aparece no painel"""
    return jsonify(listar_parcelamentos(usuario_id_atual()))


@parcelamentos_bp.route("/<ident>", methods=["DELETE"])
@jwt_required()
def excluir(ident):
    """?lancadas=1 apaga tambem as parcelas deste e de meses passados que ja viraram transacoes (so compras manuais)"""
    usuario_id = usuario_id_atual()
    if not 2 <= len(ident) <= 40 or not ident.isalnum():
        return erro("compra parcelada não encontrada", 404)
    incluir = request.args.get("lancadas", "").lower() in {"1", "true", "sim"}
    achou, futuras, lancadas = excluir_parcelamento(usuario_id, ident, incluir)
    if not achou:
        return erro("compra parcelada não encontrada", 404)
    db.session.commit()
    return jsonify({"mensagem": "compra parcelada removida", "parcelas_futuras_removidas": futuras,
                    "parcelas_lancadas_removidas": lancadas})
