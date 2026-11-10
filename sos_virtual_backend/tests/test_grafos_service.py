"""
testes do otimizador de pagamentos (servicos/grafos_service.py)
rodar: py -m pytest tests/test_grafos_service.py -v   (dentro de sos_virtual_backend)
a checagem contra programacao linear so roda se o scipy estiver instalado (pip install scipy)
"""
import random

import pytest

from servicos.grafos_service import BONUS_PRIORIDADE, calcular_roteamento_otimizado as otimizar


def conta(id, nome, capacidade=None, custo=0, categorias=None):
    return {"id": id, "nome": nome, "capacidade": capacidade, "custo": custo, "categorias": categorias or []}


def pago_por(resultado, nome, categoria=None):
    return round(sum(p["valor"] for p in resultado["plano"]
                     if p["conta"] == nome and (categoria is None or p["categoria"] == categoria)), 2)


def usado(resultado, nome):
    return next(n["usado"] for n in resultado["nos"] if n["tipo"] == "conta" and n["nome"] == nome)


VALE = lambda cap=800: conta(1, "Vale Alimentação", cap, 0, ["Alimentação"])
CORRENTE = lambda cap=None: conta(2, "Conta Corrente", cap)


# ------------------------------------------------------------ vales (contas restritas)
def test_vale_alimentacao_paga_a_comida_primeiro():
    r = otimizar([VALE(), CORRENTE()], {"Alimentação": 1400, "Moradia": 1600})
    assert r["status"] == "sucesso"
    assert pago_por(r, "Vale Alimentação", "Alimentação") == 800
    assert pago_por(r, "Conta Corrente", "Alimentação") == 600
    assert pago_por(r, "Conta Corrente", "Moradia") == 1600


def test_resultado_nao_depende_da_ordem_de_cadastro_das_contas():
    despesas = {"Alimentação": 1400, "Moradia": 1600}
    a = otimizar([VALE(), CORRENTE()], despesas)
    b = otimizar([CORRENTE(), VALE()], despesas)
    assert pago_por(a, "Vale Alimentação") == pago_por(b, "Vale Alimentação") == 800


def test_vale_nunca_paga_categoria_que_nao_aceita():
    r = otimizar([VALE(5000), CORRENTE()], {"Alimentação": 100, "Moradia": 1600})
    assert pago_por(r, "Vale Alimentação", "Moradia") == 0
    assert pago_por(r, "Vale Alimentação") == 100            # so a comida, mesmo com saldo de sobra


def test_saldo_do_vale_maior_que_a_despesa_nao_e_forcado():
    r = otimizar([VALE(1500), CORRENTE()], {"Alimentação": 1000, "Moradia": 1600})
    assert usado(r, "Vale Alimentação") == 1000             # sobram R$ 500 no vale, que nao paga aluguel
    assert pago_por(r, "Conta Corrente") == 1600


def test_vale_sozinho_nao_paga_aluguel_e_o_gargalo_explica():
    r = otimizar([VALE()], {"Moradia": 700})
    assert r["status"] == "gargalo"
    assert r["nao_coberto"] == {"Moradia": 700.0}
    assert "nenhuma conta cadastrada aceita essa categoria" in r["mensagem"]


def test_vale_sem_despesa_da_categoria_no_mes_fica_sem_uso():
    r = otimizar([VALE(), CORRENTE()], {"Moradia": 1000})
    assert r["status"] == "sucesso" and usado(r, "Vale Alimentação") == 0


def test_dois_vales_na_mesma_categoria_dividem_sem_passar_do_limite():
    r = otimizar([conta(1, "VR", 500, 0, ["Alimentação"]), conta(3, "VA", 500, 0, ["Alimentação"]), CORRENTE()],
                 {"Alimentação": 700})
    assert usado(r, "VR") + usado(r, "VA") == 700 and usado(r, "VR") <= 500 and usado(r, "VA") <= 500
    assert usado(r, "Conta Corrente") == 0


