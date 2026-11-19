"""
saldo que continua de um mes para o outro

  saldo no inicio do mes  = tudo que entrou e saiu ANTES dele (mais o saldo inicial informado, se houver)
  saldo no fim do mes     = saldo no inicio + receitas do mes - despesas do mes

assim, quem termina novembro com R$ 1.000 comeca dezembro com R$ 1.000
"""
from sqlalchemy import func

from database import db
from modelos.modelos import Transacao, Usuario
from servicos.financeiro import limites_do_mes, resumo_mensal


def saldo_anterior(usuario_id, mes, usuario=None):
    """
    saldo no INICIO do mes ("AAAA-MM"). devolve None quando nao ha como saber:
    o usuario informou um saldo inicial e este mes e anterior a ele (antes disso o sistema nao sabe quanto havia)
    - sem saldo inicial: soma tudo o que foi registrado antes do mes
    - com saldo inicial: ele vale no inicio do mes informado; so os lancamentos a partir dai entram na conta
    """
    usuario = usuario or db.session.get(Usuario, usuario_id)
    inicio, _ = limites_do_mes(mes)
    consulta = db.session.query(func.coalesce(func.sum(Transacao.valor), 0.0)).filter(Transacao.usuario_id == usuario_id, Transacao.data < inicio)

    base = 0.0
    referencia = usuario.saldo_inicial_mes if usuario else None
    if referencia:
        inicio_referencia, _ = limites_do_mes(referencia)
        if inicio < inicio_referencia:
            return None
        base = usuario.saldo_inicial or 0.0
        consulta = consulta.filter(Transacao.data >= inicio_referencia)
    return round(base + float(consulta.scalar() or 0.0), 2)


def resumo_com_saldo(usuario_id, mes):
    """
    receitas, despesas e os tres saldos do mes:
      saldo_anterior (inicio do mes; None se desconhecido), saldo_do_mes (so o que aconteceu no mes) e saldo_final (fim do mes)
    """
    usuario = db.session.get(Usuario, usuario_id)
    resumo = resumo_mensal(usuario_id, mes)
    anterior = saldo_anterior(usuario_id, mes, usuario)
    return {
        "mes": mes,
        "saldo_anterior": anterior,
        "receita": resumo["receita"],
        "despesa": resumo["despesa"],
        "saldo_do_mes": resumo["saldo"],
        "saldo_final": None if anterior is None else round(anterior + resumo["saldo"], 2),
        "saldo_inicial_informado": bool(usuario and usuario.saldo_inicial_mes),
    }
