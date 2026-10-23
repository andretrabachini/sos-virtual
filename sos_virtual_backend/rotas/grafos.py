from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required
from sqlalchemy.exc import IntegrityError

from database import db
from extensoes import limiter, usuario_id_atual
from modelos.modelos import Aresta, No
from servicos.financeiro import CATEGORIAS, gastos_por_categoria
from servicos.grafos_service import calcular_roteamento_otimizado
from validacao import VALOR_MAX, corpo_json, erro, numero, texto

grafos_bp = Blueprint("grafos", __name__, url_prefix="/api")

MAX_CONTAS = 20   # mantem o grafo pequeno e a resposta rapida


# ------------------------------------------------------------------ contas (nos do tipo 'conta')

def _contas_do_usuario(usuario_id):
    return No.query.filter_by(usuario_id=usuario_id, tipo="conta").order_by(No.nome).all()


def _validar_campos(dados, nome_obrigatorio):
    """devolve (campos, None) ou (None, mensagem de erro); so valida o que veio no corpo"""
    campos = {}

    if nome_obrigatorio or "nome" in dados:
        nome = texto(dados.get("nome"), 1, 100)
        if nome is None:
            return None, "informe o nome da conta ou cartão (até 100 caracteres)"
        campos["nome"] = nome

    if "capacidade" in dados:
        if dados["capacidade"] in (None, ""):
            campos["capacidade"] = None          # sem limite informado
        else:
            capacidade = numero(dados["capacidade"], 0.01, VALOR_MAX)
            if capacidade is None:
                return None, "limite inválido (precisa ser maior que zero)"
            campos["capacidade"] = capacidade

    if "custo" in dados:
        # percentual por real pago: negativo = cashback/beneficio, positivo = juros/taxa
        custo = numero(dados["custo"], -100, 100)
        if custo is None:
            return None, "percentual inválido (entre -100 e 100)"
        campos["custo"] = custo

    return campos, None


@grafos_bp.route("/contas", methods=["GET"])
@jwt_required()
def listar_contas():
    return jsonify([c.para_dict() for c in _contas_do_usuario(usuario_id_atual())])


@grafos_bp.route("/contas", methods=["POST"])
@jwt_required()
def criar_conta():
    usuario_id = usuario_id_atual()
    dados = corpo_json()
    if dados is None:
        return erro("corpo da requisição inválido")

    campos, mensagem = _validar_campos(dados, nome_obrigatorio=True)
    if campos is None:
        return erro(mensagem)

    if No.query.filter_by(usuario_id=usuario_id, tipo="conta").count() >= MAX_CONTAS:
        return erro(f"limite de {MAX_CONTAS} contas atingido")
    if No.query.filter_by(usuario_id=usuario_id, tipo="conta", nome=campos["nome"]).first():
        return erro("já existe uma conta com esse nome", 409)

    nova = No(
        usuario_id=usuario_id,
        tipo="conta",
        nome=campos["nome"],
        capacidade=campos.get("capacidade"),
        custo=campos.get("custo", 0.0),
    )
    db.session.add(nova)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return erro("já existe uma conta com esse nome", 409)
    return jsonify(nova.para_dict()), 201


@grafos_bp.route("/contas/<int:conta_id>", methods=["PUT"])
@jwt_required()
def editar_conta(conta_id):
    usuario_id = usuario_id_atual()
    # filtra pelo usuario do token: ninguem mexe na conta de outra pessoa
    conta = No.query.filter_by(id=conta_id, usuario_id=usuario_id, tipo="conta").first_or_404()

    dados = corpo_json()
    if dados is None:
        return erro("corpo da requisição inválido")

    campos, mensagem = _validar_campos(dados, nome_obrigatorio=False)
    if campos is None:
        return erro(mensagem)

    if "nome" in campos and campos["nome"] != conta.nome:
        if No.query.filter_by(usuario_id=usuario_id, tipo="conta", nome=campos["nome"]).first():
            return erro("já existe uma conta com esse nome", 409)

    for campo, valor in campos.items():
        setattr(conta, campo, valor)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return erro("já existe uma conta com esse nome", 409)
    return jsonify(conta.para_dict())


@grafos_bp.route("/contas/<int:conta_id>", methods=["DELETE"])
@jwt_required()
def excluir_conta(conta_id):
    usuario_id = usuario_id_atual()
    conta = No.query.filter_by(id=conta_id, usuario_id=usuario_id, tipo="conta").first_or_404()

    # as parcelas futuras projetadas a partir dessa conta saem junto (a chave estrangeira exige)
    Aresta.query.filter_by(usuario_id=usuario_id, origem_id=conta.id).delete(synchronize_session=False)
    db.session.delete(conta)
    db.session.commit()
    return jsonify({"mensagem": "conta removida"})


# ------------------------------------------------------------------ grafo e otimizacao

def _calcular(usuario_id, despesas):
    contas = [
        {"id": c.id, "nome": c.nome, "capacidade": c.capacidade, "custo": c.custo or 0.0}
        for c in _contas_do_usuario(usuario_id)
    ]
    return calcular_roteamento_otimizado(contas, despesas)


@grafos_bp.route("/grafo", methods=["GET"])
@jwt_required()
def grafo():
    """melhor forma de pagar as despesas do mes atual (alimenta o mapa do painel)"""
    usuario_id = usuario_id_atual()
    return jsonify(_calcular(usuario_id, gastos_por_categoria(usuario_id)))


@grafos_bp.route("/grafo/otimizar", methods=["POST"])
@jwt_required()
@limiter.limit("60 per hour")
def otimizar():
    """
    mesmo calculo, mas com valores informados pelo usuario (simulacao):
      {"despesas": {"Aluguel": 1600, "Alimentação": 900}}
    sem o campo "despesas", usa os gastos do mes atual
    """
    usuario_id = usuario_id_atual()
    dados = corpo_json()
    if dados is None:
        return erro("corpo da requisição inválido")

    informadas = dados.get("despesas")
    if informadas is None:
        despesas = gastos_por_categoria(usuario_id)
    else:
        if not isinstance(informadas, dict) or len(informadas) > len(CATEGORIAS):
            return erro("'despesas' deve ser um objeto categoria -> valor")
        despesas = {}
        for categoria, valor in informadas.items():
            if categoria not in CATEGORIAS:
                return erro(f"categoria inválida: {str(categoria)[:40]}")
            valor = numero(valor, 0, VALOR_MAX)
            if valor is None:
                return erro(f"valor inválido em {categoria} (número entre zero e o máximo permitido)")
            despesas[categoria] = valor

    return jsonify(_calcular(usuario_id, despesas))