def test_vale_que_aceita_mais_de_uma_categoria():
    multi = conta(1, "Vale Multibenefícios", 1000, 0, ["Alimentação", "Transporte"])
    r = otimizar([multi, CORRENTE()], {"Alimentação": 700, "Transporte": 500, "Moradia": 900})
    assert usado(r, "Vale Multibenefícios") == 1000
    assert pago_por(r, "Vale Multibenefícios", "Moradia") == 0
    assert pago_por(r, "Conta Corrente", "Moradia") == 900


def test_vale_sem_limite_informado_cobre_toda_a_categoria():
    r = otimizar([conta(1, "Cartão corporativo", None, 0, ["Transporte"]), CORRENTE()], {"Transporte": 340, "Lazer": 80})
    assert pago_por(r, "Cartão corporativo", "Transporte") == 340
    assert pago_por(r, "Conta Corrente", "Lazer") == 80


# ------------------------------------ vale + cashback: a regra de prioridade e suas consequencias
def test_vale_e_cartao_com_cashback_cada_um_no_seu_papel():
    cartao = conta(3, "Cartão Cashback", 1000, -2.0)
    r = otimizar([VALE(), cartao, CORRENTE()], {"Alimentação": 1400, "Moradia": 1600})
    assert usado(r, "Vale Alimentação") == 800               # o vale vem primeiro na comida
    assert usado(r, "Cartão Cashback") == 1000               # e o limite do cartao e todo aproveitado
    assert r["beneficio_total"] == 20.0                      # 2% de R$ 1.000


def test_prioridade_do_vale_pode_custar_um_pouco_de_cashback():
    """decisao consciente: com o cartao sem limite, usar o vale (800) reduz o cashback de 60 para 44.
    o saldo do vale e dinheiro que so serve para comida, entao ele e consumido primeiro"""
    cartao = conta(3, "Cartão Cashback", 5000, -2.0)
    r = otimizar([VALE(), cartao], {"Alimentação": 1400, "Moradia": 1600})
    assert usado(r, "Vale Alimentação") == 800
    assert r["beneficio_total"] == 44.0


def test_beneficio_mostrado_usa_o_percentual_real_e_nao_o_bonus_de_prioridade():
    r = otimizar([VALE(), CORRENTE()], {"Alimentação": 1400, "Moradia": 1600})
    assert r["beneficio_total"] == 0.0
    assert all(p["efeito"] == 0.0 for p in r["plano"])
    assert BONUS_PRIORIDADE < -10_000                        # maior que qualquer percentual real (-100%)


def test_conta_restrita_com_juros_ainda_e_usada_primeiro():
    cartao_taxa = conta(1, "Cartão com taxa", 500, 2.0, ["Lazer"])
    r = otimizar([cartao_taxa, CORRENTE()], {"Lazer": 300})
    assert usado(r, "Cartão com taxa") == 300 and r["beneficio_total"] == -6.0


def test_contas_sem_restricao_continuam_escolhendo_pelo_percentual():
    r = otimizar([conta(1, "Cashback", 1000, -2), conta(2, "Sem benefício", 5000, 0), conta(3, "Com juros", 5000, 3)],
                 {"Moradia": 1600, "Lazer": 400})
    assert usado(r, "Cashback") == 1000 and usado(r, "Com juros") == 0 and r["beneficio_total"] == 20.0


# ------------------------------------------------------------------- gargalos
def test_gargalo_mostra_o_melhor_plano_parcial_e_o_que_ficou_sem_conta():
    r = otimizar([VALE(800), CORRENTE(1000)], {"Alimentação": 2000, "Moradia": 1500})
    assert r["status"] == "gargalo"
    pago = sum(p["valor"] for p in r["plano"])
    assert pago == 1800                                      # tudo o que as contas conseguem pagar
    assert round(sum(r["nao_coberto"].values()), 2) == r["falta"] == 1700.0
    assert usado(r, "Vale Alimentação") == 800               # o vale continua sendo usado no plano parcial
    assert all(n.get("faltam", 0) > 0 for n in r["nos"] if n["id"] in {"cat:" + c for c in r["nao_coberto"]})
    assert all(c in r["mensagem"] for c in r["nao_coberto"])


