"""
regras de contas e cartoes usadas por varias rotas (transacoes, compras parceladas, importacao)
"""
from database import db
from modelos.modelos import ContaCategoria, No

MAX_CONTAS = 20   # mantem o grafo pequeno e a resposta rapida


class ContaInvalida(Exception):
    """problema com a conta escolhida, com mensagem segura para mostrar ao usuario"""


def categorias_aceitas(usuario_id, conta_id):
    """categorias que a conta aceita; lista vazia = qualquer uma"""
    return sorted(l.categoria for l in ContaCategoria.query.filter_by(usuario_id=usuario_id, conta_id=conta_id).all())


def conta_por_nome(usuario_id, nome, criar=False):
    """a conta do usuario com esse nome; com criar=True cria quando ainda nao existe (respeitando o limite de contas)"""
    conta = No.query.filter_by(usuario_id=usuario_id, nome=nome, tipo="conta").first()
    if conta is not None or not criar:
        return conta
    if No.query.filter_by(usuario_id=usuario_id, tipo="conta").count() >= MAX_CONTAS:
        raise ContaInvalida(f"limite de {MAX_CONTAS} contas atingido")
    conta = No(usuario_id=usuario_id, nome=nome, tipo="conta")
    db.session.add(conta)
    db.session.flush()           # gera o id sem finalizar a transacao
    return conta


def checar_categoria(usuario_id, conta, categoria):
    """um vale so paga as categorias dele: registrar uma compra fora disso e recusado, com orientacao"""
    aceitas = categorias_aceitas(usuario_id, conta.id)
    if aceitas and categoria not in aceitas:
        raise ContaInvalida(f"{conta.nome} só paga: {', '.join(aceitas)}. Escolha outra conta ou ajuste as categorias dela no Otimizador.")


def nomes_das_contas(usuario_id):
    return {n.id: n.nome for n in No.query.filter_by(usuario_id=usuario_id, tipo="conta").all()}


def transacao_com_conta(transacao, nomes):
    """dicionario da transacao com o nome da conta onde foi paga"""
    dados = transacao.para_dict()
    dados["conta"] = nomes.get(transacao.conta_id) if transacao.conta_id else None
    return dados
