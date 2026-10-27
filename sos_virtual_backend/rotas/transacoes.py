import re
from datetime import datetime

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

from database import db
from extensoes import limiter, usuario_id_atual
from modelos.modelos import Aresta, No, Transacao
from servicos.alertas_service import alertas_ultrapassados, fotografar_alertas
from servicos.categorizacao import detectar_categoria_com_motivo
from servicos.financeiro import CATEGORIAS
from validacao import VALOR_MAX, corpo_json, erro, numero, texto

transacoes_bp = Blueprint("transacoes", __name__, url_prefix="/api/transacoes")

# o front tambem oferece "Salário" para receitas, entao ela e aceita aqui
CATEGORIAS_VALIDAS = set(CATEGORIAS) | {"Salário"}

# formato do filtro de mes: "2026-04"
MES_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")

MSG_SALARIO = "a categoria Salário só vale para receitas"


def _categoria_valida(valor):
    return isinstance(valor, str) and valor in CATEGORIAS_VALIDAS


def _mover_projecoes(usuario_id, descricao, categoria):
    """
    ao trocar a categoria de uma compra parcelada, as parcelas futuras projetadas a partir
    dela (mesma descricao) passam a apontar para a nova categoria no grafo
    """
    projecoes = Aresta.query.filter_by(usuario_id=usuario_id, descricao=descricao, projetada=True).all()
    if not projecoes:
        return
    no = No.query.filter_by(usuario_id=usuario_id, nome=categoria, tipo="categoria").first()
    if no is None:
        no = No(usuario_id=usuario_id, nome=categoria, tipo="categoria")
        db.session.add(no)
        db.session.flush()
    for aresta in projecoes:
        aresta.destino_id = no.id


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


@transacoes_bp.route("/sugerir-categoria", methods=["POST"])
@jwt_required()
@limiter.limit("120 per minute")
def sugerir_categoria():
    """
    previa da deteccao automatica, para a tela mostrar a categoria ANTES de salvar:
      {"descricao": "mercado", "valor": -50}  ->  {"categoria": "Alimentação", "motivo": "mercado"}
    o sinal do valor importa: so receitas (valor positivo) podem ser "Salário"
    """
    dados = corpo_json()
    if dados is None:
        return erro("corpo da requisição inválido")

    descricao = texto(dados.get("descricao"), 1, 255)
    if descricao is None:
        return erro("informe a descrição (até 255 caracteres)")

    valor = None
    if dados.get("valor") is not None:
        valor = numero(dados["valor"], -VALOR_MAX, VALOR_MAX)
        if valor is None:
            return erro("valor inválido")

    categoria, motivo = detectar_categoria_com_motivo(descricao, valor)
    return jsonify({"categoria": categoria, "motivo": motivo})


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

    # se a categoria nao vier no body, detecta pela descricao (e pelo sinal do valor)
    categoria = dados.get("categoria")
    if categoria in (None, ""):
        categoria, _ = detectar_categoria_com_motivo(descricao, valor)
    elif not _categoria_valida(categoria):
        return erro("categoria inválida")

    if categoria == "Salário" and valor < 0:
        return erro(MSG_SALARIO)

    antes = fotografar_alertas(usuario_id) if valor < 0 else None   # so despesas mexem nos alertas

    nova = Transacao(
        usuario_id=usuario_id,
        descricao=descricao,
        valor=valor,
        categoria=categoria
    )

    db.session.add(nova)
    db.session.commit()
    resposta = nova.para_dict()
    resposta["alertas"] = alertas_ultrapassados(usuario_id, antes)   # o front mostra um pop-up com eles
    return jsonify(resposta), 201


@transacoes_bp.route("/<int:transacao_id>", methods=["PUT"])
@jwt_required()
def editar(transacao_id):
    usuario_id = usuario_id_atual()

    # garante que o usuario so edita transacoes que sao dele
    t = Transacao.query.filter_by(id=transacao_id, usuario_id=usuario_id).first_or_404()

    dados = corpo_json()
    if dados is None:
        return erro("corpo da requisição inválido")

    # valida tudo primeiro; so depois altera (se algo for invalido, nada e salvo)
    nova_descricao, novo_valor, nova_categoria = t.descricao, t.valor, t.categoria

    if "descricao" in dados:
        nova_descricao = texto(dados["descricao"], 1, 255)
        if nova_descricao is None:
            return erro("descrição inválida (até 255 caracteres)")

    if "valor" in dados:
        novo_valor = numero(dados["valor"], -VALOR_MAX, VALOR_MAX)
        if novo_valor is None or novo_valor == 0:
            return erro("valor inválido (diferente de zero)")

    if "categoria" in dados:
        if not _categoria_valida(dados["categoria"]):
            return erro("categoria inválida")
        nova_categoria = dados["categoria"]

    # vale para a combinacao final: trocar o sinal de uma receita "Salário" tambem e barrado
    if nova_categoria == "Salário" and novo_valor < 0:
        return erro(MSG_SALARIO + " (troque também a categoria)")

    antes = fotografar_alertas(usuario_id)
    categoria_mudou = nova_categoria != t.categoria
    t.descricao, t.valor, t.categoria = nova_descricao, novo_valor, nova_categoria

    if categoria_mudou:
        _mover_projecoes(usuario_id, t.descricao, nova_categoria)

    db.session.commit()
    resposta = t.para_dict()
    resposta["alertas"] = alertas_ultrapassados(usuario_id, antes)
    return jsonify(resposta)


@transacoes_bp.route("/<int:transacao_id>", methods=["DELETE"])
@jwt_required()
def deletar(transacao_id):
    usuario_id = usuario_id_atual()

    # mesma verificacao: so deleta se for do proprio usuario
    t = Transacao.query.filter_by(id=transacao_id, usuario_id=usuario_id).first_or_404()

    db.session.delete(t)
    db.session.commit()
    return jsonify({"mensagem": "transação removida com sucesso"})