def test_gargalo_por_limite_total_continua_igual():
    r = otimizar([conta(1, "A", 1000), conta(2, "B", 500)], {"Moradia": 1800})
    assert r["status"] == "gargalo" and r["falta"] == 300.0 and "Faltam" not in r["mensagem"] or "300,00" in r["mensagem"]


def test_gargalo_em_uma_categoria_nao_atrapalha_o_pagamento_das_outras():
    r = otimizar([VALE(800), CORRENTE(2000)], {"Alimentação": 700, "Moradia": 5000})
    assert r["status"] == "gargalo" and list(r["nao_coberto"]) == ["Moradia"]
    assert pago_por(r, "Vale Alimentação", "Alimentação") == 700


# ------------------------------------------------------------------- entradas
def test_sem_contas_e_sem_despesas():
    assert otimizar([], {"Moradia": 10})["status"] == "vazio"
    assert otimizar([VALE()], {})["status"] == "vazio"
    assert otimizar([VALE()], {"Moradia": 0})["status"] == "vazio"


def test_categoria_aceita_que_nao_existe_nas_despesas_e_ignorada():
    r = otimizar([conta(1, "Conta", 500, 0, ["Inventada", "Alimentação"])], {"Alimentação": 100})
    assert r["status"] == "sucesso" and usado(r, "Conta") == 100


def test_centavos_exatos():
    r = otimizar([conta(1, "A", 100.10, -1.5, ["Lazer"]), CORRENTE()], {"Lazer": 100.10, "Moradia": 0.07})
    assert r["status"] == "sucesso" and r["total_despesas"] == 100.17 and usado(r, "A") == 100.10


# ---------------------------- confere o otimo contra programacao linear (so com scipy instalado)
def _casos_aleatorios(n, semente):
    rnd = random.Random(semente)
    cats = ["Alimentação", "Transporte", "Saúde", "Lazer", "Moradia", "Educação"]
    for _ in range(n):
        contas = []
        for i in range(rnd.randint(1, 5)):
            restrita = rnd.random() < 0.45
            contas.append(conta(i + 1, f"C{i}", rnd.choice([None, round(rnd.uniform(50, 3500), 2)]),
                                rnd.choice([0, -0.5, -1.5, -2.25, 1, 2.5, 3.99]),
                                rnd.sample(cats, rnd.randint(1, 3)) if restrita else None))
        yield contas, {c: round(rnd.uniform(10, 2500), 2) for c in rnd.sample(cats, rnd.randint(1, 6))}


def test_otimo_igual_ao_da_programacao_linear_com_restricoes():
    np = pytest.importorskip("numpy")
    linprog = pytest.importorskip("scipy.optimize").linprog

    for contas, despesas in _casos_aleatorios(500, 21):
        r = otimizar(contas, despesas)
        cats = list(despesas)
        d = [round(despesas[c] * 100) for c in cats]
        total = sum(d)
        cap = [total if c["capacidade"] is None else round(c["capacidade"] * 100) for c in contas]
        peso = [round(c["custo"] * 100) + (BONUS_PRIORIDADE if c["categorias"] else 0) for c in contas]
        pares = [(i, j) for i, c in enumerate(contas) for j, cat in enumerate(cats) if not c["categorias"] or cat in c["categorias"]]

        def restricoes():
            A_ub, b_ub = np.zeros((len(contas), len(pares))), list(cap)
            A_dem = np.zeros((len(cats), len(pares)))
            for k, (i, j) in enumerate(pares):
                A_ub[i, k] = 1
                A_dem[j, k] = 1
            return A_ub, b_ub, A_dem

        A_ub, b_ub, A_dem = restricoes()
        lp = linprog([peso[i] for i, _ in pares], A_ub=A_ub, b_ub=b_ub, A_eq=A_dem, b_eq=d, bounds=(0, None), method="highs") if pares else None

        if lp is not None and lp.status == 0:                # tudo pode ser pago
            assert r["status"] == "sucesso", (contas, despesas)
            custo = sum(peso[i] * round(usado(r, contas[i]["nome"]) * 100) for i in range(len(contas)))
            assert abs(custo - lp.fun) <= 1, (contas, despesas, custo, lp.fun)
        else:                                                # gargalo: confere o maximo que da para pagar
            assert r["status"] == "gargalo", (contas, despesas)
            maximo = linprog([-1] * len(pares), A_ub=np.vstack([A_ub, A_dem]), b_ub=b_ub + d, bounds=(0, None), method="highs") if pares else None
            esperado = 0 if maximo is None else round(-maximo.fun)
            assert round(sum(p["valor"] for p in r["plano"]) * 100) == esperado, (contas, despesas)

        # o plano nunca viola limite, categoria aceita nem valor da despesa
        for c in contas:
            assert usado(r, c["nome"]) * 100 <= (total if c["capacidade"] is None else round(c["capacidade"] * 100)) + 1
        for p in r["plano"]:
            dono = next(c for c in contas if c["id"] == p["conta_id"])
            assert not dono["categorias"] or p["categoria"] in dono["categorias"]
        for cat in cats:
            assert sum(p["valor"] for p in r["plano"] if p["categoria"] == cat) <= despesas[cat] + 0.005


