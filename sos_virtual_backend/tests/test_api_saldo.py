"""
testes do saldo que continua de um mes para o outro (/api/saldo, painel e saldo inicial no perfil)
rodar: py -m pytest tests/test_api_saldo.py -v   (banco SQLite em memoria; veja conftest.py)
"""
import pytest
from dateutil.relativedelta import relativedelta

from servicos.tempo import hoje


def mes(delta=0):
    """'AAAA-MM' do mes atual + delta meses"""
    return (hoje().replace(day=1) + relativedelta(months=delta)).strftime("%Y-%m")


def em(delta, dia=10):
    """data (AAAA-MM-DD) no dia `dia` do mes atual + delta meses"""
    return (hoje().replace(day=1) + relativedelta(months=delta, days=dia - 1)).strftime("%Y-%m-%d")


@pytest.fixture()
def ana(cliente):
    r = cliente.post("/api/auth/cadastro", json={"nome": "Ana Teste", "email": "ana@x.com", "senha": "senha1234", "lgpd_aceito": True})
    return {"Authorization": "Bearer " + r.get_json()["token"]}


@pytest.fixture()
def bia(cliente):
    r = cliente.post("/api/auth/cadastro", json={"nome": "Bia Teste", "email": "b@x.com", "senha": "senha1234", "lgpd_aceito": True})
    return {"Authorization": "Bearer " + r.get_json()["token"]}


def lanca(c, h, descricao, valor, data, **extra):
    r = c.post("/api/transacoes", headers=h, json={"descricao": descricao, "valor": valor, "data": data, **extra})
    assert r.status_code == 201, r.get_json()


def saldo(c, h, m=None):
    r = c.get("/api/saldo" + (f"?mes={m}" if m else ""), headers=h)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def perfil(c, h, **campos):
    return c.put("/api/auth/perfil", headers=h, json=campos)


# ============================================================================ o caso do usuario
def test_terminar_novembro_com_1000_comeca_dezembro_com_1000(cliente, ana):
    lanca(cliente, ana, "Salário", 3000, em(-1))
    lanca(cliente, ana, "Despesas do mês", -2000, em(-1, 15))
    anterior, atual = saldo(cliente, ana, mes(-1)), saldo(cliente, ana, mes(0))
    assert (anterior["receita"], anterior["despesa"], anterior["saldo_do_mes"], anterior["saldo_final"]) == (3000, 2000, 1000, 1000)
    assert atual["saldo_anterior"] == 1000 and atual["saldo_do_mes"] == 0 and atual["saldo_final"] == 1000


def test_o_mes_seguinte_soma_o_que_acontece_nele(cliente, ana):
    lanca(cliente, ana, "Salário", 3000, em(-1))
    lanca(cliente, ana, "Despesas", -2000, em(-1))
    lanca(cliente, ana, "Salário", 3500, em(0))
    lanca(cliente, ana, "Aluguel", -1200, em(0))
    s = saldo(cliente, ana)
    assert (s["saldo_anterior"], s["receita"], s["despesa"], s["saldo_do_mes"], s["saldo_final"]) == (1000, 3500, 1200, 2300, 3300)


def test_painel_mostra_o_saldo_anterior_e_final(cliente, ana):
    lanca(cliente, ana, "Salário", 3000, em(-1))
    lanca(cliente, ana, "Despesas", -2000, em(-1))
    lanca(cliente, ana, "Mercado", -300, em(0))
    d = cliente.get("/api/dashboard", headers=ana).get_json()
    assert d["saldo_anterior"] == 1000 and d["saldo"] == -300 and d["saldo_final"] == 700       # "saldo" continua sendo so o do mes
    assert (d["saldo_anterior"], d["saldo_final"]) == (saldo(cliente, ana)["saldo_anterior"], saldo(cliente, ana)["saldo_final"])
    passado = cliente.get(f"/api/dashboard?mes={mes(-1)}", headers=ana).get_json()
    assert passado["saldo_anterior"] == 0 and passado["saldo_final"] == 1000


# ================================================================================ encadeamento
def test_saldo_encadeia_por_varios_meses(cliente, ana):
    lanca(cliente, ana, "a", 500, em(-3))
    lanca(cliente, ana, "b", -200, em(-2))
    lanca(cliente, ana, "c", 100, em(-1))
    assert [saldo(cliente, ana, mes(d))["saldo_anterior"] for d in (-3, -2, -1, 0)] == [0, 500, 300, 400]
    assert [saldo(cliente, ana, mes(d))["saldo_final"] for d in (-3, -2, -1, 0)] == [500, 300, 400, 400]


