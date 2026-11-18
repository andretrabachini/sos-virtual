"""
testes da interpretacao de frases do assistente (funcoes puras, sem banco)
rodar: py -m pytest tests/test_assistente_texto.py -v
"""
from datetime import datetime

import pytest

from servicos.assistente_texto import (
    achar_conta, alinhado, brl, classificar, conta_desconhecida, descricao_do_lancamento, eh_complemento, eh_pergunta, extrair_categoria,
    extrair_data, extrair_parcelas, extrair_periodo, extrair_valor, menciona_parcelamento, nome_do_mes, tipo_do_lancamento,
)

HOJE = datetime(2026, 11, 16)          # segunda-feira


def d(ano, mes, dia):
    return datetime(ano, mes, dia)


# =========================================================================== utilitarios
def test_alinhado_mantem_o_comprimento():
    for texto in ["Alimentação", "paguei R$ 50,00 no cartão Itaú", "ÇÃÕ àéîõü", "açaí 🍇 com leite"]:
        assert len(alinhado(texto)) == len(texto)
    assert alinhado("Alimentação Ñandú") == "alimentacao nandu"


@pytest.mark.parametrize("valor,esperado", [(0, "R$ 0,00"), (50, "R$ 50,00"), (1234.5, "R$ 1.234,50"), (1234567.891, "R$ 1.234.567,89"), (-80, "-R$ 80,00")])
def test_brl(valor, esperado):
    assert brl(valor) == esperado


def test_nome_do_mes():
    assert nome_do_mes("2026-03") == "março de 2026" and nome_do_mes("2025-12") == "dezembro de 2025"


# ================================================================================ valor
@pytest.mark.parametrize("frase,valor", [
    ("gastei R$ 50 no mercado", 50), ("gastei r$50 no mercado", 50), ("gastei 50 reais no mercado", 50), ("gastei 50 no mercado", 50), ("paguei 120,50 de luz", 120.5),
    ("paguei R$ 1.234,56 de aluguel", 1234.56), ("paguei 1234,56 de aluguel", 1234.56), ("paguei 1.200 de aluguel", 1200), ("gastei 1.5 no pão", 1.5), ("gastei 12.50 no pão", 12.5),
    ("gastei 2 mil no dentista", 2000), ("gastei 1,5 mil no dentista", 1500), ("recebi 3000 de salário", 3000), ("recebi R$ 3.000,00 de salário", 3000),
    ("comprei 2 camisas por 80", 80), ("comprei 2 camisas por 80 reais", 80), ("comprei um celular de 1500 em 10x", 1500), ("paguei 89,90 no cartão em 3x", 89.9),
    ("paguei a conta de luz 189,90 dia 10", 189.9), ("gastei 30 no cinema dia 15/11", 30), ("gastei 45 em 10 de novembro no mercado", 45), ("recebi 500 do freela às 14h", 500),
    ("gastei 40 no almoço 14:30", 40), ("gastei 15 em novembro de 2026 no mercado", 15), ("gastei 50 pilas no bar", 50), ("gastei 7 contos no pão", 7),
])
def test_valor_reconhecido(frase, valor):
    status, v, span = extrair_valor(frase)
    assert (status, v) == ("ok", valor), frase
    assert span and frase[span[0]:span[1]].strip()


@pytest.mark.parametrize("frase", ["gastei no mercado", "gastei dia 10 no mercado", "gastei em 3x no mercado", "compra de 15/10 no mercado", "foi em 10 de novembro", "as 14h no mercado", "gastei em 2026 no mercado"])
def test_sem_valor_em_dinheiro(frase):
    assert extrair_valor(frase)[0] == "nenhum", frase


@pytest.mark.parametrize("frase", ["gastei R$ 50 e R$ 30", "gastei 50 de gasolina e 20 de lanche", "gastei 10 reais e 20 reais", "gastei 10 e 20"])
def test_mais_de_um_valor_e_ambiguo(frase):
    assert extrair_valor(frase)[0] == "ambiguo", frase


@pytest.mark.parametrize("frase", ["gastei 0 no mercado", "gastei 0,00 no mercado", "gastei 99999999999 no mercado"])
def test_valor_invalido(frase):
    assert extrair_valor(frase)[0] == "invalido", frase


def test_valor_marcado_vence_numero_solto():
    assert extrair_valor("comprei 3 camisas e gastei R$ 90")[1] == 90
    assert extrair_valor("comprei 2 camisas por 80")[1] == 80            # "por" indica o preco


