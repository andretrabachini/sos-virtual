"""
testes da API: compra em uma conta/cartao, data da compra, escolha do mes e grafo com compras registradas
rodar: py -m pytest tests/test_api_contas_e_meses.py -v   (banco SQLite em memoria; veja conftest.py)
"""
import io

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
    return c.post("/api/transacoes", headers=h, json={"descricao": descricao, "valor": valor, **extra})


def conta(c, h, nome, **extra):
    r = c.post("/api/contas", headers=h, json={"nome": nome, **extra})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


# ------------------------------------------------------------------- compra em uma conta
def test_compra_em_conta_existente_guarda_e_mostra_a_conta(cliente, ana):
    itau = conta(cliente, ana, "Cartão Itaú")
    r = gasto(cliente, ana, conta="Cartão Itaú")
    assert r.status_code == 201 and r.get_json()["conta"] == "Cartão Itaú" and r.get_json()["conta_id"] == itau["id"]
    assert cliente.get("/api/transacoes", headers=ana).get_json()[0]["conta"] == "Cartão Itaú"


def test_compra_sem_conta_continua_sem_conta(cliente, ana):
    r = gasto(cliente, ana).get_json()
    assert r["conta"] is None and r["conta_id"] is None
    assert gasto(cliente, ana, conta="").get_json()["conta"] is None


def test_conta_nova_digitada_na_compra_e_criada(cliente, ana):
    assert gasto(cliente, ana, conta="Cartão Novo").status_code == 201
    assert [c["nome"] for c in cliente.get("/api/contas", headers=ana).get_json()] == ["Cartão Novo"]


def test_receita_nao_guarda_conta(cliente, ana):
    conta(cliente, ana, "Cartão Itaú")
    assert gasto(cliente, ana, "salário", 3000, conta="Cartão Itaú").get_json()["conta"] is None


@pytest.mark.parametrize("nome", [5, ["x"], "c" * 101, {"a": 1}])
def test_nome_de_conta_invalido(cliente, ana, nome):
    assert gasto(cliente, ana, conta=nome).status_code == 400


def test_limite_de_20_contas_tambem_vale_ao_criar_pela_compra(cliente, ana):
    for i in range(20):
        conta(cliente, ana, f"C{i}")
    r = gasto(cliente, ana, conta="Conta 21")
    assert r.status_code == 400 and "limite" in r.get_json()["erro"]
    assert gasto(cliente, ana, conta="C3").status_code == 201
    assert cliente.get("/api/transacoes", headers=ana).get_json()[0]["conta"] == "C3"


def test_conta_de_outro_usuario_nao_e_usada(cliente, ana):
    r = cliente.post("/api/auth/cadastro", json={"nome": "Bia Teste", "email": "b@x.com", "senha": "senha1234", "lgpd_aceito": True})
    bia = {"Authorization": "Bearer " + r.get_json()["token"]}
    conta(cliente, bia, "Cartão da Bia")
    gasto(cliente, ana, conta="Cartão da Bia")                                        # para a Ana, esse nome cria uma conta dela
    assert [c["nome"] for c in cliente.get("/api/contas", headers=ana).get_json()] == ["Cartão da Bia"]
    assert cliente.get("/api/contas", headers=ana).get_json()[0]["id"] != cliente.get("/api/contas", headers=bia).get_json()[0]["id"]


# ----------------------------------------------------------------------- regra do vale
def test_vale_so_aceita_as_categorias_dele(cliente, ana):
    conta(cliente, ana, "Vale Alimentação", categorias=["Alimentação"])
    r = gasto(cliente, ana, "aluguel", -800, conta="Vale Alimentação")
    assert r.status_code == 400 and "só paga: Alimentação" in r.get_json()["erro"]
    assert gasto(cliente, ana, "mercado", -80, conta="Vale Alimentação").status_code == 201


def test_vale_recusa_tambem_pela_categoria_detectada_automaticamente(cliente, ana):
    conta(cliente, ana, "Vale Alimentação", categorias=["Alimentação"])
    assert gasto(cliente, ana, "ifood pizza", -50, conta="Vale Alimentação").status_code == 400      # restaurante nao e mercado
    conta(cliente, ana, "Vale Refeição", categorias=["Restaurante"])
    assert gasto(cliente, ana, "ifood pizza", -50, conta="Vale Refeição").status_code == 201


def test_compra_recusada_nao_deixa_nada_para_tras(cliente, ana):
    conta(cliente, ana, "Vale", categorias=["Alimentação"])
    gasto(cliente, ana, "aluguel", -800, conta="Vale")
    assert cliente.get("/api/transacoes", headers=ana).get_json() == []


