from modelos.modelos import Transacao
from datetime import datetime

from dateutil.relativedelta import relativedelta

# a deteccao de categoria mora em servicos/categorizacao.py; o nome continua importavel daqui
from servicos.categorizacao import detectar_categoria  # noqa: F401
from servicos.tempo import agora


# categorias disponiveis no sistema
CATEGORIAS = [
    "Alimentação",
    "Restaurante",
    "Transporte",
    "Saúde",
    "Educação",
    "Lazer",
    "Moradia",
    "Vestuário",
    "Investimentos",
    "Outros"
]


def limites_do_mes(mes=None):
    """
    devolve (inicio, fim) de um mes "AAAA-MM" (padrao: o mes atual): inicio inclusive, fim exclusivo (dia 1 do mes seguinte)
    sem o limite de fim, lancamentos com data de meses futuros eram somados no mes atual
    """
    if mes:
        inicio = datetime(int(mes[:4]), int(mes[5:7]), 1)
    else:
        inicio = agora().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return inicio, inicio + relativedelta(months=1)


def gastos_por_categoria(usuario_id: int, mes=None) -> dict:
    """
    retorna um dicionario com o total gasto em cada categoria no mes ("AAAA-MM"; padrao: o atual)
    so conta as despesas (valores negativos)
    """
    inicio_mes, fim_mes = limites_do_mes(mes)

    transacoes = Transacao.query.filter(
        Transacao.usuario_id == usuario_id,
        Transacao.data >= inicio_mes,
        Transacao.data < fim_mes,
        Transacao.valor < 0  # so despesas
    ).all()

    totais = {}
    for t in transacoes:
        totais[t.categoria] = round(totais.get(t.categoria, 0) + abs(t.valor), 2)

    return totais


def resumo_mensal(usuario_id: int, mes=None) -> dict:
    """
    calcula receita total, despesa total e saldo do mes ("AAAA-MM"; padrao: o atual)
    """
    inicio_mes, fim_mes = limites_do_mes(mes)

    transacoes = Transacao.query.filter(
        Transacao.usuario_id == usuario_id,
        Transacao.data >= inicio_mes,
        Transacao.data < fim_mes
    ).all()

    receita = sum(t.valor for t in transacoes if t.valor > 0)
    despesa = abs(sum(t.valor for t in transacoes if t.valor < 0))

    return {
        "receita": round(receita, 2),
        "despesa": round(despesa, 2),
        "saldo": round(receita - despesa, 2)
    }
