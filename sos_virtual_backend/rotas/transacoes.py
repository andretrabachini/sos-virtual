import re
from datetime import datetime

from dateutil.relativedelta import relativedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

from database import db
from extensoes import limiter, usuario_id_atual
from modelos.modelos import Aresta, No, Transacao
from servicos.alertas_service import alertas_ultrapassados, fotografar_alertas
from servicos.categorizacao import detectar_categoria_com_motivo
from servicos.contas import ContaInvalida, checar_categoria, conta_por_nome, nomes_das_contas, transacao_com_conta
from servicos.financeiro import CATEGORIAS
from servicos.tempo import agora, hoje
from validacao import VALOR_MAX, corpo_json, data_iso, erro, numero, texto

transacoes_bp = Blueprint("transacoes", __name__, url_prefix="/api/transacoes")

# o front tambem oferece "Salário" para receitas, entao ela e aceita aqui
CATEGORIAS_VALIDAS = set(CATEGORIAS) | {"Salário"}

# formato do filtro de mes: "2026-04"
MES_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")

MSG_SALARIO = "a categoria Salário só vale para receitas"


def _categoria_valida(valor):
    return isinstance(valor, str) and valor in CATEGORIAS_VALIDAS


def _ler_data(valor):
    """data da compra: devolve (datetime, None) ou (None, mensagem). de 5 anos atras ate 12 meses a frente"""
    data = data_iso(valor)
    if data is None:
        return None, "data inválida (use o formato AAAA-MM-DD)"
    data = data.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    hoje_ = hoje()
    if not hoje_ - relativedelta(years=5) <= data <= hoje_ + relativedelta(months=12):
        return None, "a data deve estar entre 5 anos atrás e 12 meses à frente"
    return (agora() if data == hoje_ else data), None     # compra de hoje guarda a hora (ordem dentro do dia)


def _ler_nome_conta(valor):
    """nome da conta informado: (nome ou None, mensagem de erro ou None). vazio = sem conta"""
    if valor in (None, ""):
        return None, None
    nome = texto(valor, 1, 100)
    return (nome, None) if nome else (None, "nome da conta inválido (até 100 caracteres)")


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
    nomes = nomes_das_contas(usuario_id)
    return jsonify([transacao_com_conta(t, nomes) for t in transacoes])


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
    """
    campos: descricao, valor (negativo = despesa), categoria (opcional), data "AAAA-MM-DD" (opcional, padrao hoje)
    e conta (opcional): nome do cartao/conta em que a despesa foi paga; vale so paga as categorias dele
    """
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

    data = None
    if dados.get("data") not in (None, ""):
        data, mensagem = _ler_data(dados["data"])
        if data is None:
            return erro(mensagem)

    nome_conta, mensagem = _ler_nome_conta(dados.get("conta"))
    if mensagem:
        return erro(mensagem)

    antes = fotografar_alertas(usuario_id) if valor < 0 else None   # so despesas mexem nos alertas

    conta_id = None
    if nome_conta and valor < 0:                                    # conta so faz sentido para despesas
        try:
            conta = conta_por_nome(usuario_id, nome_conta, criar=True)
            checar_categoria(usuario_id, conta, categoria)
        except ContaInvalida as e:
            db.session.rollback()
            return erro(str(e))
        conta_id = conta.id

    nova = Transacao(usuario_id=usuario_id, descricao=descricao, valor=valor, categoria=categoria, conta_id=conta_id)
    if data is not None:
        nova.data = data

    db.session.add(nova)
    db.session.commit()
    resposta = transacao_com_conta(nova, nomes_das_contas(usuario_id))
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
    nova_descricao, novo_valor, nova_categoria, nova_data = t.descricao, t.valor, t.categoria, t.data

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

    if "data" in dados:
        nova_data, mensagem = _ler_data(dados["data"])
        if nova_data is None:
            return erro(mensagem)

    # vale para a combinacao final: trocar o sinal de uma receita "Salário" tambem e barrado
    if nova_categoria == "Salário" and novo_valor < 0:
        return erro(MSG_SALARIO + " (troque também a categoria)")

    nome_conta, mensagem = _ler_nome_conta(dados.get("conta")) if "conta" in dados else (None, None)
    if mensagem:
        return erro(mensagem)

    antes = fotografar_alertas(usuario_id)
    nova_conta_id = t.conta_id
    try:
        if "conta" in dados:
            nova_conta_id = conta_por_nome(usuario_id, nome_conta, criar=True).id if nome_conta else None
        if novo_valor > 0:
            nova_conta_id = None                                    # receita nao tem conta
        # a regra do vale so e conferida quando a conta ou a categoria estao sendo mudadas agora
        if nova_conta_id and novo_valor < 0 and ("conta" in dados or "categoria" in dados):
            checar_categoria(usuario_id, No.query.get(nova_conta_id), nova_categoria)
    except ContaInvalida as e:
        db.session.rollback()
        return erro(str(e))

    categoria_mudou = nova_categoria != t.categoria
    t.descricao, t.valor, t.categoria, t.data, t.conta_id = nova_descricao, novo_valor, nova_categoria, nova_data, nova_conta_id

    if categoria_mudou:
        _mover_projecoes(usuario_id, t.descricao, nova_categoria)

    db.session.commit()
    resposta = transacao_com_conta(t, nomes_das_contas(usuario_id))
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
