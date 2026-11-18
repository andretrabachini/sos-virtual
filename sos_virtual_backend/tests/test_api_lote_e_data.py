"""
testes da API: editar a data de uma compra e atribuir conta a varias compras de uma vez
rodar: py -m pytest tests/test_api_lote_e_data.py -v   (banco SQLite em memoria; veja conftest.py)
"""
import pytest
from dateutil.relativedelta import relativedelta

from servicos.tempo import hoje


def iso(d):
    return d.strftime("%Y-%m-%d")


@pytest.fixture()
def ana(cliente):
    r = cliente.post("/api/auth/cadastro", json={"nome": "Ana Teste", "email": "ana@x.com", "senha": "senha1234", "lgpd_aceito": True})
    return {"Authorization": "Bearer " + r.get_json()["token"]}


def gasto(c, h, descricao="mercado", valor=-50, **extra):
    r = c.post("/api/transacoes", headers=h, json={"descricao": descricao, "valor": valor, **extra})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def lote(c, h, ids, conta):
    return c.put("/api/transacoes/lote", headers=h, json={"ids": ids, "conta": conta})


def contas_de(c, h):
    return {t["descricao"]: t["conta"] for t in c.get("/api/transacoes", headers=h).get_json()}


# ===================================================================== editar a data
def test_trocar_a_data_move_a_compra_de_mes(cliente, ana):
    t = gasto(cliente, ana)
    antiga = hoje() - relativedelta(months=3, day=10)
    r = cliente.put(f"/api/transacoes/{t['id']}", headers=ana, json={"data": iso(antiga)})
    assert r.status_code == 200 and r.get_json()["data"].startswith(iso(antiga))
    assert cliente.get("/api/transacoes?mes=" + hoje().strftime("%Y-%m"), headers=ana).get_json() == []
    assert len(cliente.get("/api/transacoes?mes=" + antiga.strftime("%Y-%m"), headers=ana).get_json()) == 1


def test_editar_para_o_mesmo_dia_mantem_a_hora(cliente, ana):
    t = gasto(cliente, ana)                                         # criada agora: tem hora
    r = cliente.put(f"/api/transacoes/{t['id']}", headers=ana, json={"data": iso(hoje())}).get_json()
    assert r["data"] == t["data"]


def test_data_de_hoje_guarda_a_hora_atual_e_futura_vale_ate_12_meses(cliente, ana):
    t = gasto(cliente, ana, data=iso(hoje() - relativedelta(months=2)))
    assert cliente.put(f"/api/transacoes/{t['id']}", headers=ana, json={"data": iso(hoje())}).get_json()["data"] > iso(hoje()) + "T00:00:00"
    assert cliente.put(f"/api/transacoes/{t['id']}", headers=ana, json={"data": iso(hoje() + relativedelta(months=12))}).status_code == 200


@pytest.mark.parametrize("data", ["ontem", "2026-13-45", 20261023, ["2026-10-01"], "01/10/2026", None])
def test_data_invalida_na_edicao_nao_altera_nada(cliente, ana, data):
    t = gasto(cliente, ana)
    assert cliente.put(f"/api/transacoes/{t['id']}", headers=ana, json={"data": data}).status_code == 400
    assert cliente.get("/api/transacoes", headers=ana).get_json()[0]["data"] == t["data"]


@pytest.mark.parametrize("deslocamento", [dict(months=13), dict(years=-6)])
def test_data_fora_do_limite_na_edicao(cliente, ana, deslocamento):
    t = gasto(cliente, ana)
    assert cliente.put(f"/api/transacoes/{t['id']}", headers=ana, json={"data": iso(hoje() + relativedelta(**deslocamento))}).status_code == 400


def test_mover_uma_despesa_para_o_mes_atual_pode_disparar_o_alerta(cliente, ana):
    cliente.post("/api/alertas", headers=ana, json={"categoria": "Lazer", "limite": 100})
    antiga = gasto(cliente, ana, "cinema", -500, categoria="Lazer", data=iso(hoje() - relativedelta(months=3)))
    assert antiga["alertas"] == []                                  # mes passado: nao conta no limite deste mes
    r = cliente.put(f"/api/transacoes/{antiga['id']}", headers=ana, json={"data": iso(hoje())}).get_json()
    assert len(r["alertas"]) == 1 and r["alertas"][0]["categoria"] == "Lazer"


def test_so_edita_a_data_da_propria_compra(cliente, ana):
    t = gasto(cliente, ana)
    r = cliente.post("/api/auth/cadastro", json={"nome": "Bia Teste", "email": "b@x.com", "senha": "senha1234", "lgpd_aceito": True})
    bia = {"Authorization": "Bearer " + r.get_json()["token"]}
    assert cliente.put(f"/api/transacoes/{t['id']}", headers=bia, json={"data": iso(hoje())}).status_code == 404