# ------------------------------------------- compras ja registradas em uma conta (fixos)
def fixo(conta_id, categoria, valor):
    return {"conta_id": conta_id, "categoria": categoria, "valor": valor}


def registrado_em(resultado, nome):
    return next(n["usado_registrado"] for n in resultado["nos"] if n["tipo"] == "conta" and n["nome"] == nome)


def test_o_que_ja_foi_pago_consome_o_limite_da_conta():
    cartao = conta(3, "Cartão Cashback", 1000, -2.0)
    r = otimizar([cartao, CORRENTE()], {"Moradia": 1600}, fixos=[fixo(3, "Alimentação", 400)])
    assert registrado_em(r, "Cartão Cashback") == 400
    assert pago_por(r, "Cartão Cashback", "Moradia") == 600            # so sobraram R$ 600 do limite de R$ 1.000
    assert usado(r, "Cartão Cashback") == 1000 and pago_por(r, "Conta Corrente") == 1000


def test_beneficio_separa_registrado_e_sugerido():
    r = otimizar([conta(3, "Cartão Cashback", 1000, -2.0), CORRENTE()], {"Moradia": 1600}, fixos=[fixo(3, "Alimentação", 400)])
    assert r["beneficio_registrado"] == 8.0 and r["beneficio_sugerido"] == 12.0 and r["beneficio_total"] == 20.0


def test_totais_somam_o_registrado_e_o_pendente():
    r = otimizar([conta(3, "Cartão", 5000), CORRENTE()], {"Moradia": 1600}, fixos=[fixo(3, "Alimentação", 400), fixo(3, "Lazer", 100)])
    assert (r["total_registrado"], r["total_pendente"], r["total_despesas"]) == (500.0, 1600.0, 2100.0)


def test_so_compras_registradas_nada_a_sugerir():
    r = otimizar([conta(3, "Cartão", 5000, -1.0)], {}, fixos=[fixo(3, "Alimentação", 400)])
    assert r["status"] == "sucesso" and r["plano"] == [] and r["beneficio_total"] == 4.0
    assert r["registrados"][0]["conta"] == "Cartão" and "já estão registradas" in r["mensagem"]


def test_nenhuma_despesa_continua_vazio():
    assert otimizar([CORRENTE()], {}, fixos=[])["status"] == "vazio"


def test_vale_com_parte_do_saldo_ja_usada():
    r = otimizar([VALE(800), CORRENTE()], {"Alimentação": 1000}, fixos=[fixo(1, "Alimentação", 300)])
    assert pago_por(r, "Vale Alimentação", "Alimentação") == 500       # os R$ 300 ja pagos saem do saldo de R$ 800
    assert pago_por(r, "Conta Corrente", "Alimentação") == 500
    assert usado(r, "Vale Alimentação") == 800


def test_conta_que_passou_do_limite_nao_recebe_mais_nada_e_e_sinalizada():
    r = otimizar([conta(3, "Cartão", 500, -2.0), CORRENTE()], {"Moradia": 1000}, fixos=[fixo(3, "Lazer", 700)])
    assert r["excedeu_limite"] == [{"conta": "Cartão", "excedeu": 200.0}]
    assert r["status"] == "sucesso" and pago_por(r, "Cartão") == 0 and pago_por(r, "Conta Corrente") == 1000


