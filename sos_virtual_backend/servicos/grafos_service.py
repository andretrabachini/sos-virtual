"""
roteamento otimizado de pagamentos com grafos (fluxo de custo minimo)

o grafo tem 4 camadas:
    S (super fonte) -> contas/cartoes -> categorias de despesa -> T (super sumidouro)

- S -> conta:         capacidade = quanto a conta consegue pagar no mes (limite do cartao, saldo do vale)
                      custo = % por R$ pago (negativo = cashback/beneficio, positivo = juros/taxa)
- conta -> categoria: so existe se a conta ACEITA a categoria. conta sem restricao aceita todas;
                      conta restrita (ex.: Vale Alimentação so paga "Alimentação") so as escolhidas
- categoria -> T:     capacidade = valor da despesa, que precisa ser paga por inteiro

regra dos vales: uma conta restrita guarda dinheiro que NAO serve para o resto (o saldo do vale
nao paga o aluguel), entao ela e usada PRIMEIRO nas categorias que aceita. isso e feito somando um
bonus enorme ao peso dela, maior que qualquer cashback ou juros real. o bonus entra so no calculo:
os valores mostrados ao usuario (beneficio, efeito) usam sempre o percentual verdadeiro

o algoritmo (network simplex, do networkx) trabalha melhor com numeros INTEIROS. por isso tudo roda em
centavos, e o custo em "centesimos de ponto percentual por centavo" (1,5% -> 150)
"""
import networkx as nx

# R$ = centavos * custo_inteiro / 1_000_000 (centavos -> reais /100; centesimos de % -> fracao /10_000)
ESCALA_CUSTO = 1_000_000

# o percentual real vai de -100% a +100% (peso de -10_000 a +10_000); o bonus de prioridade passa disso
BONUS_PRIORIDADE = -20_000


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


def calcular_roteamento_otimizado(contas, despesas):
    """
    :param contas: lista de dicts {"id", "nome", "capacidade" (R$ ou None = sem limite),
                   "custo" (%), "categorias" (lista de categorias aceitas; vazia/None = todas)}
    :param despesas: dict {categoria: valor em R$} - o que precisa ser pago no mes
    :return: dict com status "sucesso", "gargalo" ou "vazio" (nunca levanta erro de negocio).
             no gargalo vem tambem o melhor plano parcial e o que ficou sem conta (nao_coberto)
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

    capacidade, restrita, aceitas, peso_real, peso_modelo = {}, {}, {}, {}, {}
    for c in contas:
        cid = c["id"]
        # conta sem limite informado: pode pagar qualquer valor (limitada so pelo total das despesas)
        capacidade[cid] = total if c.get("capacidade") is None else _centavos(c["capacidade"])
        escolhidas = c.get("categorias") or []
        restrita[cid] = bool(escolhidas)
        aceitas[cid] = [cat for cat in demanda if (not escolhidas or cat in escolhidas)]
        peso_real[cid] = _peso(c.get("custo"))
        peso_modelo[cid] = peso_real[cid] + (BONUS_PRIORIDADE if restrita[cid] else 0)

    # ---------- monta o grafo ----------
    G = nx.DiGraph()
    G.add_node("S", demand=-total)   # injeta o dinheiro
    G.add_node("T", demand=total)    # consome o dinheiro

    no_conta = {c["id"]: f"conta:{c['id']}" for c in contas}

    # camada 1: fonte -> contas (o beneficio/custo e cobrado aqui, uma vez por real que passa pela conta)
    for c in contas:
        G.add_edge("S", no_conta[c["id"]], capacity=capacidade[c["id"]], weight=peso_modelo[c["id"]])

    # camada 2: contas -> categorias que elas aceitam (sem custo proprio)
    for c in contas:
        for categoria in aceitas[c["id"]]:
            G.add_edge(no_conta[c["id"]], f"cat:{categoria}", capacity=demanda[categoria], weight=0)

    # camada 3: categorias -> sumidouro (cada despesa precisa ser paga por inteiro)
    for categoria, valor in demanda.items():
        G.add_edge(f"cat:{categoria}", "T", capacity=valor, weight=0)

    # ---------- resolve ----------
    try:
        _, fluxo = nx.network_simplex(G)
        nao_coberto = {}
    except nx.NetworkXUnfeasible:
        # nao da para pagar tudo: calcula o melhor que as contas conseguem (maximo pago, com o menor custo)
        # e descobre o que ficou sem conta, para explicar ao usuario onde esta o gargalo
        fluxo = nx.max_flow_min_cost(G, "S", "T")
        nao_coberto = {
            cat: demanda[cat] - fluxo[f"cat:{cat}"].get("T", 0)
            for cat in demanda if demanda[cat] - fluxo[f"cat:{cat}"].get("T", 0) > 0
        }

    # ---------- monta a resposta ----------
    plano, nos = [], []
    ganho = 0                     # em unidades de ESCALA_CUSTO, com o percentual REAL de cada conta
    for c in contas:
        cid, origem = c["id"], no_conta[c["id"]]
        usado = fluxo["S"].get(origem, 0)
        ganho += -usado * peso_real[cid]
        for categoria in demanda:
            valor = fluxo.get(origem, {}).get(f"cat:{categoria}", 0)
            if valor > 0:
                plano.append({
                    "conta_id": cid,
                    "conta": c["nome"],
                    "categoria": categoria,
                    "valor": _reais(valor),
                    "efeito": _dinheiro(valor, peso_real[cid]),
                })
        nos.append({
            "id": origem,
            "nome": c["nome"],
            "tipo": "conta",
            "usado": _reais(usado),
            "capacidade": None if c.get("capacidade") is None else _reais(capacidade[cid]),
            "custo": float(c.get("custo") or 0),
            "efeito": _dinheiro(usado, peso_real[cid]),
            "restrita": restrita[cid],
            "categorias": list(c.get("categorias") or []),
        })
    for categoria, valor in demanda.items():
        no = {"id": f"cat:{categoria}", "nome": categoria, "tipo": "categoria", "valor": _reais(valor)}
        if categoria in nao_coberto:
            no["faltam"] = _reais(nao_coberto[categoria])
        nos.append(no)

    resposta = {
        "status": "sucesso" if not nao_coberto else "gargalo",
        "total_despesas": _reais(total),
        "beneficio_total": round(ganho / ESCALA_CUSTO, 2) + 0.0,
        "plano": plano,
        "nos": nos,
        "arestas": [
            {"origem": f"conta:{p['conta_id']}", "destino": f"cat:{p['categoria']}", "valor": p["valor"]}
            for p in plano
        ],
    }

    if nao_coberto:
        partes = []
        for categoria, falta in nao_coberto.items():
            ninguem = not any(categoria in aceitas[c["id"]] for c in contas)
            partes.append(f"{categoria} (faltam {_brl(falta)}"
                          + ("; nenhuma conta cadastrada aceita essa categoria)" if ninguem else ")"))
        resposta["nao_coberto"] = {cat: _reais(v) for cat, v in nao_coberto.items()}
        resposta["falta"] = _reais(sum(nao_coberto.values()))
        resposta["mensagem"] = ("Gargalo detectado! Não dá para pagar tudo com os limites e as categorias atuais: "
                                + "; ".join(partes) + ". Revise os limites ou as categorias aceitas por cada conta.")
    return resposta
