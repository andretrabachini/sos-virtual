"""
testes da API: baixar o modelo de planilha e importar planilhas (XLSX e CSV) com Tipo, Categoria e Conta
rodar: py -m pytest tests/test_api_planilhas.py -v   (banco SQLite em memoria; veja conftest.py)
"""
import io
from datetime import datetime

import pytest
from openpyxl import Workbook, load_workbook

CABECALHO = ["Data", "Descrição", "Valor", "Tipo", "Categoria", "Conta"]
TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture()
def ana(cliente):
    r = cliente.post("/api/auth/cadastro", json={"nome": "Ana Teste", "email": "ana@x.com", "senha": "senha1234", "lgpd_aceito": True})
    return {"Authorization": "Bearer " + r.get_json()["token"]}


def planilha(linhas):
    livro = Workbook()
    folha = livro.active
    folha.title = "Lançamentos"
    folha.append(CABECALHO)
    for linha in linhas:
        folha.append(list(linha))
    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()


def enviar(c, h, conteudo, nome="planilha.xlsx", **form):
    return c.post("/api/simulacoes/importar-extrato", headers=h, content_type="multipart/form-data",
                  data={"arquivo": (io.BytesIO(conteudo), nome), **form})


def transacoes(c, h):
    return {t["descricao"]: t for t in c.get("/api/transacoes", headers=h).get_json()}


D = datetime(2026, 10, 15)


# ========================================================================= baixar o modelo
def test_baixar_modelo_em_excel(cliente, ana):
    cliente.post("/api/contas", headers=ana, json={"nome": "Cartão Nubank"})
    r = cliente.get("/api/modelos/planilha.xlsx", headers=ana)
    assert r.status_code == 200 and r.mimetype == TIPO_XLSX
    assert 'attachment; filename="modelo-sos-virtual.xlsx"' in r.headers["Content-Disposition"]
    livro = load_workbook(io.BytesIO(r.data))
    assert [livro["Lançamentos"].cell(1, c).value for c in range(1, 7)] == CABECALHO
    assert livro["Listas"]["B2"].value == "Cartão Nubank"          # a lista suspensa de contas traz as contas do usuario


def test_modelo_so_traz_as_contas_do_proprio_usuario(cliente, ana):
    cliente.post("/api/contas", headers=ana, json={"nome": "Cartão da Ana"})
    r = cliente.post("/api/auth/cadastro", json={"nome": "Bia Teste", "email": "b@x.com", "senha": "senha1234", "lgpd_aceito": True})
    bia = {"Authorization": "Bearer " + r.get_json()["token"]}
    cliente.post("/api/contas", headers=bia, json={"nome": "Cartão da Bia"})
    listas = load_workbook(io.BytesIO(cliente.get("/api/modelos/planilha.xlsx", headers=ana).data))["Listas"]
    assert [listas.cell(i, 2).value for i in (2, 3)] == ["Cartão da Ana", None]


def test_baixar_modelo_em_csv(cliente, ana):
    r = cliente.get("/api/modelos/planilha.csv", headers=ana)
    assert r.status_code == 200 and r.mimetype == "text/csv" and r.data.startswith(b"\xef\xbb\xbf")
    assert r.data.decode("utf-8-sig").splitlines()[0] == ";".join(CABECALHO)
    assert 'filename="modelo-sos-virtual.csv"' in r.headers["Content-Disposition"]


@pytest.mark.parametrize("rota", ["/api/modelos/planilha.xlsx", "/api/modelos/planilha.csv"])
def test_modelo_exige_login(cliente, rota):
    assert cliente.get(rota).status_code == 401


# ================================================================ importar planilha do Excel
def test_caminho_completo_baixar_preencher_e_enviar(cliente, ana):
    """o que o usuario faz: baixa o modelo, preenche no Excel e envia"""
    cliente.post("/api/contas", headers=ana, json={"nome": "Cartão Nubank"})
    livro = load_workbook(io.BytesIO(cliente.get("/api/modelos/planilha.xlsx", headers=ana).data))
    folha = livro["Lançamentos"]
    for linha in ([D, "Supermercado", 250.0, "Despesa", "Alimentação", "Cartão Nubank"], [D, "Salário", 4500, "Receita", "Salário", None]):
        folha.append(linha)
    saida = io.BytesIO()
    livro.save(saida)
    r = enviar(cliente, ana, saida.getvalue())
    assert r.status_code == 201 and r.get_json()["importadas"] == 2
    t = transacoes(cliente, ana)
    assert t["Supermercado"]["valor"] == -250 and t["Supermercado"]["categoria"] == "Alimentação" and t["Supermercado"]["conta"] == "Cartão Nubank"
    assert t["Salário"]["valor"] == 4500 and t["Salário"]["categoria"] == "Salário" and t["Salário"]["conta"] is None


