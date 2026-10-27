"""
testes da leitura de extratos (servicos/extratos.py): CSV, OFX, valores, datas e compras parceladas
rodar: py -m pytest tests/test_extratos.py -v   (nao precisa de banco)
"""
from datetime import datetime

import pytest

from servicos.extratos import (
    ExtratoInvalido, calcular_parcelas, chave_compra, detectar_parcela, gerar_projecoes, ler_extrato,
    limpar_descricao_parcela, parse_data, parse_valor,
)


# ------------------------------------------------------------------- valores e datas
@pytest.mark.parametrize("texto,esperado", [
    ("R$ 1.234,56", 1234.56), ("-50.00", -50.0), ("(50,00)", -50.0), ("50,00 D", -50.0), ("1.234", 1234.0),
    ("12,5", 12.5), ("1,234.56", 1234.56), ("-R$ 8,90", -8.9), ("abc", None), ("", None),
])
def test_parse_valor(texto, esperado):
    assert parse_valor(texto) == esperado


@pytest.mark.parametrize("texto,esperado", [
    ("05/10/2026", datetime(2026, 10, 5)), ("05/10/26", datetime(2026, 10, 5)), ("2026-10-05", datetime(2026, 10, 5)),
    ("2026-10-05 10:30:00", datetime(2026, 10, 5)), ("05-10-2026", datetime(2026, 10, 5)), ("32/13/2026", None),
    ("", None), ("01/01/1800", None),
])
def test_parse_data(texto, esperado):
    assert parse_data(texto) == esperado


# --------------------------------------------------------------------------- CSV
CSV = ("Extrato Banco X;;\nConta 1234;;\n\nData;Histórico;Valor (R$)\n"
       "05/10/2026;MERCADO SAO JOAO;-450,00\n06/10/2026;LOJA XYZ PARC 02/05;-100,00\n08/10/2026;SALARIO;2.000,00\n"
       "32/13/2026;DATA RUIM;-5,00\n09/10/2026;SEM VALOR;abc\n")


def test_csv_com_preambulo_latin1_e_linhas_com_erro():
    lancamentos, erros = ler_extrato("csv", CSV.encode("latin-1"))
    assert [(l["descricao"], l["valor"]) for l in lancamentos] == [("MERCADO SAO JOAO", -450.0), ("LOJA XYZ PARC 02/05", -100.0), ("SALARIO", 2000.0)]
    assert [e["motivo"] for e in erros] == ["data inválida", "valor inválido"]


def test_csv_separado_por_virgula():
    lancamentos, _ = ler_extrato("csv", b"Data,Descricao,Valor\n2026-10-05,Mercado,-10.50\n")
    assert lancamentos[0]["valor"] == -10.5


def test_csv_sem_cabecalho_ou_vazio_e_recusado():
    for conteudo in (b"coluna1;coluna2\n1;2\n", b"", b"Data;Descricao;Valor\n"):
        with pytest.raises(ExtratoInvalido):
            ler_extrato("csv", conteudo)


def test_csv_com_linhas_demais_e_recusado():
    with pytest.raises(ExtratoInvalido, match="linhas demais"):
        ler_extrato("csv", ("Data;Descricao;Valor\n" + "01/01/2026;X;-1,00\n" * 1001).encode())


# --------------------------------------------------------------------------- OFX
OFX = b"""OFXHEADER:100
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKTRANLIST>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20261005120000[-3:BRT]<TRNAMT>-450.00<MEMO>MERCADO
</STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20261006<TRNAMT>-100.00<NAME>LOJA XYZ<MEMO>PARC 02/05 &amp; CIA
</STMTTRN>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20261008<TRNAMT>2000,00<MEMO>SALARIO
</STMTTRN>
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"""


def test_ofx_com_tags_sem_fechamento_e_nome_junto_do_memo():
    lancamentos, erros = ler_extrato("ofx", OFX)
    assert [(l["descricao"], l["valor"]) for l in lancamentos] == [("MERCADO", -450.0), ("LOJA XYZ PARC 02/05 & CIA", -100.0), ("SALARIO", 2000.0)]
    assert erros == []


def test_ofx_nao_resolve_entidades_externas():
    malicioso = b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><OFX><STMTTRN><DTPOSTED>20261005<TRNAMT>-1.00<MEMO>&e;</STMTTRN></OFX>'
    lancamentos, _ = ler_extrato("ofx", malicioso)
    assert "root:" not in lancamentos[0]["descricao"]


# ------------------------------------------------------------------- parcelas
@pytest.mark.parametrize("descricao,esperado", [
    ("LOJA XYZ PARC 02/05", (2, 5)), ("PARCELA 2 DE 5", (2, 5)), ("TV 1/3", (1, 3)), ("parcelado 3/6", (3, 6)), ("Parc.3/6", (3, 6)),
    ("COMPRA 05/10/2026 MERCADO", None), ("SEM PARCELA", None), ("X 12/10", None), ("X 1/1", None), ("X 1/99", None),
])
def test_detectar_parcela(descricao, esperado):
    assert detectar_parcela(descricao) == esperado


@pytest.mark.parametrize("descricao,esperado", [
    ("TV 55 PARC 02/06", "TV 55"), ("NOTEBOOK DELL PARCELA 2 DE 10", "NOTEBOOK DELL"), ("Notebook Dell (2/10)", "Notebook Dell"),
    ("LOJA XYZ 3/12", "LOJA XYZ"), ("COMPRA 05/10/2026 MERCADO 2/3", "COMPRA 05/10/2026 MERCADO"), ("Pagamento (1/2) mercado", "Pagamento mercado"),
    ("PARC 02/05", "PARC 02/05"), ("Sem marcador", "Sem marcador"), ("TV - PARC 1/3", "TV"),
])
def test_limpar_descricao_parcela(descricao, esperado):
    assert limpar_descricao_parcela(descricao) == esperado


def test_mesma_compra_em_meses_diferentes_tem_a_mesma_chave():
    assert chave_compra("LOJA XYZ PARC 02/05", 5) == chave_compra("Loja  xyz Parc 03/05", 5)


def test_valor_parcela_ou_valor_total():
    assert calcular_parcelas(100.0, 2, 5, False) == [100.0] * 5
    v = calcular_parcelas(100.0, 1, 3, True)
    assert v == [33.34, 33.33, 33.33] and round(sum(v), 2) == 100.0


def test_projecoes_mensais_com_fim_de_mes():
    p = gerar_projecoes(datetime(2026, 1, 31), 1, 4, [75.0] * 4)
    assert [x["data"].strftime("%Y-%m-%d") for x in p] == ["2026-02-28", "2026-03-31", "2026-04-30"] and [x["numero"] for x in p] == [2, 3, 4]