def test_compra_fora_das_categorias_do_vale_e_respeitada_e_avisada():
    r = otimizar([VALE(800), CORRENTE()], {"Moradia": 100}, fixos=[fixo(1, "Moradia", 150)])
    assert r["fora_da_regra"] == [{"conta": "Vale Alimentação", "categoria": "Moradia", "valor": 150.0}]
    assert r["registrados"][0]["categoria"] == "Moradia"               # a realidade manda: nao e apagada nem recusada


def test_conta_sem_limite_com_compras_registradas():
    r = otimizar([conta(3, "Cartão", None, -1.0)], {"Lazer": 200}, fixos=[fixo(3, "Alimentação", 300)])
    assert r["status"] == "sucesso" and registrado_em(r, "Cartão") == 300 and pago_por(r, "Cartão", "Lazer") == 200


def test_compra_em_conta_que_nao_existe_mais_e_ignorada():
    r = otimizar([CORRENTE()], {"Moradia": 100}, fixos=[fixo(99, "Lazer", 500)])
    assert r["total_registrado"] == 0.0 and r["status"] == "sucesso"


def test_gargalo_considera_o_que_ja_foi_pago():
    r = otimizar([conta(3, "Cartão", 1000)], {"Moradia": 500}, fixos=[fixo(3, "Lazer", 900)])
    assert r["status"] == "gargalo" and r["falta"] == 400.0 and "ainda está sem conta" in r["mensagem"]


def test_arestas_marcam_se_sao_registradas_ou_sugeridas():
    r = otimizar([conta(3, "Cartão", 5000), CORRENTE()], {"Moradia": 100}, fixos=[fixo(3, "Lazer", 50)])
    assert {a["tipo"] for a in r["arestas"]} == {"registrado", "sugerido"}
    lazer = next(n for n in r["nos"] if n["id"] == "cat:Lazer")
    assert (lazer["registrado"], lazer["pendente"], lazer["valor"]) == (50.0, 0.0, 50.0)
    moradia = next(n for n in r["nos"] if n["id"] == "cat:Moradia")
    assert (moradia["registrado"], moradia["pendente"]) == (0.0, 100.0)


def test_registrar_e_sugerir_equivale_a_reduzir_o_limite():
    """a sugestao com compras ja registradas e igual a otimizar com o limite ja reduzido (que ja foi validado contra programacao linear)"""
    rnd = random.Random(5)
    cats = ["Alimentação", "Transporte", "Saúde", "Lazer", "Moradia"]
    for _ in range(200):
        contas = [conta(i + 1, f"C{i}", rnd.choice([None, round(rnd.uniform(500, 3000), 2)]), rnd.choice([0, -1, -2, 1.5]),
                        rnd.sample(cats, rnd.randint(1, 2)) if rnd.random() < 0.4 else None) for i in range(rnd.randint(1, 4))]
        despesas = {c: round(rnd.uniform(10, 900), 2) for c in rnd.sample(cats, rnd.randint(1, 4))}
        fixos = [fixo(rnd.choice(contas)["id"], rnd.choice(cats), round(rnd.uniform(10, 300), 2)) for _ in range(rnd.randint(0, 4))]
        com_fixos = otimizar(contas, despesas, fixos)
        gasto = {}
        for f in fixos:
            gasto[f["conta_id"]] = gasto.get(f["conta_id"], 0) + f["valor"]
        reduzidas = [{**c, "capacidade": None if c["capacidade"] is None else max(0, round(c["capacidade"] - gasto.get(c["id"], 0), 2))} for c in contas]
        sem_fixos = otimizar(reduzidas, despesas)
        assert com_fixos["status"] == sem_fixos["status"]
        assert sorted((p["conta_id"], p["categoria"], p["valor"]) for p in com_fixos["plano"]) == sorted((p["conta_id"], p["categoria"], p["valor"]) for p in sem_fixos["plano"])
        assert com_fixos["beneficio_sugerido"] == sem_fixos["beneficio_total"]