def test_modelo_sem_preencher_nao_importa_nada(cliente, ana):
    r = enviar(cliente, ana, cliente.get("/api/modelos/planilha.xlsx", headers=ana).data)
    assert r.status_code == 400 and "nenhuma transação válida" in r.get_json()["erro"]
    r = enviar(cliente, ana, cliente.get("/api/modelos/planilha.csv", headers=ana).data, "modelo.csv")
    assert r.status_code == 400 and cliente.get("/api/transacoes", headers=ana).get_json() == []


def test_csv_do_modelo_preenchido(cliente, ana):
    csv = cliente.get("/api/modelos/planilha.csv", headers=ana).data + "02/10/2026;Padaria;18,50;Despesa;Alimentação;Cartão Itaú\r\n".encode()
    r = enviar(cliente, ana, csv, "modelo.csv")
    assert r.status_code == 201 and transacoes(cliente, ana)["Padaria"]["conta"] == "Cartão Itaú"


def test_conta_em_branco_usa_a_conta_escolhida_na_tela(cliente, ana):
    r = enviar(cliente, ana, planilha([[D, "Com conta", 10, "Despesa", None, "Cartão A"], [D, "Sem conta", 20, "Despesa", None, None]]), conta="Cartão Padrão")
    assert r.status_code == 201
    t = transacoes(cliente, ana)
    assert t["Com conta"]["conta"] == "Cartão A" and t["Sem conta"]["conta"] == "Cartão Padrão"
    assert {c["nome"] for c in cliente.get("/api/contas", headers=ana).get_json()} == {"Cartão A", "Cartão Padrão"}


def test_categoria_da_planilha_vale_e_ignora_acento_e_maiuscula(cliente, ana):
    enviar(cliente, ana, planilha([[D, "mercado do bairro", 10, "Despesa", "lazer", None], [D, "farmacia", 20, "Despesa", "RESTAURANTE", None], [D, "bar", 30, "Despesa", "saude", None]]))
    t = transacoes(cliente, ana)
    assert (t["mercado do bairro"]["categoria"], t["farmacia"]["categoria"], t["bar"]["categoria"]) == ("Lazer", "Restaurante", "Saúde")     # a planilha manda, mesmo contra a deteccao


def test_categoria_desconhecida_usa_a_deteccao_e_avisa(cliente, ana):
    r = enviar(cliente, ana, planilha([[D, "Supermercado", 10, "Despesa", "Comidinhas", None], [D, "Livro", 20, "Despesa", None, None]])).get_json()
    assert r["categorias_ignoradas"] == 1
    t = transacoes(cliente, ana)
    assert t["Supermercado"]["categoria"] == "Alimentação" and t["Livro"]["categoria"] == "Educação"


def test_salario_numa_despesa_e_ignorado(cliente, ana):
    r = enviar(cliente, ana, planilha([[D, "Pagamento da diarista", 900, "Despesa", "Salário", None]])).get_json()
    assert r["categorias_ignoradas"] == 1 and transacoes(cliente, ana)["Pagamento da diarista"]["categoria"] != "Salário"


def test_tipo_com_valor_positivo_e_sem_tipo_com_sinal(cliente, ana):
    enviar(cliente, ana, planilha([[D, "A despesa", 100, "Despesa", None, None], [D, "B receita", 100, "Receita", None, None], [D, "C sinal", -100, None, None, None], [D, "D positivo", 100, None, None, None]]))
    t = transacoes(cliente, ana)
    assert [t[n]["valor"] for n in ("A despesa", "B receita", "C sinal", "D positivo")] == [-100, 100, -100, 100]


def test_opcao_de_fatura_de_cartao_so_inverte_as_linhas_sem_tipo(cliente, ana):
    enviar(cliente, ana, planilha([[D, "Compra com tipo", 100, "Despesa", None, None], [D, "Compra sem tipo", 100, None, None, None]]), cartao="true")
    t = transacoes(cliente, ana)
    assert t["Compra com tipo"]["valor"] == -100 and t["Compra sem tipo"]["valor"] == -100       # a primeira ja dizia ser despesa; a segunda foi invertida


def test_receita_com_conta_na_planilha_nao_guarda_conta(cliente, ana):
    enviar(cliente, ana, planilha([[D, "Freela", 500, "Receita", None, "Cartão X"]]))
    assert transacoes(cliente, ana)["Freela"]["conta"] is None