# ================================================================================= data
@pytest.mark.parametrize("frase,esperada", [
    ("gastei 50 hoje", d(2026, 11, 16)), ("gastei 50 ontem", d(2026, 11, 15)), ("gastei 50 anteontem", d(2026, 11, 14)),
    ("gastei 50 dia 10", d(2026, 11, 10)), ("gastei 50 dia 16", d(2026, 11, 16)), ("gastei 50 dia 20", d(2026, 10, 20)),          # dia 20 ainda nao chegou: mes passado
    ("gastei 50 em 10/11", d(2026, 11, 10)), ("gastei 50 em 25/12", d(2025, 12, 25)), ("gastei 50 em 10/11/2025", d(2025, 11, 10)), ("gastei 50 em 10/11/25", d(2025, 11, 10)),
    ("gastei 50 em 3 de outubro", d(2026, 10, 3)), ("gastei 50 em 3 de dezembro", d(2025, 12, 3)), ("gastei 50 dia 3 de outubro de 2024", d(2024, 10, 3)),
    ("gastei 50 na sexta", d(2026, 11, 13)), ("gastei 50 no sábado", d(2026, 11, 14)), ("gastei 50 na segunda", d(2026, 11, 16)), ("gastei 50 na segunda passada", d(2026, 11, 9)),
    ("gastei 50 no mercado", None),
])
def test_data_reconhecida(frase, esperada):
    data, span, erro = extrair_data(frase, HOJE)
    assert (data, erro) == (esperada, None), frase
    assert (span is None) == (esperada is None)


@pytest.mark.parametrize("frase,trecho", [("gastei 50 em 31/02", "31/02"), ("gastei 50 dia 31 no mercado", "31"), ("gastei 50 em 30/02/2026", "30/02")])
def test_data_impossivel_gera_erro(frase, trecho):
    data, _, erro = extrair_data(frase, HOJE.replace(month=3, day=15) if "dia 31" in frase else HOJE)
    assert data is None and erro and ("não existe" in erro) and trecho.split("/")[0] in erro


@pytest.mark.parametrize("frase", ["gastei 15 em outubro", "gastei 15 no mês de março", "gastei 15 durante dezembro"])
def test_mes_sem_dia_pergunta_o_dia(frase):
    data, _, erro = extrair_data(frase, HOJE)
    assert data is None and erro.startswith("Em que dia de ") and "«dia 10 de " in erro


def test_data_explicita_vence_palavra_relativa():
    assert extrair_data("gastei 50 hoje, dia 10/11", HOJE)[0] == d(2026, 11, 10)


# ====================================================================== parcelas e tipo
@pytest.mark.parametrize("frase,qtd", [("em 10x", 10), ("em 3 parcelas", 3), ("12 vezes", 12), ("comprei em 6x no cartão", 6), ("parcelei em 2x", 2)])
def test_parcelas(frase, qtd):
    assert extrair_parcelas(frase)[0] == qtd and menciona_parcelamento(frase)


@pytest.mark.parametrize("frase", ["gastei 50 no mercado", "comprei 1x", "gastei 3 reais", "em 100x"])
def test_sem_parcelas(frase):
    assert extrair_parcelas(frase)[0] is None


def test_menciona_parcelamento_sem_numero():
    assert menciona_parcelamento("parcelei o notebook") and menciona_parcelamento("compra a prazo") and not menciona_parcelamento("gastei no mercado")


@pytest.mark.parametrize("frase,tipo", [
    ("gastei 50 no mercado", "despesa"), ("paguei a luz", "despesa"), ("comprei um tênis", "despesa"), ("investi 500 no tesouro", "despesa"), ("abasteci 200", "despesa"),
    ("recebi 3000", "receita"), ("ganhei 100 de presente", "receita"), ("caiu o salário", "receita"), ("me pagaram 500", "receita"), ("vendi o celular por 800", "receita"),
    ("recebi e gastei 50", "ambos"), ("como estão meus gastos?", None), ("meus gastos", None), ("oi", None),
])
def test_tipo_do_lancamento(frase, tipo):
    assert tipo_do_lancamento(frase) == tipo


@pytest.mark.parametrize("frase", ["quanto gastei?", "Quanto eu gastei com mercado?", "qual meu saldo", "como estão meus gastos", "me diga quanto gastei", "posso gastar 50?", "gastei 50?", "quero saber o total"])
def test_e_pergunta(frase):
    assert eh_pergunta(frase)


@pytest.mark.parametrize("frase", ["gastei 50 no mercado", "comprei um livro como presente por 50", "paguei 20 de luz", "recebi 100"])
def test_nao_e_pergunta(frase):
    assert not eh_pergunta(frase)


# ================================================================================ conta
CONTAS = ["Cartão Itaú", "Vale Alimentação", "Conta Principal", "Cartão Nubank Roxinho"]


