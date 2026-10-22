"""
grava no banco os lancamentos lidos de um extrato e projeta as parcelas futuras
a leitura do arquivo em si fica em servicos/extratos.py
"""
from collections import Counter, defaultdict
from datetime import datetime
from uuid import uuid4

from dateutil.relativedelta import relativedelta

from database import db
from modelos.modelos import Aresta, No, Transacao
from servicos.extratos import (
    calcular_parcelas,
    chave_compra,
    detectar_parcela,
    gerar_projecoes,
)
from servicos.financeiro import detectar_categoria


def _obter_no(usuario_id, nome, tipo, cache):
    """busca o no (conta ou categoria) do usuario e cria se ainda nao existir"""
    chave = (nome, tipo)
    if chave not in cache:
        no = No.query.filter_by(usuario_id=usuario_id, nome=nome, tipo=tipo).first()
        if no is None:
            no = No(usuario_id=usuario_id, nome=nome, tipo=tipo)
            db.session.add(no)
            db.session.flush()  # gera o id sem finalizar a transacao
        cache[chave] = no
    return cache[chave]


def _projetar_parcelas(usuario_id, no_conta, no_categoria, lanc, atual, total, valores):
    """cria as arestas das parcelas futuras de uma compra; devolve quantas foram criadas"""
    chave = chave_compra(lanc["descricao"], total)

    # a parcela que acabou de aparecer no extrato virou lancamento real:
    # se ela estava projetada de um extrato anterior, remove a projecao para nao contar duas vezes
    Aresta.query.filter_by(
        usuario_id=usuario_id, chave_compra=chave, parcela_atual=atual, projetada=True
    ).delete(synchronize_session=False)

    ja_projetadas = {
        a.parcela_atual
        for a in Aresta.query.filter_by(usuario_id=usuario_id, chave_compra=chave, projetada=True)
    }

    grupo = uuid4().hex
    criadas = 0
    # laço que percorre cada parcela futura, avancando a data mes a mes
    for p in gerar_projecoes(lanc["data"], atual, total, valores):
        if p["numero"] in ja_projetadas:
            continue  # essa parcela ja foi projetada por uma importacao anterior
        db.session.add(Aresta(
            usuario_id=usuario_id,
            origem_id=no_conta.id,
            destino_id=no_categoria.id,
            peso=p["valor"],
            data=p["data"],
            descricao=lanc["descricao"],
            projetada=True,
            parcela_atual=p["numero"],
            total_parcelas=total,
            grupo_parcelamento=grupo,
            chave_compra=chave,
        ))
        criadas += 1
    return criadas


def importar_lancamentos(usuario_id, lancamentos, conta, valor_e_total=False, detectar=True):
    """
    grava os lancamentos como transacoes, pula os que ja foram importados antes
    e, para compras parceladas, cria as parcelas futuras como arestas projetadas
    NAO faz commit: quem chama decide (assim, se algo falhar, nada fica pela metade)
    """
    resumo = {"importadas": 0, "duplicadas": 0, "parceladas": [], "projecoes_criadas": 0}
    cache_nos = {}
    no_conta = _obter_no(usuario_id, conta, "conta", cache_nos)

    # carrega de uma vez o que ja existe no periodo, para detectar reimportacao do mesmo extrato
    # contamos ocorrencias: duas compras iguais no mesmo dia continuam valendo as duas
    datas = [l["data"] for l in lancamentos]
    existentes = Transacao.query.filter(
        Transacao.usuario_id == usuario_id,
        Transacao.data >= min(datas),
        Transacao.data <= max(datas),
    ).all()
    contagem = Counter((t.data, t.descricao, round(t.valor, 2)) for t in existentes)

    for lanc in lancamentos:
        descricao = lanc["descricao"]
        valor = lanc["valor"]

        # so despesas podem ser parceladas
        parcela = detectar_parcela(descricao) if (detectar and valor < 0) else None
        valores = None
        if parcela:
            atual, total = parcela
            valores = calcular_parcelas(abs(valor), atual, total, valor_e_total)
            valor = -valores[atual - 1]  # valor da parcela deste mes

        chave = (lanc["data"], descricao, round(valor, 2))
        if contagem[chave] > 0:
            contagem[chave] -= 1
            resumo["duplicadas"] += 1
            continue

        categoria = detectar_categoria(descricao)
        db.session.add(Transacao(
            usuario_id=usuario_id,
            descricao=descricao,
            valor=valor,
            categoria=categoria,
            data=lanc["data"],
        ))
        resumo["importadas"] += 1

        if parcela:
            no_categoria = _obter_no(usuario_id, categoria, "categoria", cache_nos)
            criadas = _projetar_parcelas(
                usuario_id, no_conta, no_categoria, lanc, atual, total, valores
            )
            resumo["projecoes_criadas"] += criadas
            resumo["parceladas"].append({
                "descricao": descricao,
                "parcela": f"{atual}/{total}",
                "valor_parcela": abs(valor),
                "projecoes_criadas": criadas,
            })

    return resumo


def projecao_mensal(usuario_id, renda_mensal, meses):
    """
    soma as parcelas futuras de cada um dos proximos meses
    e calcula quanto da renda continua livre depois delas
    """
    agora = datetime.utcnow()
    mes_atual = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    inicio = mes_atual + relativedelta(months=1)           # o mes atual ja esta nas transacoes reais
    fim = mes_atual + relativedelta(months=meses + 1)

    arestas = Aresta.query.filter(
        Aresta.usuario_id == usuario_id,
        Aresta.projetada.is_(True),
        Aresta.data >= inicio,
        Aresta.data < fim,
    ).all()

    totais = defaultdict(float)
    for a in arestas:
        totais[a.data.strftime("%Y-%m")] += float(a.peso)

    resultado = []
    for i in range(1, meses + 1):
        mes = (mes_atual + relativedelta(months=i)).strftime("%Y-%m")
        comprometido = round(totais.get(mes, 0.0), 2)
        resultado.append({
            "mes": mes,
            "comprometido": comprometido,
            # sem renda informada no cadastro nao da para calcular o saldo livre
            "saldo_livre": round(renda_mensal - comprometido, 2) if renda_mensal else None,
        })
    return resultado
