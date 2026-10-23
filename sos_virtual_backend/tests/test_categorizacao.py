"""
testes da deteccao automatica de categoria (servicos/categorizacao.py)
rodar: py -m pytest tests/test_categorizacao.py -v   (dentro de sos_virtual_backend)
nao precisa de banco de dados nem do servidor
"""
import time

import pytest

from servicos.categorizacao import (
    CATEGORIA_PADRAO, REGRAS, SO_RECEITA, detectar_categoria, detectar_categoria_com_motivo, normalizar,
)

CATEGORIAS_DO_SISTEMA = {"Alimentação", "Transporte", "Saúde", "Educação", "Lazer", "Moradia",
                         "Vestuário", "Investimentos", "Outros"}


def cat(texto, valor=-10):
    return detectar_categoria(texto, valor)


# ------------------------------------------------------------------ texto
@pytest.mark.parametrize("texto,esperado", [
    ("Farmácia São Paulo", "Saúde"), ("FARMACIA SAO JOAO", "Saúde"), ("farmácia", "Saúde"),
    ("Farma\u0301cia", "Saúde"),                       # acento "solto" (letra + acento separado)
    ("Café da manhã", "Alimentação"), ("CAFE", "Alimentação"),
    ("Tênis novo", "Vestuário"), ("TENIS", "Vestuário"),
    ("Conta de ÁGUA", "Moradia"), ("Almoço", "Alimentação"),
    ("ＵＢＥＲ ＴＲＩＰ", "Transporte"),               # letras de largura total
    ("Uber\u200b", "Transporte"),                     # caractere invisivel colado na palavra
])
def test_acentos_maiusculas_e_caracteres_especiais(texto, esperado):
    assert cat(texto) == esperado


@pytest.mark.parametrize("texto,esperado", [
    ("UBER *TRIP", "Transporte"), ("UBER* TRIP", "Transporte"), ("IFD*PIZZARIA DO ZE", "Alimentação"),
    ("PAG*PADARIA SANTA", "Alimentação"), ("iFood*Restaurante", "Alimentação"),
    ("COMPRA CARTAO 1234 MERCADO 05/10", "Alimentação"), ("PIX ENVIADO JOAO", "Outros"),
    ("NETFLIX.COM", "Lazer"), ("SPOTIFY AB", "Lazer"), ("PARC 02/05 TENIS", "Vestuário"),
    ("DEB AUT CPFL ENERGIA", "Moradia"), ("SABESP-CONTA", "Moradia"),
])
def test_formatos_de_extrato_bancario(texto, esperado):
    assert cat(texto) == esperado


# ------------------------------------------------- palavra inteira (erros da versao antiga)
@pytest.mark.parametrize("texto", [
    "Luzia Maria", "Doação para ONG", "Compra 199 reais", "Operação limpeza", "Showroom Fiat",
    "Barbearia do João", "Barra Shopping", "Consultoria financeira", "Loja de ferragens",
    "Jogador de futebol", "Pagamento boleto", "Gasolineira", "Agrupamento", "Metrópole",
])
def test_nao_casa_palavra_dentro_de_outra(texto):
    assert cat(texto) == "Outros"


def test_gasolina_nao_vira_moradia_por_causa_de_gas():
    assert cat("Posto gasolina") == "Transporte"
    assert cat("Gás de cozinha") == "Moradia"


@pytest.mark.parametrize("texto,esperado", [
    ("Restaurantes", "Alimentação"), ("Farmácias", "Saúde"), ("Mercados", "Alimentação"),
    ("Cursos online", "Educação"), ("Ingressos show", "Lazer"), ("Táxis", "Transporte"), ("Pedágios", "Transporte"),
])
def test_plural_simples(texto, esperado):
    assert cat(texto) == esperado


@pytest.mark.parametrize("texto,esperado", [
    ("SUPERMERC BOM PRECO", "Alimentação"), ("HIPERMERCADO EXTRA", "Alimentação"), ("SUPERMERCADO", "Alimentação"),
    ("DROGARIA SAO PAULO", "Saúde"), ("DROGARI", "Saúde"), ("RESTAURANT DO ZE", "Alimentação"),
])
def test_nomes_compostos_e_abreviados_pelo_banco(texto, esperado):
    assert cat(texto) == esperado


# --------------------------------------------------------------- prioridade
@pytest.mark.parametrize("texto,esperado", [
    ("Uber Eats almoço", "Alimentação"), ("UBEREATS", "Alimentação"), ("99 Food", "Alimentação"),
    ("99 Pop corrida", "Transporte"), ("Uber viagem", "Transporte"), ("Viagem para Santos", "Lazer"),
    ("Posto de saúde", "Saúde"), ("Posto Shell", "Transporte"), ("Posto", "Transporte"),
    ("Aluguel de carro", "Transporte"), ("Aluguel apartamento", "Moradia"),
    ("Mercado Livre", "Outros"), ("MERCADOLIVRE*COMPRA", "Outros"), ("Mercado Pago", "Outros"),
    ("Mercado Bitcoin", "Investimentos"), ("Mercado", "Alimentação"),
    ("Mensalidade academia", "Saúde"), ("Mensalidade condomínio", "Moradia"), ("Mensalidade escolar", "Educação"),
    ("Mensalidade", "Educação"), ("Mensalidade plano de saúde", "Saúde"),
    ("Clínica veterinária", "Outros"), ("Pet shop", "Outros"), ("Clínica", "Saúde"),
    ("Amazon Prime", "Lazer"), ("Amazon", "Outros"),
    ("Restaurante no hotel", "Alimentação"), ("Bar e restaurante", "Alimentação"), ("Bar do Zé", "Lazer"),
])
def test_prioridade_pela_palavra_mais_especifica(texto, esperado):
    assert cat(texto) == esperado