@pytest.mark.parametrize("frase,conta", [
    ("gastei 50 no itaú", "Cartão Itaú"), ("gastei 50 no cartão itau", "Cartão Itaú"), ("gastei 50 no CARTÃO ITAÚ", "Cartão Itaú"),
    ("gastei 50 em alimentação no vale alimentação", "Vale Alimentação"), ("gastei 50 no vale alimentacao", "Vale Alimentação"),
    ("gastei 50 na conta principal", "Conta Principal"), ("gastei 50 no nubank roxinho", "Cartão Nubank Roxinho"),
])
def test_conta_reconhecida(frase, conta):
    achada, empatadas, palavras = achar_conta(frase, CONTAS)
    assert achada == conta and empatadas == [] and palavras


@pytest.mark.parametrize("frase", ["gastei 50 no mercado", "gastei 50 em alimentação", "gastei 50 no vale", "gastei 50 no nubank", "paguei a conta de luz"])
def test_nenhuma_conta(frase):
    assert achar_conta(frase, CONTAS)[0] is None


def test_conta_ambigua():
    achada, empatadas, _ = achar_conta("gastei 50 no itau", ["Cartão Itaú", "Conta Itaú"])
    assert achada is None and sorted(empatadas) == ["Cartão Itaú", "Conta Itaú"]
    assert achar_conta("gastei 50 no cartão itau", ["Cartão Itaú", "Conta Itaú"])[0] is None              # "cartao"/"conta" sao genericas: continua empatado


def test_nome_mais_especifico_vence():
    assert achar_conta("gastei 50 no nubank roxinho", ["Cartão Nubank", "Cartão Nubank Roxinho"])[0] == "Cartão Nubank Roxinho"


@pytest.mark.parametrize("frase,palavra", [("gastei 30 no cartão Nubank", "Nubank"), ("paguei no cartão de PicPay", "PicPay"), ("usei o vale Sodexo", "Sodexo")])
def test_conta_desconhecida(frase, palavra):
    assert conta_desconhecida(frase) == palavra


@pytest.mark.parametrize("frase", ["paguei a conta de luz", "gastei no cartão de crédito", "gastei no cartão", "gastei 50 no mercado"])
def test_conta_de_luz_nao_e_conta_desconhecida(frase):
    assert conta_desconhecida(frase) is None


# ============================================================================= descricao
def desc(frase, contas=CONTAS):
    status, valor, span = extrair_valor(frase)
    data, span_data, _ = extrair_data(frase, HOJE)
    _, span_parcelas = extrair_parcelas(frase)
    conta, _, palavras = achar_conta(frase, contas)
    extra = {alinhado(conta_desconhecida(frase) or "")} - {""} if not conta else set()
    return descricao_do_lancamento(frase, [s for s in (span, span_data, span_parcelas) if s], palavras | extra)


@pytest.mark.parametrize("frase,descricao", [
    ("gastei R$ 50 no mercado hoje", "Mercado"), ("paguei 120,50 de luz", "Luz"), ("comprei um tênis por 200", "Tênis"), ("recebi 3000 de salário", "Salário"),
    ("gastei 50 reais com uber ontem", "Uber"), ("paguei R$ 1.234,56 de aluguel", "Aluguel"), ("gastei 2 mil no dentista", "Dentista"), ("comprei 2 camisas por 80", "2 camisas"),
    ("paguei a conta de luz 189,90 dia 10", "Conta de luz"), ("gastei 30 no cinema dia 15/11", "Cinema"), ("recebi 500 do freela às 14h", "Freela"), ("gastei 40 no almoço 14:30", "Almoço"),
    ("gastei 80 no restaurante sexta", "Restaurante"), ("eu gastei hoje 25 reais na padaria", "Padaria"), ("gastei 50 no mercado!", "Mercado"), ("Gastei R$ 50 no Mercado Extra.", "Mercado Extra"),
    ("gastei 50 no cartão itaú em gasolina", "Gasolina"), ("gastei 50 em gasolina no itaú", "Gasolina"), ("paguei 300 de mensalidade da faculdade", "Mensalidade da faculdade"),
    ("gastei 50 no cartão Nubank no uber", "Uber"), ("gastei 50", ""), ("gastei R$ 50 hoje", ""), ("recebi 100", ""),
])
def test_descricao(frase, descricao):
    assert desc(frase) == descricao, frase


def test_descricao_limita_o_tamanho():
    assert len(descricao_do_lancamento("gastei 50 " + "x" * 400, [(7, 9)])) <= 255


