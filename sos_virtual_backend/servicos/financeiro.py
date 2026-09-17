from modelos.modelos import Transacao
from datetime import datetime


# categorias disponiveis no sistema
CATEGORIAS = [
    "Alimentação",
    "Transporte",
    "Saúde",
    "Educação",
    "Lazer",
    "Moradia",
    "Vestuário",
    "Investimentos",
    "Outros"
]


def detectar_categoria(texto: str) -> str:
    """
    tenta adivinhar a categoria de uma transacao com base nas palavras da descricao
    se nao encontrar nenhuma correspondencia, retorna 'Outros'
    """
    texto = texto.lower()

    regras = {
        "Alimentação": ["mercado", "restaurante", "almoço", "jantar", "lanche", "ifood", "comida", "padaria"],
        "Transporte":  ["uber", "99", "gasolina", "ônibus", "metrô", "passagem", "carro", "combustivel"],
        "Saúde":       ["farmácia", "médico", "consulta", "remédio", "plano de saúde", "dentista", "hospital"],
        "Educação":    ["curso", "faculdade", "livro", "escola", "mensalidade", "apostila"],
        "Lazer":       ["cinema", "show", "netflix", "spotify", "viagem", "hotel", "jogo"],
        "Moradia":     ["aluguel", "condomínio", "luz", "água", "internet", "energia", "gás"],
        "Vestuário":   ["roupa", "tênis", "sapato", "camisa", "calça", "loja"],
        "Investimentos": ["investimento", "poupança", "tesouro", "ação", "fundo"],
    }

    for categoria, palavras in regras.items():
        if any(palavra in texto for palavra in palavras):
            return categoria

    return "Outros"


def gastos_por_categoria(usuario_id: int) -> dict:
    """
    retorna um dicionario com o total gasto em cada categoria no mes atual
    so conta as despesas (valores negativos)
    """
    agora = datetime.utcnow()
    inicio_mes = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    transacoes = Transacao.query.filter(
        Transacao.usuario_id == usuario_id,
        Transacao.data >= inicio_mes,
        Transacao.valor < 0  # so despesas
    ).all()

    totais = {}
    for t in transacoes:
        totais[t.categoria] = round(totais.get(t.categoria, 0) + abs(t.valor), 2)

    return totais


def resumo_mensal(usuario_id: int) -> dict:
    """
    calcula receita total, despesa total e saldo do mes atual
    """
    agora = datetime.utcnow()
    inicio_mes = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    transacoes = Transacao.query.filter(
        Transacao.usuario_id == usuario_id,
        Transacao.data >= inicio_mes
    ).all()

    receita = sum(t.valor for t in transacoes if t.valor > 0)
    despesa = abs(sum(t.valor for t in transacoes if t.valor < 0))

    return {
        "receita": round(receita, 2),
        "despesa": round(despesa, 2),
        "saldo": round(receita - despesa, 2)
    }
