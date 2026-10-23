"""
roteamento otimizado de pagamentos com grafos (fluxo de custo minimo)

o grafo tem 4 camadas:
    S (super fonte) -> contas/cartoes -> categorias de despesa -> T (super sumidouro)

- S -> conta:       capacidade = quanto a conta consegue pagar no mes (limite do cartao, saldo)
                    custo = % por R$ pago (negativo = cashback/beneficio, positivo = juros/taxa)
- conta -> categoria: por padrao toda conta pode pagar toda categoria (ou so o que for
                    informado em `transacoes`, com um limite por ligacao)
- categoria -> T:   capacidade = valor da despesa, que precisa ser paga por inteiro

o algoritmo (network simplex, do networkx) trabalha melhor com numeros INTEIROS. por isso tudo roda em
centavos, e o custo em "centesimos de ponto percentual por centavo" (1,5% -> 150)
"""
import networkx as nx

# R$ = centavos * custo_inteiro / 1_000_000 (centavos -> reais /100; centesimos de % -> fracao /10_000)
ESCALA_CUSTO = 1_000_000


def _centavos(valor):
    return int(round(float(valor) * 100))


def _reais(centavos):
    return round(centavos / 100, 2)


def _brl(centavos):
    texto = f"{centavos / 100:,.2f}"          # 1,234.56
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _peso(custo_percentual):
    """1,5 (% de cashback com sinal negativo: -1,5) -> inteiro usado como peso da aresta"""
    return int(round(float(custo_percentual or 0) * 100))


def _dinheiro(valor_centavos, peso):
    """efeito em R$ de pagar `valor_centavos` numa conta de peso `peso` (positivo = ganho/cashback)"""
    return round(-valor_centavos * peso / ESCALA_CUSTO, 2) + 0.0   # "+ 0.0" evita o -0.0


def calcular_roteamento_otimizado(contas, despesas, transacoes=None):
    """
    :param contas: lista de dicts {"id", "nome", "capacidade" (R$ ou None = sem limite), "custo" (%)}
    :param despesas: dict {categoria: valor em R$} - o que precisa ser pago no mes
    :param transacoes: opcional, lista de {"conta_id", "categoria", "limite"}: restringe quais contas
                       podem pagar quais categorias. sem isso, toda conta paga toda categoria
    :return: dict com status "sucesso", "gargalo" ou "vazio" (nunca levanta erro de negocio)
    """
    demanda = {}
    for categoria, valor in despesas.items():
        centavos = _centavos(valor)
        if centavos > 0:
            demanda[categoria] = centavos

    if not contas:
        return {"status": "vazio", "mensagem": "Cadastre pelo menos uma conta ou cartão para calcular."}
    if not demanda:
        return {"status": "vazio", "mensagem": "Não há despesas para distribuir."}

    total = sum(demanda.values())

    # conta sem limite informado: pode pagar qualquer valor (limitada so pelo total das despesas)
    capacidade = {
        c["id"]: total if c.get("capacidade") is None else _centavos(c["capacidade"])
        for c in contas
    }

    def gargalo(capacidade_total):
        falta = total - capacidade_total
        return {
            "status": "gargalo",
            "mensagem": (f"Gargalo detectado! O limite das contas ({_brl(capacidade_total)}) "
                         f"não cobre as despesas ({_brl(total)}). Faltam {_brl(falta)}."),
            "total_despesas": _reais(total),
            "capacidade_total": _reais(capacidade_total),
            "falta": _reais(falta),
        }

    if sum(capacidade.values()) < total:
        return gargalo(sum(capacidade.values()))

    # ---------- monta o grafo ----------
    G = nx.DiGraph()
    G.add_node("S", demand=-total)   # injeta o dinheiro
    G.add_node("T", demand=total)    # consome o dinheiro

    no_conta = {c["id"]: f"conta:{c['id']}" for c in contas}
    pesos = {c["id"]: _peso(c.get("custo")) for c in contas}

    # camada 1: fonte -> contas (o beneficio/custo e cobrado aqui, uma vez por real que passa pela conta)
    for c in contas:
        G.add_edge("S", no_conta[c["id"]], capacity=capacidade[c["id"]], weight=pesos[c["id"]])

    # camada 2: contas -> categorias (sem custo proprio)
    if transacoes is None:
        for c in contas:
            for categoria, valor in demanda.items():
                G.add_edge(no_conta[c["id"]], f"cat:{categoria}", capacity=valor, weight=0)
    else:
        for t in transacoes:
            if t["conta_id"] in no_conta and t["categoria"] in demanda:
                G.add_edge(no_conta[t["conta_id"]], f"cat:{t['categoria']}",
                           capacity=_centavos(t["limite"]), weight=0)

    # camada 3: categorias -> sumidouro (cada despesa precisa ser paga por inteiro)
    for categoria, valor in demanda.items():
        G.add_edge(f"cat:{categoria}", "T", capacity=valor, weight=0)

    # ---------- resolve ----------
    try:
        # network simplex: alem de achar o custo minimo, devolve solucoes "basicas", que dividem poucas
        # despesas entre contas (capacity scaling achava o mesmo custo, mas picotava mais os pagamentos)
        custo_total, fluxo = nx.network_simplex(G)
    except nx.NetworkXUnfeasible:
        # com restricoes (transacoes), o total das contas pode bastar mas as ligacoes nao
        return gargalo(sum(capacidade.values())) if sum(capacidade.values()) < total else {
            "status": "gargalo",
            "mensagem": "Gargalo detectado! As contas liberadas para cada despesa não conseguem cobrir o valor total.",
            "total_despesas": _reais(total),
        }

    # ---------- monta a resposta ----------
    plano, nos, usado_por_conta = [], [], {}
    for c in contas:
        origem = no_conta[c["id"]]
        usado = fluxo["S"].get(origem, 0)
        usado_por_conta[c["id"]] = usado
        for categoria in demanda:
            valor = fluxo.get(origem, {}).get(f"cat:{categoria}", 0)
            if valor > 0:
                plano.append({
                    "conta_id": c["id"],
                    "conta": c["nome"],
                    "categoria": categoria,
                    "valor": _reais(valor),
                    "efeito": _dinheiro(valor, pesos[c["id"]]),
                })
        nos.append({
            "id": origem,
            "nome": c["nome"],
            "tipo": "conta",
            "usado": _reais(usado),
            "capacidade": None if c.get("capacidade") is None else _reais(capacidade[c["id"]]),
            "custo": float(c.get("custo") or 0),
            "efeito": _dinheiro(usado, pesos[c["id"]]),
        })
    for categoria, valor in demanda.items():
        nos.append({"id": f"cat:{categoria}", "nome": categoria, "tipo": "categoria", "valor": _reais(valor)})

    return {
        "status": "sucesso",
        "total_despesas": _reais(total),
        # custo_total e negativo quando ha cashback: o beneficio liquido e o oposto dele
        "beneficio_total": round(-custo_total / ESCALA_CUSTO, 2) + 0.0,
        "plano": plano,
        "nos": nos,
        "arestas": [
            {"origem": f"conta:{p['conta_id']}", "destino": f"cat:{p['categoria']}", "valor": p["valor"]}
            for p in plano
        ],
    }
