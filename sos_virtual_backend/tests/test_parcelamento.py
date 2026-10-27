"""
testes do calculo de compras parceladas (servicos/parcelamento.py): so as funcoes puras, sem banco
rodar: py -m pytest tests/test_parcelamento.py -v
"""
from datetime import datetime

import pytest

from servicos.parcelamento import cronograma, datas_das_parcelas, resumo_parcelamento


# ----------------------------------------------------------------- sem juros
def test_sem_juros_divide_igual_quando_fecha():
    assert cronograma(1200, 12, 0) == [100.0] * 12


def test_sem_juros_resto_dos_centavos_vai_para_as_primeiras_parcelas():
    assert cronograma(1000, 3, 0) == [333.34, 333.33, 333.33]
    assert round(sum(cronograma(1000, 3, 0)), 2) == 1000.0


@pytest.mark.parametrize("valor,n", [(0.05, 2), (99.99, 7), (1234.56, 11), (0.01, 2), (10_000_000, 36), (100.10, 3)])
def test_sem_juros_a_soma_sempre_fecha_exata(valor, n):
    valores = cronograma(valor, n, 0)
    assert len(valores) == n and round(sum(valores), 2) == round(valor, 2)
    assert max(valores) - min(valores) <= 0.01 + 1e-9


def test_juros_none_ou_zero_sao_iguais():
    assert cronograma(500, 5, None) == cronograma(500, 5, 0) == [100.0] * 5


# ------------------------------------------------------------------ com juros (Tabela Price)
@pytest.mark.parametrize("vista,n,juros,esperado", [
    (1000, 12, 1.0, 88.85),       # exemplo classico: 12x de R$ 88,85
    (1000, 10, 2.0, 111.33),
    (5000, 24, 1.99, 264.06),
    (100, 2, 5.0, 53.78),
])
def test_valor_da_parcela_com_juros(vista, n, juros, esperado):
    assert cronograma(vista, n, juros) == [esperado] * n


@pytest.mark.parametrize("vista,n,juros", [(1000, 12, 1.0), (2599.90, 10, 2.5), (80, 36, 0.5), (15000, 24, 3.99), (300, 2, 12)])
def test_tabela_de_amortizacao_zera_o_saldo(vista, n, juros):
    """confere a formula de forma independente: simulando mes a mes, o saldo devedor chega a ~zero na ultima parcela"""
    pmt = cronograma(vista, n, juros)[0]
    saldo = float(vista)
    for _ in range(n):
        saldo = saldo * (1 + juros / 100) - pmt
    assert abs(saldo) < 0.01 * n          # sobra so o efeito de arredondar a parcela para centavos


def test_juros_total_e_valor_total():
    r = resumo_parcelamento(1000, 12, 1.0)
    assert r["valor_parcela"] == 88.85 and r["valor_total"] == 1066.2 and r["juros_total"] == 66.2


def test_sem_juros_resumo_nao_tem_juros():
    r = resumo_parcelamento(1200, 12, 0)
    assert r["valor_total"] == 1200.0 and r["juros_total"] == 0.0 and r["valor_parcela"] == 100.0


def test_resumo_mostra_ultima_parcela_diferente_quando_sobra_centavo():
    r = resumo_parcelamento(1000, 3, 0)
    assert r["valor_parcela"] == 333.34 and r["ultima_parcela"] == 333.33


def test_juros_maiores_geram_parcelas_maiores():
    assert cronograma(1000, 12, 1)[0] < cronograma(1000, 12, 2)[0] < cronograma(1000, 12, 5)[0]


def test_mais_parcelas_diminuem_o_valor_mas_aumentam_o_total():
    a, b = resumo_parcelamento(1000, 6, 2), resumo_parcelamento(1000, 12, 2)
    assert b["valor_parcela"] < a["valor_parcela"] and b["valor_total"] > a["valor_total"]


# --------------------------------------------------------------------------- datas
def test_datas_mensais_a_partir_da_primeira():
    d = datas_das_parcelas(datetime(2026, 10, 23), 4)
    assert [x.strftime("%Y-%m-%d") for x in d] == ["2026-10-23", "2026-11-23", "2026-12-23", "2027-01-23"]


def test_datas_em_fim_de_mes_nao_pulam_mes():
    d = datas_das_parcelas(datetime(2026, 1, 31), 4)
    assert [x.strftime("%Y-%m-%d") for x in d] == ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"]


def test_datas_atravessam_ano_bissexto():
    assert datas_das_parcelas(datetime(2027, 12, 31), 3)[-1].strftime("%Y-%m-%d") == "2028-02-29"