def test_regra_do_vale_na_edicao(cliente, ana):
    conta(cliente, ana, "Vale", categorias=["Alimentação"])
    tid = gasto(cliente, ana, "mercado", -80, conta="Vale").get_json()["id"]
    assert cliente.put(f"/api/transacoes/{tid}", headers=ana, json={"categoria": "Moradia"}).status_code == 400
    assert cliente.put(f"/api/transacoes/{tid}", headers=ana, json={"conta": "Vale", "categoria": "Alimentação"}).status_code == 200


def test_editar_so_a_descricao_nao_esbarra_na_regra_de_uma_conta_restringida_depois(cliente, ana):
    c = conta(cliente, ana, "Cartão X")
    tid = gasto(cliente, ana, "aluguel", -800, conta="Cartão X").get_json()["id"]
    cliente.put(f"/api/contas/{c['id']}", headers=ana, json={"categorias": ["Alimentação"]})     # passou a ser vale depois da compra
    assert cliente.put(f"/api/transacoes/{tid}", headers=ana, json={"descricao": "aluguel de outubro"}).status_code == 200


# ----------------------------------------------------------------- trocar a conta depois
def test_trocar_e_tirar_a_conta_de_uma_compra(cliente, ana):
    conta(cliente, ana, "Cartão A")
    conta(cliente, ana, "Cartão B")
    tid = gasto(cliente, ana, conta="Cartão A").get_json()["id"]
    assert cliente.put(f"/api/transacoes/{tid}", headers=ana, json={"conta": "Cartão B"}).get_json()["conta"] == "Cartão B"
    assert cliente.put(f"/api/transacoes/{tid}", headers=ana, json={"conta": ""}).get_json()["conta"] is None
    assert cliente.put(f"/api/transacoes/{tid}", headers=ana, json={"conta": None}).get_json()["conta"] is None
    assert cliente.put(f"/api/transacoes/{tid}", headers=ana, json={"categoria": "Lazer"}).get_json()["conta"] is None


def test_virar_receita_remove_a_conta(cliente, ana):
    conta(cliente, ana, "Cartão A")
    tid = gasto(cliente, ana, conta="Cartão A").get_json()["id"]
    assert cliente.put(f"/api/transacoes/{tid}", headers=ana, json={"valor": 50}).get_json()["conta"] is None


def test_excluir_a_conta_libera_as_compras_sem_apagar_nada(cliente, ana):
    c = conta(cliente, ana, "Cartão A")
    gasto(cliente, ana, conta="Cartão A")
    assert cliente.delete(f"/api/contas/{c['id']}", headers=ana).status_code == 200
    compras = cliente.get("/api/transacoes", headers=ana).get_json()
    assert len(compras) == 1 and compras[0]["conta"] is None


def test_renomear_a_conta_acompanha_as_compras_parceladas(cliente, ana):
    c = conta(cliente, ana, "Cartão Velho")
    cliente.post("/api/parcelamentos", headers=ana, json={"descricao": "TV", "valor_vista": 600, "parcelas": 3, "conta": "Cartão Velho"})
    cliente.put(f"/api/contas/{c['id']}", headers=ana, json={"nome": "Cartão Novo"})
    assert cliente.get("/api/parcelamentos", headers=ana).get_json()[0]["conta"] == "Cartão Novo"
    assert cliente.get("/api/transacoes", headers=ana).get_json()[0]["conta"] == "Cartão Novo"


# ---------------------------------------------------------------------- data da compra
def test_compra_com_data_antiga_aparece_no_mes_dela(cliente, ana):
    data = hoje() - relativedelta(months=9, day=15)
    r = gasto(cliente, ana, "mercado", -120, data=iso(data))
    assert r.status_code == 201 and r.get_json()["data"].startswith(iso(data))
    mes = data.strftime("%Y-%m")
    assert [t["descricao"] for t in cliente.get("/api/transacoes?mes=" + mes, headers=ana).get_json()] == ["mercado"]
    assert cliente.get("/api/transacoes?mes=" + hoje().strftime("%Y-%m"), headers=ana).get_json() == []


def test_data_de_hoje_guarda_a_hora_e_futura_vale_ate_12_meses(cliente, ana):
    assert gasto(cliente, ana, data=iso(hoje())).get_json()["data"] > iso(hoje()) + "T00:00:00"
    assert gasto(cliente, ana, data=iso(hoje() + relativedelta(months=12))).status_code == 201


@pytest.mark.parametrize("deslocamento", [dict(months=13), dict(years=-6)])
def test_data_fora_do_limite(cliente, ana, deslocamento):
    assert gasto(cliente, ana, data=iso(hoje() + relativedelta(**deslocamento))).status_code == 400


@pytest.mark.parametrize("data", ["ontem", "2026-13-45", 20261023, ["2026-10-01"], "01/10/2026"])
def test_data_invalida(cliente, ana, data):
    assert gasto(cliente, ana, data=data).status_code == 400