def test_mes_sem_lancamentos_no_meio_mantem_o_saldo(cliente, ana):
    lanca(cliente, ana, "Salário", 1000, em(-4))
    lanca(cliente, ana, "Compra", -250, em(-1))
    assert [saldo(cliente, ana, mes(d))["saldo_final"] for d in (-4, -3, -2, -1)] == [1000, 1000, 1000, 750]


def test_meses_futuros_continuam_do_ultimo_saldo(cliente, ana):
    lanca(cliente, ana, "Salário", 1000, em(0))
    assert saldo(cliente, ana, mes(3)) == {**saldo(cliente, ana, mes(3)), "saldo_anterior": 1000, "saldo_do_mes": 0, "saldo_final": 1000}


def test_saldo_negativo_tambem_continua(cliente, ana):
    lanca(cliente, ana, "Dívida", -800, em(-1))
    lanca(cliente, ana, "Salário", 300, em(0))
    s = saldo(cliente, ana)
    assert s["saldo_anterior"] == -800 and s["saldo_final"] == -500


def test_virada_de_ano(cliente, ana):
    """o saldo de dezembro passa para janeiro do ano seguinte, em qualquer epoca do ano"""
    base = hoje().replace(month=1, day=1)
    lanca(cliente, ana, "Dezembro", 900, (base - relativedelta(days=20)).strftime("%Y-%m-%d"))
    janeiro = base.strftime("%Y-%m")
    dezembro = (base - relativedelta(months=1)).strftime("%Y-%m")
    assert saldo(cliente, ana, dezembro)["saldo_final"] == 900 and saldo(cliente, ana, janeiro)["saldo_anterior"] == 900


def test_dias_de_virada_de_mes_caem_no_mes_certo(cliente, ana):
    ultimo, primeiro = (hoje().replace(day=1) - relativedelta(days=1)).strftime("%Y-%m-%d"), hoje().replace(day=1).strftime("%Y-%m-%d")
    lanca(cliente, ana, "No ultimo dia", 100, ultimo)
    lanca(cliente, ana, "No primeiro dia", 10, primeiro)
    assert saldo(cliente, ana, mes(-1))["saldo_final"] == 100
    s = saldo(cliente, ana)
    assert s["saldo_anterior"] == 100 and s["receita"] == 10 and s["saldo_final"] == 110


def test_historico_vazio(cliente, ana):
    s = saldo(cliente, ana)
    assert s == {"mes": mes(0), "saldo_anterior": 0, "receita": 0, "despesa": 0, "saldo_do_mes": 0, "saldo_final": 0, "saldo_inicial_informado": False}


def test_soma_sem_erro_de_centavos(cliente, ana):
    for valor in (0.1, 0.2, 0.7):
        lanca(cliente, ana, "x", valor, em(-1))
    assert saldo(cliente, ana)["saldo_anterior"] == 1.0


def test_compras_em_qualquer_conta_ou_sem_conta_contam(cliente, ana):
    cliente.post("/api/contas", headers=ana, json={"nome": "Cartão Itaú"})
    lanca(cliente, ana, "No cartão", -100, em(-1), conta="Cartão Itaú")
    lanca(cliente, ana, "Sem conta", -50, em(-1))
    lanca(cliente, ana, "Salário", 400, em(-1))
    assert saldo(cliente, ana)["saldo_anterior"] == 250


def test_mes_atual_e_o_padrao(cliente, ana):
    lanca(cliente, ana, "x", 10, em(0))
    assert saldo(cliente, ana) == saldo(cliente, ana, mes(0))


def test_cada_usuario_tem_o_proprio_saldo(cliente, ana, bia):
    lanca(cliente, ana, "Ana", 1000, em(-1))
    lanca(cliente, bia, "Bia", 50, em(-1))
    assert saldo(cliente, ana)["saldo_anterior"] == 1000 and saldo(cliente, bia)["saldo_anterior"] == 50


@pytest.mark.parametrize("m", ["2026-13", "2026-00", "10/2026", "abc", "1999-12", "2101-01", "2026-1", "'; DROP TABLE x;--"])
def test_mes_invalido(cliente, ana, m):
    assert cliente.get(f"/api/saldo?mes={m}", headers=ana).status_code == 400


