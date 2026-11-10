"""
roteamento otimizado de pagamentos com grafos (fluxo de custo minimo)

o grafo tem 4 camadas:
    S (super fonte) -> contas/cartoes -> categorias de despesa -> T (super sumidouro)

- S -> conta:         capacidade = quanto a conta consegue pagar no mes (limite do cartao, saldo do vale)
                      custo = % por R$ pago (negativo = cashback/beneficio, positivo = juros/taxa)
- conta -> categoria: so existe se a conta ACEITA a categoria. conta sem restricao aceita todas;
                      conta restrita (ex.: Vale Alimentação so paga "Alimentação") so as escolhidas
- categoria -> T:     capacidade = valor da despesa, que precisa ser paga por inteiro

dois tipos de despesa
- REGISTRADA: a compra ja foi lancada em uma conta ou cartao (fixos). Isso e um fato: aparece no grafo como
  esta, e consome o limite da conta
- PENDENTE: ainda sem conta definida (despesas). So essa parte e otimizada, com o que sobrou do limite de cada conta

regra dos vales: uma conta restrita guarda dinheiro que NAO serve para o resto (o saldo do vale
nao paga o aluguel), entao ela e usada PRIMEIRO nas categorias que aceita. isso e feito somando um
bonus enorme ao peso dela, maior que qualquer cashback ou juros real. o bonus entra so no calculo:
os valores mostrados ao usuario (beneficio, efeito) usam sempre o percentual verdadeiro

o algoritmo (network simplex, do networkx) trabalha melhor com numeros INTEIROS. por isso tudo roda em
centavos, e o custo em "centesimos de ponto percentual por centavo" (1,5% -> 150)
"""
from collections import defaultdict

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


