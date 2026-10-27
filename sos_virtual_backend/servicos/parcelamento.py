"""
compras parceladas registradas a mao: calculo das parcelas (com ou sem juros) e gravacao no banco

regras
- com juros usa a TABELA PRICE, a mais comum no varejo e nos cartoes: parcelas iguais,
  PMT = valor_a_vista * i / (1 - (1 + i)^-n), com i = juros ao mes e n = numero de parcelas
- sem juros divide em centavos e o resto vai para as primeiras parcelas (a soma fecha exata)
- parcelas com data ate o fim do mes atual viram LANCAMENTOS (transacoes reais);
  as de meses seguintes viram parcelas FUTURAS (arestas projetadas), que aparecem na projecao do painel
"""
import hashlib
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from dateutil.relativedelta import relativedelta

from database import db
from servicos.extratos import limpar_descricao_parcela
from modelos.modelos import Aresta, No, Parcelamento, Transacao

MIN_PARCELAS, MAX_PARCELAS = 2, 36
JUROS_MAX = 30.0          # % ao mes (acima disso quase certamente e engano de digitacao)
CENTAVO = Decimal("0.01")


# ------------------------------------------------------------------ calculo (funcoes puras)

def cronograma(valor_vista, parcelas, juros_mensal=0.0):
    """lista com o valor de cada parcela, em reais"""
    vista = Decimal(str(valor_vista))
    n = int(parcelas)
    taxa = Decimal(str(juros_mensal or 0)) / 100

    if taxa == 0:
        centavos = int((vista * 100).to_integral_value(ROUND_HALF_UP))
        base, resto = divmod(centavos, n)
        return [(base + (1 if i < resto else 0)) / 100 for i in range(n)]

    pmt = (vista * taxa / (1 - (1 + taxa) ** (-n))).quantize(CENTAVO, ROUND_HALF_UP)
    return [float(pmt)] * n


def resumo_parcelamento(valor_vista, parcelas, juros_mensal=0.0):
    valores = cronograma(valor_vista, parcelas, juros_mensal)
    total = round(sum(valores), 2)
    return {
        "numero_parcelas": int(parcelas),
        "valor_parcela": valores[0],
        "ultima_parcela": valores[-1],          # so difere da primeira nas compras sem juros com centavos sobrando
        "valor_total": total,
        "juros_total": round(total - float(valor_vista), 2),
        "juros_mensal": float(juros_mensal or 0),
    }


def datas_das_parcelas(inicio, parcelas):
    """uma por mes, a partir da primeira; relativedelta cuida do fim de mes (31/01 + 1 mes = 28/02)"""
    return [inicio + relativedelta(months=k) for k in range(int(parcelas))]


def _inicio_do_proximo_mes():
    agora = datetime.utcnow()
    return agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0) + relativedelta(months=1)


# ------------------------------------------------------------------ gravacao

def _obter_no(usuario_id, nome, tipo):
    no = No.query.filter_by(usuario_id=usuario_id, nome=nome, tipo=tipo).first()
    if no is None:
        no = No(usuario_id=usuario_id, nome=nome, tipo=tipo)
        db.session.add(no)
        db.session.flush()
    return no


def criar_parcelamento(usuario_id, descricao, valor_vista, parcelas, juros_mensal, conta, categoria, data_inicio):
    """NAO faz commit: quem chama decide (assim, se algo falhar, nada fica pela metade)"""
    valores = cronograma(valor_vista, parcelas, juros_mensal)
    datas = datas_das_parcelas(data_inicio, parcelas)
    resumo = resumo_parcelamento(valor_vista, parcelas, juros_mensal)
    grupo = uuid4().hex
    limite = _inicio_do_proximo_mes()

    no_conta = _obter_no(usuario_id, conta, "conta")
    no_categoria = _obter_no(usuario_id, categoria, "categoria")

    lancadas = projetadas = 0
    for k, (valor, data) in enumerate(zip(valores, datas), start=1):
        descricao_k = f"{descricao} ({k}/{parcelas})"
        if data < limite:
            db.session.add(Transacao(usuario_id=usuario_id, descricao=descricao_k, valor=-valor,
                                     categoria=categoria, data=data))
            lancadas += 1
        else:
            db.session.add(Aresta(
                usuario_id=usuario_id, origem_id=no_conta.id, destino_id=no_categoria.id, peso=valor, data=data,
                descricao=descricao_k, projetada=True, parcela_atual=k, total_parcelas=int(parcelas),
                grupo_parcelamento=grupo, chave_compra=f"manual:{grupo}",
            ))
            projetadas += 1

    db.session.add(Parcelamento(
        usuario_id=usuario_id, grupo=grupo, descricao=descricao, valor_vista=float(valor_vista),
        valor_parcela=resumo["valor_parcela"], valor_total=resumo["valor_total"], numero_parcelas=int(parcelas),
        juros_mensal=float(juros_mensal or 0), conta=conta, categoria=categoria, data_inicio=data_inicio,
    ))
    resumo.update({"lancadas": lancadas, "projetadas": projetadas,
                   "primeira_data": datas[0].date().isoformat(), "ultima_data": datas[-1].date().isoformat()})
    return resumo