def test_gasto_antigo_nao_dispara_alerta_do_mes_atual(cliente, ana):
    cliente.post("/api/alertas", headers=ana, json={"categoria": "Lazer", "limite": 100})
    antigo = iso(hoje() - relativedelta(months=3))
    assert gasto(cliente, ana, "cinema", -500, categoria="Lazer", data=antigo).get_json()["alertas"] == []
    assert len(gasto(cliente, ana, "show", -500, categoria="Lazer").get_json()["alertas"]) == 1


# ------------------------------------------------------------------------ escolher o mes
def test_painel_de_outro_mes(cliente, ana):
    antigo = hoje() - relativedelta(months=4, day=10)
    gasto(cliente, ana, "mercado", -200, data=iso(antigo))
    gasto(cliente, ana, "salário", 3000, data=iso(antigo))
    gasto(cliente, ana, "mercado", -50)
    passado = cliente.get("/api/dashboard?mes=" + antigo.strftime("%Y-%m"), headers=ana).get_json()
    assert passado["mes"] == antigo.strftime("%Y-%m") and passado["despesa_total"] == 200 and passado["receita_total"] == 3000
    assert passado["por_categoria"] == {"Alimentação": 200} and len(passado["transacoes_recentes"]) == 2
    atual = cliente.get("/api/dashboard", headers=ana).get_json()
    assert atual["despesa_total"] == 50 and atual["mes"] == hoje().strftime("%Y-%m")


@pytest.mark.parametrize("mes", ["2026-13", "10/2026", "abc", "1999-12", "2101-01", "2026-1"])
def test_mes_invalido_e_recusado_em_todas_as_telas(cliente, ana, mes):
    for rota in ("/api/dashboard", "/api/alertas", "/api/grafo"):
        assert cliente.get(f"{rota}?mes={mes}", headers=ana).status_code == 400


def test_mes_sem_dados_devolve_zeros(cliente, ana):
    d = cliente.get("/api/dashboard?mes=2020-01", headers=ana).get_json()
    assert d["despesa_total"] == 0 and d["por_categoria"] == {} and d["transacoes_recentes"] == []


def test_alertas_comparam_com_o_gasto_do_mes_escolhido(cliente, ana):
    antigo = hoje() - relativedelta(months=2, day=5)
    cliente.post("/api/alertas", headers=ana, json={"categoria": "Lazer", "limite": 100})
    gasto(cliente, ana, "cinema", -300, categoria="Lazer", data=iso(antigo))
    do_mes = cliente.get("/api/alertas?mes=" + antigo.strftime("%Y-%m"), headers=ana).get_json()[0]
    assert do_mes["gasto_atual"] == 300 and do_mes["disparado"] is True
    atual = cliente.get("/api/alertas", headers=ana).get_json()[0]
    assert atual["gasto_atual"] == 0 and atual["disparado"] is False


# --------------------------------------------------------------- grafo com compras registradas
def test_caso_do_cartao_meli_compra_parcelada_aparece_como_usada(cliente, ana):
    """compra parcelada no Cartão Meli: o cartao deve aparecer USADO no caminho do dinheiro (antes aparecia 'não usada')"""
    conta(cliente, ana, "Cartão Meli", capacidade=2000, custo=-1)
    r = cliente.post("/api/parcelamentos", headers=ana, json={"descricao": "Strap Academia", "valor_vista": 50, "parcelas": 2, "categoria": "Saúde", "conta": "Cartão Meli"})
    assert r.status_code == 201
    g = cliente.get("/api/grafo", headers=ana).get_json()
    meli = next(n for n in g["nos"] if n["nome"] == "Cartão Meli")
    assert meli["usado_registrado"] == 25.0 and meli["usado"] == 25.0
    assert g["registrados"] == [{"conta_id": meli["id"].split(":")[1] and int(meli["id"].split(":")[1]), "conta": "Cartão Meli", "categoria": "Saúde", "valor": 25.0, "efeito": 0.25}]
    assert g["beneficio_registrado"] == 0.25 and g["total_registrado"] == 25.0


def test_so_o_que_esta_sem_conta_e_sugerido(cliente, ana):
    conta(cliente, ana, "Cartão Cashback", capacidade=1000, custo=-2)
    conta(cliente, ana, "Conta Corrente")
    gasto(cliente, ana, "mercado", -400, conta="Cartão Cashback")
    gasto(cliente, ana, "aluguel", -1600)
    g = cliente.get("/api/grafo", headers=ana).get_json()
    assert g["registradas"] == {"Alimentação": 400.0} and g["pendentes"] == {"Moradia": 1600.0}
    sugerido = {(p["conta"], p["categoria"]): p["valor"] for p in g["plano"]}
    assert sugerido[("Cartão Cashback", "Moradia")] == 600.0               # o limite de R$ 1.000 menos os R$ 400 ja usados
    assert g["beneficio_registrado"] == 8.0 and g["beneficio_sugerido"] == 12.0 and g["beneficio_total"] == 20.0


