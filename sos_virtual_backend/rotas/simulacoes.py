from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

from database import db
from extensoes import limiter, usuario_id_atual
from modelos.modelos import Usuario
from servicos.alertas_service import alertas_ultrapassados, fotografar_alertas
from servicos.extratos import ExtratoInvalido, ler_extrato
from servicos.importacao import importar_lancamentos, projecao_mensal
from validacao import erro, texto

simulacoes_bp = Blueprint("simulacoes", __name__, url_prefix="/api/simulacoes")

EXTENSOES_ACEITAS = {"csv", "ofx", "qfx"}


def _marcado(valor):
    # campos de formulario chegam como texto: aceita "true", "1", "on" ou "sim"
    return str(valor or "").strip().lower() in {"true", "1", "on", "sim"}


@simulacoes_bp.route("/importar-extrato", methods=["POST"])
@jwt_required()
@limiter.limit("20 per hour")
def importar_extrato():
    """
    recebe um extrato (CSV ou OFX) em multipart/form-data:
      arquivo     -> o arquivo (obrigatorio)
      conta       -> nome da conta/cartao de origem (padrao: "Conta Principal")
      cartao      -> "true" se for fatura de cartao (compras vem positivas; inverte o sinal)
      valor_total -> "true" se o valor das compras parceladas for o TOTAL da compra
                     (por padrao o valor do extrato ja e o de uma parcela)
      parcelas    -> "false" desliga a deteccao de compras parceladas
    """
    usuario_id = usuario_id_atual()

    arquivo = request.files.get("arquivo")
    if arquivo is None or not arquivo.filename:
        return erro("envie o extrato no campo 'arquivo'")

    # confere so a extensao; o nome enviado nunca e usado para salvar nada,
    # porque o arquivo e lido em memoria e descartado (nada vai para o disco)
    nome = arquivo.filename.lower()
    extensao = nome.rsplit(".", 1)[-1] if "." in nome else ""
    if extensao not in EXTENSOES_ACEITAS:
        return erro("formato não suportado (envie um arquivo CSV ou OFX)")
    if extensao == "qfx":
        extensao = "ofx"

    conta = texto(request.form.get("conta") or "Conta Principal", 1, 100)
    if conta is None:
        return erro("nome da conta inválido (até 100 caracteres)")

    try:
        # o tamanho maximo (2 MB) ja e barrado pelo MAX_CONTENT_LENGTH do app.py
        lancamentos, erros_leitura = ler_extrato(extensao, arquivo.read())
    except ExtratoInvalido as e:
        return erro(str(e))

    # fatura de cartao: o banco lista as compras como valores positivos
    if _marcado(request.form.get("cartao")):
        for l in lancamentos:
            l["valor"] = -l["valor"]

    antes = fotografar_alertas(usuario_id)
    try:
        resumo = importar_lancamentos(
            usuario_id,
            lancamentos,
            conta,
            valor_e_total=_marcado(request.form.get("valor_total")),
            detectar=request.form.get("parcelas", "true").strip().lower() != "false",
        )
        db.session.commit()  # um unico commit: ou grava tudo ou nao grava nada
    except Exception:
        db.session.rollback()
        raise  # o handler de erro 500 do app.py responde sem vazar detalhes

    resumo["alertas"] = alertas_ultrapassados(usuario_id, antes)
    resumo["linhas_com_erro"] = len(erros_leitura)
    resumo["erros"] = erros_leitura[:10]  # mostra so as 10 primeiras para a resposta nao crescer
    return jsonify(resumo), 201


@simulacoes_bp.route("/projecao", methods=["GET"])
@jwt_required()
def projecao():
    """quanto das parcelas futuras ja esta comprometido em cada um dos proximos meses"""
    usuario_id = usuario_id_atual()

    try:
        meses = int(request.args.get("meses", 6))
    except ValueError:
        return erro("'meses' deve ser um número inteiro")
    if not 1 <= meses <= 24:
        return erro("'meses' deve estar entre 1 e 24")

    usuario = db.session.get(Usuario, usuario_id)
    renda = usuario.renda_mensal or 0.0 if usuario else 0.0

    return jsonify({
        "renda_mensal": renda,
        "meses": projecao_mensal(usuario_id, renda, meses),
    })
