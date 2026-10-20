import re
from datetime import datetime

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

from database import db
from extensoes import usuario_id_atual
from modelos.modelos import Transacao
from servicos.financeiro import CATEGORIAS, detectar_categoria
from validacao import VALOR_MAX, corpo_json, erro, numero, texto

transacoes_bp = Blueprint("transacoes", __name__, url_prefix="/api/transacoes")

# o front tambem oferece "Salário" para receitas, entao ela e aceita aqui
CATEGORIAS_VALIDAS = set(CATEGORIAS) | {"Salário"}

# formato do filtro de mes: "2026-04"
MES_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def _categoria_valida(valor):
    return isinstance(valor, str) and valor in CATEGORIAS_VALIDAS


@transacoes_bp.route("", methods=["GET"])
@jwt_required()
def listar():
    usuario_id = usuario_id_atual()

    consulta = Transacao.query.filter_by(usuario_id=usuario_id)

    # filtro opcional por mes — antes, um valor fora do formato causava erro 500
    mes = request.args.get("mes")
    if mes:
        achou = MES_RE.match(mes)
        if not achou:
            return erro("mês inválido (use o formato AAAA-MM)")
        ano, m = int(achou.group(1)), int(achou.group(2))
        inicio = datetime(ano, m, 1)
        # calcula o primeiro dia do mes seguinte para usar como limite
        fim = datetime(ano, m + 1, 1) if m < 12 else datetime(ano + 1, 1, 1)
        consulta = consulta.filter(Transacao.data >= inicio, Transacao.data < fim)

    # teto de 1000 linhas por resposta, para uma conta muito cheia nao derrubar o servidor
    transacoes = consulta.order_by(Transacao.data.desc()).limit(1000).all()
    return jsonify([t.para_dict() for t in transacoes])


@transacoes_bp.route("", methods=["POST"])
@jwt_required()
def criar():
    usuario_id = usuario_id_atual()
    dados = corpo_json()
    if dados is None:
        return erro("corpo da requisição inválido")

    descricao = texto(dados.get("descricao"), 1, 255)
    if descricao is None:
        return erro("informe a descrição (até 255 caracteres)")

    # valor positivo = receita, negativo = despesa; zero nao faz sentido
    valor = numero(dados.get("valor"), -VALOR_MAX, VALOR_MAX)
    if valor is None or valor == 0:
        return erro("valor inválido (diferente de zero)")

    # se a categoria nao vier no body, tenta detectar automaticamente pela descricao
    categoria = dados.get("categoria")
    if categoria in (None, ""):
        categoria = detectar_categoria(descricao)
    elif not _categoria_valida(categoria):
        return erro("categoria inválida")

    nova = Transacao(
        usuario_id=usuario_id,
        descricao=descricao,
        valor=valor,
        categoria=categoria
    )

    db.session.add(nova)
    db.session.commit()
    return jsonify(nova.para_dict()), 201


@transacoes_bp.route("/<int:transacao_id>", methods=["PUT"])
@jwt_required()
def editar(transacao_id):
    usuario_id = usuario_id_atual()

    # garante que o usuario so edita transacoes que sao dele
    t = Transacao.query.filter_by(id=transacao_id, usuario_id=usuario_id).first_or_404()

    dados = corpo_json()
    if dados is None:
        return erro("corpo da requisição inválido")

    # valida cada campo; se algum for invalido, retorna erro antes do commit e nada e salvo
    if "descricao" in dados:
        descricao = texto(dados["descricao"], 1, 255)
        if descricao is None:
            return erro("descrição inválida (até 255 caracteres)")
        t.descricao = descricao

    if "valor" in dados:
        valor = numero(dados["valor"], -VALOR_MAX, VALOR_MAX)
        if valor is None or valor == 0:
            return erro("valor inválido (diferente de zero)")
        t.valor = valor

    if "categoria" in dados:
        if not _categoria_valida(dados["categoria"]):
            return erro("categoria inválida")
        t.categoria = dados["categoria"]

    db.session.commit()
    return jsonify(t.para_dict())


@transacoes_bp.route("/<int:transacao_id>", methods=["DELETE"])
@jwt_required()
def deletar(transacao_id):
    usuario_id = usuario_id_atual()

    # mesma verificacao: so deleta se for do proprio usuario
    t = Transacao.query.filter_by(id=transacao_id, usuario_id=usuario_id).first_or_404()

    db.session.delete(t)
    db.session.commit()
    return jsonify({"mensagem": "transação removida com sucesso"})