# ========================================================================= periodo e categoria
@pytest.mark.parametrize("frase,mes,explicito", [
    ("como estão meus gastos?", "2026-11", False), ("como estão meus gastos este mês?", "2026-11", True), ("gastos neste mês", "2026-11", True), ("no mês atual", "2026-11", True),
    ("e no mês passado?", "2026-10", True), ("no mes anterior", "2026-10", True), ("no último mês", "2026-10", True), ("mês retrasado", "2026-09", True),
    ("quanto gastei em outubro?", "2026-10", True), ("em janeiro", "2026-01", True), ("em dezembro", "2025-12", True), ("em março de 2024", "2024-03", True),
    ("em novembro", "2026-11", True), ("em maio de 2026", "2026-05", True),
])
def test_periodo(frase, mes, explicito):
    assert extrair_periodo(frase, HOJE) == (mes, explicito), frase


def test_periodo_na_virada_do_ano():
    janeiro = datetime(2027, 1, 10)
    assert extrair_periodo("mês passado", janeiro)[0] == "2026-12" and extrair_periodo("em dezembro", janeiro)[0] == "2026-12" and extrair_periodo("em fevereiro", janeiro)[0] == "2026-02"


@pytest.mark.parametrize("frase,categoria", [
    ("quanto gastei com alimentação?", "Alimentação"), ("quanto gastei com mercado?", "Alimentação"), ("gastos com uber", "Transporte"), ("quanto gastei com lazer", "Lazer"),
    ("quanto gastei com restaurante", "Restaurante"), ("gastos de moradia", "Moradia"), ("quanto paguei de aluguel", "Moradia"), ("meus gastos com saúde", "Saúde"),
    ("como estão meus gastos?", None), ("quanto gastei este mês?", None), ("quanto gastei em outubro?", None), ("e no mês passado?", None),
])
def test_categoria(frase, categoria):
    assert extrair_categoria(frase) == categoria, frase


# ============================================================================= intencao
@pytest.mark.parametrize("frase,intencao", [
    ("Como estão meus gastos este mês?", "resumo"), ("resumo do mês", "resumo"), ("qual meu saldo?", "resumo"), ("quanto gastei este mês?", "resumo"), ("quanto ainda posso gastar?", "resumo"),
    ("Me dê dicas para economizar", "dicas"), ("como gastar menos?", "dicas"), ("quero reduzir meus gastos", "dicas"),
    ("Como montar uma reserva de emergência?", "reserva"), ("preciso de uma reserva de emergencia", "reserva"),
    ("Qual cartão devo usar?", "otimizar"), ("como pagar minhas despesas?", "otimizar"), ("onde tem cashback?", "otimizar"), ("me ajuda a escolher qual cartão usar", "otimizar"),
    ("minhas metas", "metas"), ("quais são meus objetivos?", "metas"), ("meus alertas", "alertas"), ("estourei algum limite de gasto?", "alertas"),
    ("tenho parcelas nos próximos meses?", "parcelas"), ("quanto já está comprometido?", "parcelas"),
    ("últimas transações", "ultimas"), ("o que gastei por último?", "ultimas"), ("maiores gastos", "maiores"), ("onde eu mais gasto?", "maiores"), ("para onde vai meu dinheiro?", "maiores"),
    ("quanto recebi em outubro?", "receitas"), ("minhas receitas", "receitas"),
    ("como funciona a regra 50/30/20?", "educ_orcamento"), ("como montar um orçamento?", "educ_orcamento"), ("quero sair do vermelho", "educ_dividas"), ("estou endividado", "educ_dividas"),
    ("devo investir no tesouro direto?", "educ_investir"), ("como investir?", "educ_investir"), ("como usar bem o cartão de crédito?", "educ_cartao"),
    ("o que são juros compostos?", "educ_juros"), ("vale a pena parcelar?", "educ_parcelar"),
    ("ajuda", "ajuda"), ("o que você faz?", "ajuda"), ("como funciona o sistema?", "ajuda"),
    ("oi", "saudacao"), ("bom dia", "saudacao"), ("Olá, tudo bem?", "saudacao"), ("obrigado!", "agradecimento"), ("valeu", "agradecimento"),
    ("asdfgh", "desconhecida"), ("e em outubro?", "desconhecida"), ("quanto é 2+2", "desconhecida"),
])
def test_classificar(frase, intencao):
    assert classificar(frase) == intencao, frase


def test_saudacao_nao_atrapalha_a_pergunta():
    assert classificar("bom dia, quanto gastei este mês?") == "resumo"
    assert classificar("obrigado, e minhas metas?") == "metas"
    assert classificar("oi, me dê dicas") == "dicas"


@pytest.mark.parametrize("frase", ["e em outubro?", "e no mês passado?", "e com transporte?", "E agora?", "e o mês retrasado"])
def test_complemento(frase):
    assert eh_complemento(frase)


@pytest.mark.parametrize("frase", ["quanto gastei?", "estou bem", "e " + "palavra " * 10, "eu gastei"])
def test_nao_e_complemento(frase):
    assert not eh_complemento(frase)