def test_reenviar_a_mesma_planilha_nao_duplica(cliente, ana):
    dados = planilha([[D, "Compra", 10, "Despesa", None, "Cartão A"]])
    assert enviar(cliente, ana, dados).get_json()["importadas"] == 1
    r = enviar(cliente, ana, dados).get_json()
    assert r["importadas"] == 0 and r["duplicadas"] == 1 and len(cliente.get("/api/transacoes", headers=ana).get_json()) == 1


def test_linhas_de_exemplo_nunca_entram(cliente, ana):
    r = enviar(cliente, ana, planilha([[D, "EXEMPLO - Supermercado", 250, "Despesa", None, None], [D, "Compra real", 30, "Despesa", None, None]])).get_json()
    assert r["importadas"] == 1 and list(transacoes(cliente, ana)) == ["Compra real"]


def test_limite_de_20_contas_na_planilha(cliente, ana):
    linhas = [[D, f"Compra {i}", 10, "Despesa", None, f"Conta {i}"] for i in range(25)]
    r = enviar(cliente, ana, planilha(linhas)).get_json()
    assert r["importadas"] == 20 and r["linhas_sem_conta"] == 5
    assert len(cliente.get("/api/contas", headers=ana).get_json()) == 20


def test_vale_na_planilha_importa_e_avisa_o_que_esta_fora_da_regra(cliente, ana):
    cliente.post("/api/contas", headers=ana, json={"nome": "Vale Alimentação", "categorias": ["Alimentação"]})
    r = enviar(cliente, ana, planilha([[D, "Mercado", 80, "Despesa", "Alimentação", "Vale Alimentação"], [D, "Condomínio", 300, "Despesa", "Moradia", "Vale Alimentação"]])).get_json()
    assert r["importadas"] == 2 and r["fora_da_regra"] == {"Moradia": 1}


def test_compra_parcelada_na_planilha_projeta_no_cartao_da_linha(cliente, ana):
    r = enviar(cliente, ana, planilha([[D, "Notebook PARC 02/05", 349.9, "Despesa", None, "Cartão Meli"]])).get_json()
    assert r["projecoes_criadas"] == 3
    compra = cliente.get("/api/parcelamentos", headers=ana).get_json()[0]
    assert compra["conta"] == "Cartão Meli" and compra["parcelas_restantes"] == 3


def test_linhas_com_problema_sao_listadas_sem_derrubar_o_resto(cliente, ana):
    r = enviar(cliente, ana, planilha([[D, "Boa", 10, "Despesa", None, None], ["não é data", "Ruim", 10, "Despesa", None, None], [D, "Tipo ruim", 10, "Talvez", None, None]])).get_json()
    assert r["importadas"] == 1 and r["linhas_com_erro"] == 2
    assert {e["motivo"] for e in r["erros"]} == {"data inválida", "tipo inválido (use Despesa ou Receita)"}


# ============================================================================= recusas
def test_xlsx_corrompido_e_recusado_com_mensagem_amigavel(cliente, ana):
    r = enviar(cliente, ana, b"isto nao e uma planilha")
    assert r.status_code == 400 and "planilha" in r.get_json()["erro"]


def test_extensao_nao_suportada(cliente, ana):
    r = enviar(cliente, ana, b"x", "planilha.xls")
    assert r.status_code == 400 and "CSV, OFX ou XLSX" in r.get_json()["erro"]


def test_arquivo_acima_de_2_mb_e_recusado(cliente, ana):
    assert enviar(cliente, ana, b"a" * (3 * 1024 * 1024)).status_code == 413


def test_importar_exige_login(cliente):
    r = cliente.post("/api/simulacoes/importar-extrato", content_type="multipart/form-data", data={"arquivo": (io.BytesIO(b"x"), "a.xlsx")})
    assert r.status_code == 401


def test_nao_cria_conta_fantasma_quando_nenhuma_linha_usa_a_conta_da_tela(cliente, ana):
    enviar(cliente, ana, planilha([[D, "Compra", 10, "Despesa", None, "Cartão A"], [D, "Freela", 500, "Receita", None, None]]), conta="Conta Principal")
    assert [c["nome"] for c in cliente.get("/api/contas", headers=ana).get_json()] == ["Cartão A"]
    enviar(cliente, ana, planilha([[D, "Só receita", 100, "Receita", None, None]]), conta="Outra Conta")
    assert [c["nome"] for c in cliente.get("/api/contas", headers=ana).get_json()] == ["Cartão A"]