def test_saldo_exige_login(cliente):
    assert cliente.get("/api/saldo").status_code == 401


# =================================================================================== saldo inicial
def test_saldo_inicial_vale_no_inicio_do_mes_informado(cliente, ana):
    assert perfil(cliente, ana, saldo_inicial=3000, saldo_inicial_mes=mes(-2)).status_code == 200
    s = saldo(cliente, ana, mes(-2))
    assert s["saldo_anterior"] == 3000 and s["saldo_final"] == 3000 and s["saldo_inicial_informado"] is True


def test_saldo_inicial_mais_o_que_aconteceu_depois(cliente, ana):
    perfil(cliente, ana, saldo_inicial=3000, saldo_inicial_mes=mes(-2))
    lanca(cliente, ana, "Despesa", -500, em(-2))
    lanca(cliente, ana, "Salário", 2000, em(-1))
    assert [saldo(cliente, ana, mes(d))["saldo_anterior"] for d in (-2, -1, 0)] == [3000, 2500, 4500]


def test_lancamentos_anteriores_ao_saldo_inicial_ficam_de_fora(cliente, ana):
    lanca(cliente, ana, "Antigo", -9999, em(-6))
    perfil(cliente, ana, saldo_inicial=100, saldo_inicial_mes=mes(-2))
    assert saldo(cliente, ana, mes(-1))["saldo_anterior"] == 100          # o -9999 de antes do saldo inicial nao entra


def test_meses_antes_do_saldo_inicial_nao_tem_saldo_anterior_nem_final(cliente, ana):
    lanca(cliente, ana, "Antigo", 700, em(-5))
    perfil(cliente, ana, saldo_inicial=100, saldo_inicial_mes=mes(-2))
    s = saldo(cliente, ana, mes(-5))
    assert s["saldo_anterior"] is None and s["saldo_final"] is None and s["saldo_do_mes"] == 700 and s["receita"] == 700      # o fluxo do mes continua visivel


def test_saldo_inicial_negativo(cliente, ana):
    perfil(cliente, ana, saldo_inicial=-250.5, saldo_inicial_mes=mes(0))
    lanca(cliente, ana, "Salário", 1000, em(0))
    s = saldo(cliente, ana)
    assert s["saldo_anterior"] == -250.5 and s["saldo_final"] == 749.5


def test_painel_com_saldo_inicial_e_mes_anterior_a_ele(cliente, ana):
    perfil(cliente, ana, saldo_inicial=100, saldo_inicial_mes=mes(0))
    d = cliente.get(f"/api/dashboard?mes={mes(-1)}", headers=ana).get_json()
    assert d["saldo_anterior"] is None and d["saldo_final"] is None
    assert cliente.get("/api/dashboard", headers=ana).get_json()["saldo_anterior"] == 100


# ================================================================================ perfil: validacao
def test_perfil_devolve_e_guarda_o_saldo_inicial(cliente, ana):
    r = perfil(cliente, ana, saldo_inicial=1234.567, saldo_inicial_mes="2026-10").get_json()
    assert r["saldo_inicial"] == 1234.57 and r["saldo_inicial_mes"] == "2026-10"
    assert cliente.get("/api/auth/perfil", headers=ana).get_json()["saldo_inicial"] == 1234.57
    login = cliente.post("/api/auth/login", json={"email": "ana@x.com", "senha": "senha1234"}).get_json()["usuario"]
    assert login["saldo_inicial"] == 1234.57 and login["saldo_inicial_mes"] == "2026-10"


def test_usuario_novo_nao_tem_saldo_inicial(cliente, ana):
    p = cliente.get("/api/auth/perfil", headers=ana).get_json()
    assert p["saldo_inicial"] == 0 and p["saldo_inicial_mes"] is None


def test_valor_sem_mes_vale_a_partir_do_mes_atual(cliente, ana):
    r = perfil(cliente, ana, saldo_inicial=500).get_json()
    assert r["saldo_inicial_mes"] == mes(0) and saldo(cliente, ana)["saldo_anterior"] == 500