# ------------------------------------------------------------------ receitas
@pytest.mark.parametrize("texto,valor,esperado", [
    ("Salário outubro", 3000, "Salário"), ("13º salário", 1500, "Salário"), ("Férias", 2000, "Salário"),
    ("Bônus anual", 800, "Salário"), ("Folha de pagamento", 4000, "Salário"),
    ("Rendimento poupança", 12.5, "Investimentos"), ("Dividendos", 40, "Investimentos"), ("Resgate CDB", 1000, "Investimentos"),
    ("PIX RECEBIDO JOAO", 50, "Outros"), ("Restituição IR", 900, "Outros"), ("Freelance site", 700, "Outros"),
    ("Estorno Uber", 23.9, "Transporte"),
])
def test_receitas(texto, valor, esperado):
    assert cat(texto, valor) == esperado


@pytest.mark.parametrize("texto", ["Salário outubro", "13º salário", "Férias", "Bônus anual", "Folha de pagamento"])
def test_salario_nunca_e_sugerido_para_despesa(texto):
    assert cat(texto, -100) == "Outros"
    assert cat(texto, None) == "Outros"          # sem valor informado = despesa


def test_despesa_com_palavra_de_salario_usa_a_outra_categoria():
    assert cat("Pagamento de salário da diarista", -900) == "Moradia"


# -------------------------------------------------------------------- bordas
@pytest.mark.parametrize("entrada", [
    "", "   ", None, 123, [], {}, 3.14, True, "!!!***", "12345", "😀😀😀", "\n\t", "<script>alert(1)</script>",
    "'; DROP TABLE transacoes;--", "uber" * 100, "a" * 255,
])
def test_entradas_estranhas_nunca_quebram(entrada):
    resultado = detectar_categoria(entrada, -10)
    assert resultado in CATEGORIAS_DO_SISTEMA


def test_texto_muito_grande_e_rapido_e_nao_trava():
    inicio = time.time()
    assert cat("x" * 200_000) == "Outros"
    assert cat("mercado " * 50_000) == "Alimentação"
    assert time.time() - inicio < 1


def test_mil_descricoes_em_menos_de_dois_segundos():
    descricoes = [f"COMPRA {i} MERCADO BOM PRECO LOJA {i}" for i in range(1000)]
    inicio = time.time()
    assert all(cat(d) == "Alimentação" for d in descricoes)
    assert time.time() - inicio < 2


def test_valor_invalido_e_tratado_como_despesa():
    assert detectar_categoria("Salário", "muito") == "Outros"
    assert detectar_categoria("Salário", True) == "Outros"
    assert detectar_categoria("Salário", float("nan")) == "Outros"
    assert detectar_categoria("Salário", 0) == "Outros"


def test_motivo_informa_a_palavra_que_decidiu():
    assert detectar_categoria_com_motivo("Compra no SUPERMERCADO Bom Preço", -50) == ("Alimentação", "supermerc")
    assert detectar_categoria_com_motivo("Uber Eats", -50) == ("Alimentação", "uber eats")
    assert detectar_categoria_com_motivo("coisa qualquer", -50) == ("Outros", None)
    assert detectar_categoria_com_motivo("", -50) == ("Outros", None)


def test_resultado_nao_depende_de_maiusculas_ou_espacos_extras():
    assert cat("  UBER    *   TRIP  ") == cat("uber trip") == "Transporte"


# --------------------------------------------- consistencia da propria tabela de regras
def test_so_existem_categorias_conhecidas():
    assert set(REGRAS) <= CATEGORIAS_DO_SISTEMA | SO_RECEITA


def test_nenhuma_palavra_vazia_ou_duplicada_na_mesma_categoria():
    for categoria, palavras in REGRAS.items():
        limpas = [normalizar(p.lstrip("?").rstrip("*")) for p in palavras]
        assert all(limpas), f"palavra vazia em {categoria}"
        assert len(limpas) == len(set(limpas)), f"palavra repetida em {categoria}"


def test_mesma_palavra_nao_aparece_em_duas_categorias():
    vistas = {}
    for categoria, palavras in REGRAS.items():
        for p in palavras:
            chave = normalizar(p.lstrip("?").rstrip("*"))
            assert chave not in vistas, f"'{chave}' aparece em {vistas.get(chave)} e em {categoria}"
            vistas[chave] = categoria


def test_cada_palavra_da_tabela_leva_a_propria_categoria():
    """se uma palavra for 'engolida' por outra categoria, ela nunca funcionaria: aqui isso aparece"""
    problemas = []
    for categoria, palavras in REGRAS.items():
        for p in palavras:
            texto = p.lstrip("?").rstrip("*")
            obtido = detectar_categoria(texto, 10)            # valor positivo libera Salário
            if obtido != categoria:
                problemas.append(f"'{texto}' deveria ser {categoria}, deu {obtido}")
    assert not problemas, "\n".join(problemas)


def test_palavras_de_salario_nao_vazam_para_despesas():
    for p in REGRAS["Salário"]:
        assert detectar_categoria(p, -10) != "Salário", p