def calcular_roteamento_otimizado(contas, despesas, fixos=None):
    """
    :param contas: lista de dicts {"id", "nome", "capacidade" (R$ ou None = sem limite),
                   "custo" (%), "categorias" (lista de categorias aceitas; vazia/None = todas)}
    :param despesas: dict {categoria: valor em R$} - o que ainda esta SEM conta e precisa ser distribuido
    :param fixos: opcional, lista de {"conta_id", "categoria", "valor"} - compras ja registradas em uma conta
    :return: dict com status "sucesso", "gargalo" ou "vazio" (nunca levanta erro de negocio).
             no gargalo vem tambem o melhor plano parcial e o que ficou sem conta (nao_coberto)
    """
    ids = {c["id"] for c in contas}

    # ---- o que ja foi pago em cada conta (fatos), em centavos
    fixo_conta, fixo_cat, fixo_par = defaultdict(int), defaultdict(int), defaultdict(int)
    for f in fixos or []:
        valor = _centavos(f["valor"])
        if valor <= 0 or f["conta_id"] not in ids:
            continue
        fixo_conta[f["conta_id"]] += valor
        fixo_cat[f["categoria"]] += valor
        fixo_par[(f["conta_id"], f["categoria"])] += valor

    # ---- o que falta distribuir
    demanda = {}
    for categoria, valor in despesas.items():
        centavos = _centavos(valor)
        if centavos > 0:
            demanda[categoria] = centavos

    if not contas:
        return {"status": "vazio", "mensagem": "Cadastre pelo menos uma conta ou cartão para calcular."}
    if not demanda and not fixo_cat:
        return {"status": "vazio", "mensagem": "Não há despesas para distribuir."}

    total_pendente = sum(demanda.values())
    total_fixo = sum(fixo_conta.values())

    capacidade, restrita, aceitas, peso_real, peso_modelo = {}, {}, {}, {}, {}
    for c in contas:
        cid = c["id"]
        # conta sem limite informado: pode pagar qualquer valor (limitada so pelo que falta distribuir);
        # conta com limite: o que ja foi pago nela sai do limite
        capacidade[cid] = total_pendente if c.get("capacidade") is None else max(0, _centavos(c["capacidade"]) - fixo_conta[cid])
        escolhidas = c.get("categorias") or []
        restrita[cid] = bool(escolhidas)
        aceitas[cid] = [cat for cat in demanda if (not escolhidas or cat in escolhidas)]
        peso_real[cid] = _peso(c.get("custo"))
        peso_modelo[cid] = peso_real[cid] + (BONUS_PRIORIDADE if restrita[cid] else 0)

    # ---------- resolve so a parte pendente ----------
    fluxo, nao_coberto = {"S": {}}, {}
    if demanda:
        G = nx.DiGraph()
        G.add_node("S", demand=-total_pendente)   # injeta o dinheiro
        G.add_node("T", demand=total_pendente)    # consome o dinheiro

        no_conta = {c["id"]: f"conta:{c['id']}" for c in contas}
        for c in contas:                          # camada 1: fonte -> contas (o beneficio/custo e cobrado aqui)
            G.add_edge("S", no_conta[c["id"]], capacity=capacidade[c["id"]], weight=peso_modelo[c["id"]])
        for c in contas:                          # camada 2: contas -> categorias que elas aceitam
            for categoria in aceitas[c["id"]]:
                G.add_edge(no_conta[c["id"]], f"cat:{categoria}", capacity=demanda[categoria], weight=0)
        for categoria, valor in demanda.items():  # camada 3: categorias -> sumidouro (cada despesa e paga por inteiro)
            G.add_edge(f"cat:{categoria}", "T", capacity=valor, weight=0)

        try:
            _, fluxo = nx.network_simplex(G)
        except nx.NetworkXUnfeasible:
            # nao da para pagar tudo: calcula o melhor que as contas conseguem (maximo pago, com o menor custo)
            # e descobre o que ficou sem conta, para explicar ao usuario onde esta o gargalo
            fluxo = nx.max_flow_min_cost(G, "S", "T")
            nao_coberto = {
                cat: demanda[cat] - fluxo[f"cat:{cat}"].get("T", 0)
                for cat in demanda if demanda[cat] - fluxo[f"cat:{cat}"].get("T", 0) > 0
            }

    # ---------- monta a resposta ----------
    plano, registrados, nos, fora_da_regra, excedeu = [], [], [], [], []
    ganho_registrado = ganho_sugerido = 0       # em unidades de ESCALA_CUSTO, com o percentual REAL de cada conta
    for c in contas:
        cid, origem = c["id"], f"conta:{c['id']}"
        sugerido = fluxo["S"].get(origem, 0)
        registrado = fixo_conta[cid]
        ganho_registrado += -registrado * peso_real[cid]
        ganho_sugerido += -sugerido * peso_real[cid]

        for categoria in {k[1] for k in fixo_par if k[0] == cid}:
            valor = fixo_par[(cid, categoria)]
            registrados.append({"conta_id": cid, "conta": c["nome"], "categoria": categoria, "valor": _reais(valor),
                                "efeito": _dinheiro(valor, peso_real[cid])})
            escolhidas = c.get("categorias") or []
            if escolhidas and categoria not in escolhidas:
                fora_da_regra.append({"conta": c["nome"], "categoria": categoria, "valor": _reais(valor)})
        for categoria in demanda:
            valor = fluxo.get(origem, {}).get(f"cat:{categoria}", 0)
            if valor > 0:
                plano.append({"conta_id": cid, "conta": c["nome"], "categoria": categoria, "valor": _reais(valor),
                              "efeito": _dinheiro(valor, peso_real[cid])})

        limite = None if c.get("capacidade") is None else _centavos(c["capacidade"])
        if limite is not None and registrado > limite:
            excedeu.append({"conta": c["nome"], "excedeu": _reais(registrado - limite)})
        nos.append({
            "id": origem, "nome": c["nome"], "tipo": "conta",
            "usado": _reais(registrado + sugerido), "usado_registrado": _reais(registrado), "usado_sugerido": _reais(sugerido),
            "capacidade": None if limite is None else _reais(limite),
            "custo": float(c.get("custo") or 0),
            "efeito": _dinheiro(registrado + sugerido, peso_real[cid]),
            "restrita": restrita[cid], "categorias": list(c.get("categorias") or []),
        })

    todas = set(demanda) | set(fixo_cat)
    for categoria in sorted(todas, key=lambda k: (k not in demanda, k)):
        no = {"id": f"cat:{categoria}", "nome": categoria, "tipo": "categoria",
              "valor": _reais(demanda.get(categoria, 0) + fixo_cat.get(categoria, 0)),
              "registrado": _reais(fixo_cat.get(categoria, 0)), "pendente": _reais(demanda.get(categoria, 0))}
        if categoria in nao_coberto:
            no["faltam"] = _reais(nao_coberto[categoria])
        nos.append(no)

    resposta = {
        "status": "sucesso" if not nao_coberto else "gargalo",
        "total_despesas": _reais(total_pendente + total_fixo),
        "total_registrado": _reais(total_fixo),
        "total_pendente": _reais(total_pendente),
        "beneficio_registrado": round(ganho_registrado / ESCALA_CUSTO, 2) + 0.0,
        "beneficio_sugerido": round(ganho_sugerido / ESCALA_CUSTO, 2) + 0.0,
        "beneficio_total": round((ganho_registrado + ganho_sugerido) / ESCALA_CUSTO, 2) + 0.0,
        "plano": plano,                  # sugestoes, so para o que estava sem conta
        "registrados": registrados,      # o que ja foi pago, por conta
        "fora_da_regra": fora_da_regra,  # compras registradas em categorias que a conta nao aceita (a realidade manda)
        "excedeu_limite": excedeu,       # contas em que o registrado passa do limite informado
        "nos": nos,
        "arestas": (
            [{"origem": f"conta:{r['conta_id']}", "destino": f"cat:{r['categoria']}", "valor": r["valor"], "tipo": "registrado"} for r in registrados]
            + [{"origem": f"conta:{p['conta_id']}", "destino": f"cat:{p['categoria']}", "valor": p["valor"], "tipo": "sugerido"} for p in plano]
        ),
    }
    if not demanda:
        resposta["mensagem"] = "Todas as despesas do mês já estão registradas em uma conta ou cartão."

    if nao_coberto:
        partes = []
        for categoria, falta in nao_coberto.items():
            ninguem = not any(categoria in aceitas[c["id"]] for c in contas)
            partes.append(f"{categoria} (faltam {_brl(falta)}"
                          + ("; nenhuma conta cadastrada aceita essa categoria)" if ninguem else ")"))
        resposta["nao_coberto"] = {cat: _reais(v) for cat, v in nao_coberto.items()}
        resposta["falta"] = _reais(sum(nao_coberto.values()))
        resposta["mensagem"] = ("Gargalo detectado! Não dá para pagar tudo o que ainda está sem conta com os limites e as categorias atuais: "
                                + "; ".join(partes) + ". Revise os limites ou as categorias aceitas por cada conta.")
    return resposta