def test_so_o_mes_mantem_o_valor_e_so_o_valor_mantem_o_mes(cliente, ana):
    perfil(cliente, ana, saldo_inicial=500, saldo_inicial_mes=mes(-3))
    r = perfil(cliente, ana, saldo_inicial_mes=mes(-2)).get_json()
    assert (r["saldo_inicial"], r["saldo_inicial_mes"]) == (500, mes(-2))
    r = perfil(cliente, ana, saldo_inicial=800).get_json()
    assert (r["saldo_inicial"], r["saldo_inicial_mes"]) == (800, mes(-2))


@pytest.mark.parametrize("vazio", [None, ""])
def test_mes_vazio_remove_o_saldo_inicial(cliente, ana, vazio):
    perfil(cliente, ana, saldo_inicial=500, saldo_inicial_mes=mes(-1))
    lanca(cliente, ana, "x", 40, em(-2))
    r = perfil(cliente, ana, saldo_inicial_mes=vazio, saldo_inicial=999).get_json()          # o valor enviado junto e ignorado
    assert (r["saldo_inicial"], r["saldo_inicial_mes"]) == (0, None)
    assert saldo(cliente, ana)["saldo_anterior"] == 40 and saldo(cliente, ana)["saldo_inicial_informado"] is False      # volta a somar desde o inicio


@pytest.mark.parametrize("campos", [
    {"saldo_inicial": "mil"}, {"saldo_inicial": True}, {"saldo_inicial": [1]}, {"saldo_inicial": None}, {"saldo_inicial": 10 ** 12}, {"saldo_inicial": -10 ** 12},
    {"saldo_inicial": 100, "saldo_inicial_mes": "2026-13"}, {"saldo_inicial": 100, "saldo_inicial_mes": "10/2026"}, {"saldo_inicial": 100, "saldo_inicial_mes": 5},
    {"saldo_inicial": 100, "saldo_inicial_mes": "1999-01"}, {"saldo_inicial": 100, "saldo_inicial_mes": ["2026-10"]}, {"saldo_inicial": 100, "saldo_inicial_mes": "2026-1"},
])
def test_saldo_inicial_invalido_e_recusado(cliente, ana, campos):
    assert perfil(cliente, ana, **campos).status_code == 400
    p = cliente.get("/api/auth/perfil", headers=ana).get_json()
    assert p["saldo_inicial"] == 0 and p["saldo_inicial_mes"] is None


def test_pedido_invalido_nao_altera_nenhum_campo(cliente, ana):
    """validar tudo antes de gravar: um saldo ruim nao pode deixar o nome ou a renda pela metade"""
    r = perfil(cliente, ana, nome="Nome Novo", renda_mensal=9000, saldo_inicial="lixo", saldo_inicial_mes=mes(0))
    assert r.status_code == 400
    p = cliente.get("/api/auth/perfil", headers=ana).get_json()
    assert p["nome"] == "Ana Teste" and p["renda_mensal"] == 0
    r = perfil(cliente, ana, nome="Nome Novo", renda_mensal=9000, saldo_inicial=10, saldo_inicial_mes=mes(0))
    p = r.get_json()
    assert r.status_code == 200 and (p["nome"], p["renda_mensal"], p["saldo_inicial"]) == ("Nome Novo", 9000, 10)


def test_alterar_so_o_nome_nao_mexe_no_saldo_inicial(cliente, ana):
    perfil(cliente, ana, saldo_inicial=500, saldo_inicial_mes=mes(-1))
    p = perfil(cliente, ana, nome="Outro Nome").get_json()
    assert (p["saldo_inicial"], p["saldo_inicial_mes"]) == (500, mes(-1))


def test_saldo_inicial_vai_na_exportacao_de_dados(cliente, ana):
    perfil(cliente, ana, saldo_inicial=500, saldo_inicial_mes=mes(-1))
    u = cliente.get("/api/auth/meus-dados", headers=ana).get_json()["usuario"]
    assert u["saldo_inicial"] == 500 and u["saldo_inicial_mes"] == mes(-1)


def test_excluir_a_conta_apaga_tambem_o_saldo_inicial(cliente, ana):
    perfil(cliente, ana, saldo_inicial=500, saldo_inicial_mes=mes(-1))
    assert cliente.delete("/api/auth/conta", headers=ana, json={"senha": "senha1234"}).status_code == 200
    r = cliente.post("/api/auth/cadastro", json={"nome": "Ana Teste", "email": "ana@x.com", "senha": "senha1234", "lgpd_aceito": True})
    assert r.get_json()["usuario"]["saldo_inicial"] == 0 and r.get_json()["usuario"]["saldo_inicial_mes"] is None