def test_grafo_de_outro_mes_usa_as_compras_daquele_mes(cliente, ana):
    conta(cliente, ana, "Cartão", capacidade=1000)
    antigo = hoje() - relativedelta(months=3, day=8)
    gasto(cliente, ana, "mercado", -300, conta="Cartão", data=iso(antigo))
    do_mes = cliente.get("/api/grafo?mes=" + antigo.strftime("%Y-%m"), headers=ana).get_json()
    assert do_mes["mes"] == antigo.strftime("%Y-%m") and do_mes["total_registrado"] == 300.0
    assert cliente.get("/api/grafo", headers=ana).get_json()["status"] == "vazio"


def test_simulacao_mantem_o_registrado_e_troca_so_o_pendente(cliente, ana):
    conta(cliente, ana, "Cartão", capacidade=1000)
    gasto(cliente, ana, "mercado", -400, conta="Cartão")
    g = cliente.post("/api/grafo/otimizar", headers=ana, json={"despesas": {"Lazer": 200}}).get_json()
    assert g["total_registrado"] == 400.0 and g["total_pendente"] == 200.0 and g["total_despesas"] == 600.0
    assert cliente.post("/api/grafo/otimizar", headers=ana, json={"mes": "abc"}).status_code == 400


def test_compra_alem_do_limite_da_conta_e_sinalizada(cliente, ana):
    conta(cliente, ana, "Cartão", capacidade=300)
    gasto(cliente, ana, "mercado", -500, conta="Cartão")
    g = cliente.get("/api/grafo", headers=ana).get_json()
    assert g["excedeu_limite"] == [{"conta": "Cartão", "excedeu": 200.0}]


# ------------------------------------------------------------------ importacao e parcelas
def importar(c, h, csv, conta_nome):
    return c.post("/api/simulacoes/importar-extrato", headers=h, content_type="multipart/form-data",
                  data={"arquivo": (io.BytesIO(csv.encode()), "e.csv"), "conta": conta_nome})


def test_importacao_grava_a_conta_nas_despesas_e_nao_nas_receitas(cliente, ana):
    hoje_br = hoje().strftime("%d/%m/%Y")
    r = importar(cliente, ana, f"Data;Histórico;Valor\n{hoje_br};MERCADO;-50,00\n{hoje_br};SALARIO;3.000,00\n", "Cartão Itaú")
    assert r.status_code == 201
    contas = {t["descricao"]: t["conta"] for t in cliente.get("/api/transacoes", headers=ana).get_json()}
    assert contas == {"MERCADO": "Cartão Itaú", "SALARIO": None}


def test_importar_extrato_de_vale_avisa_o_que_esta_fora_da_regra(cliente, ana):
    conta(cliente, ana, "Vale Alimentação", categorias=["Alimentação"])
    hoje_br = hoje().strftime("%d/%m/%Y")
    r = importar(cliente, ana, f"Data;Histórico;Valor\n{hoje_br};MERCADO;-50,00\n{hoje_br};ALUGUEL;-800,00\n", "Vale Alimentação").get_json()
    assert r["importadas"] == 2 and r["fora_da_regra"] == {"Moradia": 1}        # importa mesmo assim (o extrato manda) e avisa


def test_primeira_parcela_de_compra_parcelada_guarda_a_conta(cliente, ana):
    cliente.post("/api/parcelamentos", headers=ana, json={"descricao": "Notebook", "valor_vista": 1000, "parcelas": 4, "conta": "Cartão Meli"})
    assert [t["conta"] for t in cliente.get("/api/transacoes", headers=ana).get_json()] == ["Cartão Meli"]


def test_vale_recusa_compra_parcelada_de_outra_categoria(cliente, ana):
    conta(cliente, ana, "Vale Alimentação", categorias=["Alimentação"])
    r = cliente.post("/api/parcelamentos", headers=ana, json={"descricao": "Notebook", "valor_vista": 1000, "parcelas": 4, "conta": "Vale Alimentação"})
    assert r.status_code == 400 and "só paga" in r.get_json()["erro"]


def test_exportar_inclui_a_conta_de_cada_compra(cliente, ana):
    gasto(cliente, ana, conta="Cartão Itaú")
    exportado = cliente.get("/api/auth/meus-dados", headers=ana).get_json()
    assert exportado["transacoes"][0]["conta"] == "Cartão Itaú"