# ================================================================ atribuir conta em lote
def test_atribui_a_conta_de_varias_compras_de_uma_vez(cliente, ana):
    ids = [gasto(cliente, ana, f"compra {i}")["id"] for i in range(3)]
    cliente.post("/api/contas", headers=ana, json={"nome": "Cartão Itaú"})
    r = lote(cliente, ana, ids, "Cartão Itaú")
    assert r.status_code == 200 and r.get_json() == {"conta": "Cartão Itaú", "atualizadas": 3, "receitas_ignoradas": 0, "recusadas": [], "nao_encontradas": 0}
    assert set(contas_de(cliente, ana).values()) == {"Cartão Itaú"}


def test_conta_vazia_tira_a_conta_de_todas(cliente, ana):
    ids = [gasto(cliente, ana, f"c{i}", conta="Cartão A")["id"] for i in range(3)]
    r = lote(cliente, ana, ids, "").get_json()
    assert r["conta"] is None and r["atualizadas"] == 3 and set(contas_de(cliente, ana).values()) == {None}


def test_conta_nova_no_lote_e_criada(cliente, ana):
    ids = [gasto(cliente, ana)["id"]]
    assert lote(cliente, ana, ids, "Cartão Novo").status_code == 200
    assert [c["nome"] for c in cliente.get("/api/contas", headers=ana).get_json()] == ["Cartão Novo"]


def test_receitas_sao_ignoradas(cliente, ana):
    d, r_ = gasto(cliente, ana, "mercado"), gasto(cliente, ana, "salário", 3000)
    r = lote(cliente, ana, [d["id"], r_["id"]], "Cartão A").get_json()
    assert r["atualizadas"] == 1 and r["receitas_ignoradas"] == 1
    assert contas_de(cliente, ana) == {"mercado": "Cartão A", "salário": None}


def test_vale_recusa_so_as_compras_de_outra_categoria_e_atualiza_o_resto(cliente, ana):
    cliente.post("/api/contas", headers=ana, json={"nome": "Vale Alimentação", "categorias": ["Alimentação"]})
    boa, ruim = gasto(cliente, ana, "mercado"), gasto(cliente, ana, "aluguel", -800)
    r = lote(cliente, ana, [boa["id"], ruim["id"]], "Vale Alimentação").get_json()
    assert r["atualizadas"] == 1 and r["recusadas"] == [{"id": ruim["id"], "descricao": "aluguel", "categoria": "Moradia"}]
    assert contas_de(cliente, ana) == {"mercado": "Vale Alimentação", "aluguel": None}


def test_nao_toca_nas_compras_de_outra_pessoa(cliente, ana):
    minha = gasto(cliente, ana, "minha")
    r = cliente.post("/api/auth/cadastro", json={"nome": "Bia Teste", "email": "b@x.com", "senha": "senha1234", "lgpd_aceito": True})
    bia = {"Authorization": "Bearer " + r.get_json()["token"]}
    dela = gasto(cliente, bia, "dela")
    resposta = lote(cliente, ana, [minha["id"], dela["id"], 99999], "Cartão A").get_json()
    assert resposta["atualizadas"] == 1 and resposta["nao_encontradas"] == 2
    assert contas_de(cliente, bia) == {"dela": None}
    assert lote(cliente, ana, [dela["id"]], "Cartão A").status_code == 404           # so ids de outra pessoa: nada a fazer


def test_ids_repetidos_contam_uma_vez(cliente, ana):
    t = gasto(cliente, ana)
    assert lote(cliente, ana, [t["id"]] * 5, "Cartão A").get_json()["atualizadas"] == 1


def test_lote_respeita_o_limite_de_contas(cliente, ana):
    for i in range(20):
        cliente.post("/api/contas", headers=ana, json={"nome": f"C{i}"})
    t = gasto(cliente, ana)
    r = lote(cliente, ana, [t["id"]], "Conta 21")
    assert r.status_code == 400 and "limite" in r.get_json()["erro"]
    assert contas_de(cliente, ana) == {"mercado": None}


@pytest.mark.parametrize("corpo", [
    {}, {"conta": "X"}, {"ids": [], "conta": "X"}, {"ids": "1,2", "conta": "X"}, {"ids": [1, "2"], "conta": "X"}, {"ids": [True], "conta": "X"},
    {"ids": [1.5], "conta": "X"}, {"ids": [None], "conta": "X"}, {"ids": [1], "conta": 5}, {"ids": [1], "conta": ["X"]}, {"ids": [1], "conta": "c" * 101},
    {"ids": list(range(1, 202)), "conta": "X"}, {"ids": [1]},
])
def test_pedidos_invalidos_sao_recusados(cliente, ana, corpo):
    gasto(cliente, ana)
    assert cliente.put("/api/transacoes/lote", headers=ana, json=corpo).status_code == 400


def test_lote_com_corpo_quebrado_e_sem_login(cliente, ana):
    assert cliente.put("/api/transacoes/lote", headers=ana, data="isto nao e json", content_type="application/json").status_code == 400
    assert cliente.put("/api/transacoes/lote", json={"ids": [1], "conta": "X"}).status_code == 401


def test_lote_de_200_compras(cliente, ana):
    ids = [gasto(cliente, ana, f"c{i}", -1)["id"] for i in range(200)]
    r = lote(cliente, ana, ids, "Cartão A").get_json()
    assert r["atualizadas"] == 200
