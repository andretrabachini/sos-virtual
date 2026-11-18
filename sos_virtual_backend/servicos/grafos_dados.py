"""
dados do grafo financeiro de um usuario (contas, categorias aceitas por conta e o calculo do mes)
usado pela rota /api/grafo e pelo assistente; nao depende do Flask
"""
from collections import defaultdict

from modelos.modelos import ContaCategoria, No, Transacao
from servicos.financeiro import CATEGORIAS, limites_do_mes
from servicos.grafos_service import calcular_roteamento_otimizado


def contas_do_usuario(usuario_id):
    return No.query.filter_by(usuario_id=usuario_id, tipo="conta").order_by(No.nome).all()


def categorias_por_conta(usuario_id):
    """{conta_id: [categorias que ela aceita]}; conta fora do mapa = aceita qualquer categoria"""
    mapa = defaultdict(list)
    for linha in ContaCategoria.query.filter_by(usuario_id=usuario_id).all():
        mapa[linha.conta_id].append(linha.categoria)
    return {cid: sorted(cats, key=CATEGORIAS.index) for cid, cats in mapa.items()}


def movimentos_do_mes(usuario_id, mes):
    """
    despesas do mes separadas em: ja registradas em uma conta (fixos) e ainda sem conta (pendentes).
    so as pendentes sao otimizadas; as registradas ja aconteceram e consomem o limite da conta
    """
    inicio, fim = limites_do_mes(mes)
    fixos, pendentes = defaultdict(float), defaultdict(float)
    for t in Transacao.query.filter(Transacao.usuario_id == usuario_id, Transacao.data >= inicio,
                                    Transacao.data < fim, Transacao.valor < 0).all():
        if t.conta_id:
            fixos[(t.conta_id, t.categoria)] += -t.valor
        else:
            pendentes[t.categoria] += -t.valor
    return ([{"conta_id": c, "categoria": k, "valor": round(v, 2)} for (c, k), v in fixos.items()],
            {k: round(v, 2) for k, v in pendentes.items()})


def calcular_do_mes(usuario_id, mes, despesas=None):
    """despesas=None usa o que esta sem conta no mes; um dict simula outros valores para essa parte"""
    mapa = categorias_por_conta(usuario_id)
    contas = [
        {"id": c.id, "nome": c.nome, "capacidade": c.capacidade, "custo": c.custo or 0.0,
         "categorias": mapa.get(c.id, [])}
        for c in contas_do_usuario(usuario_id)
    ]
    fixos, pendentes = movimentos_do_mes(usuario_id, mes)
    resultado = calcular_roteamento_otimizado(contas, pendentes if despesas is None else despesas, fixos)

    registradas = defaultdict(float)
    for f in fixos:
        registradas[f["categoria"]] += f["valor"]
    resultado.update({"mes": mes, "pendentes": pendentes, "registradas": {k: round(v, 2) for k, v in registradas.items()}})
    return resultado