# ------------------------------------------------------------------ consulta

def _id_publico(chave):
    """identificador curto e estavel de uma compra parcelada (para a tela usar em exclusoes)"""
    if chave.startswith("manual:"):
        return "m" + chave[len("manual:"):]
    return "x" + hashlib.sha1(chave.encode("utf-8")).hexdigest()[:16]


def _grupos_de_arestas(usuario_id):
    grupos = defaultdict(list)
    for a in Aresta.query.filter_by(usuario_id=usuario_id, projetada=True).all():
        grupos[a.chave_compra or f"g:{a.grupo_parcelamento}"].append(a)
    return grupos


def listar_parcelamentos(usuario_id):
    """compras parceladas em andamento (as que ainda tem parcelas futuras), da mais proxima de terminar para a mais longa"""
    nomes = {n.id: n.nome for n in No.query.filter_by(usuario_id=usuario_id).all()}
    manuais = {p.grupo: p for p in Parcelamento.query.filter_by(usuario_id=usuario_id).all()}
    itens = []
    for chave, arestas in _grupos_de_arestas(usuario_id).items():
        arestas.sort(key=lambda a: a.parcela_atual or 0)
        primeira = arestas[0]
        manual = manuais.get(chave[len("manual:"):]) if chave.startswith("manual:") else None
        itens.append({
            "id": _id_publico(chave),
            "origem": "manual" if chave.startswith("manual:") else "extrato",
            "descricao": manual.descricao if manual else limpar_descricao_parcela(primeira.descricao),
            "conta": manual.conta if manual else nomes.get(primeira.origem_id, "—"),
            "categoria": manual.categoria if manual else nomes.get(primeira.destino_id, "—"),
            "total_parcelas": primeira.total_parcelas,
            "parcelas_pagas": (primeira.parcela_atual or 1) - 1,
            "parcelas_restantes": len(arestas),
            "valor_parcela": float(primeira.peso),
            "falta_pagar": round(sum(float(a.peso) for a in arestas), 2),
            "proxima_data": min(a.data for a in arestas).date().isoformat(),
            "ultima_data": max(a.data for a in arestas).date().isoformat(),
            "juros_mensal": manual.juros_mensal if manual else None,
            "valor_vista": manual.valor_vista if manual else None,
            "valor_total": manual.valor_total if manual else None,
        })
    itens.sort(key=lambda i: (i["parcelas_restantes"], i["descricao"]))
    return itens


def excluir_parcelamento(usuario_id, ident, incluir_lancadas=False):
    """
    remove as parcelas futuras de uma compra parcelada; para compras manuais pode remover tambem as
    parcelas ja lancadas em transacoes. devolve (encontrou, parcelas_futuras_removidas, lancadas_removidas)
    """
    for chave, arestas in _grupos_de_arestas(usuario_id).items():
        if _id_publico(chave) != ident:
            continue
        removidas = len(arestas)
        for a in arestas:
            db.session.delete(a)

        lancadas = 0
        if chave.startswith("manual:"):
            manual = Parcelamento.query.filter_by(usuario_id=usuario_id, grupo=chave[len("manual:"):]).first()
            if manual:
                if incluir_lancadas:
                    for k in range(1, manual.numero_parcelas + 1):
                        for t in Transacao.query.filter_by(usuario_id=usuario_id, descricao=f"{manual.descricao} ({k}/{manual.numero_parcelas})").all():
                            db.session.delete(t)
                            lancadas += 1
                db.session.delete(manual)
        return True, removidas, lancadas
    return False, 0, 0
