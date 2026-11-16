"""
testes da importacao de planilhas (CSV e XLSX) e do modelo de planilha
rodar: py -m pytest tests/test_planilhas.py -v   (nao precisa de banco)
"""
import io
import time
import zipfile
from datetime import date, datetime, timedelta

import pytest
from openpyxl import Workbook, load_workbook

from servicos.extratos import EXCEL_BASE, ExtratoInvalido, MAX_DESCOMPACTADO, ler_extrato, parse_data, parse_valor
from servicos.modelos_planilha import COLUNAS, gerar_modelo_csv, gerar_modelo_xlsx


def xlsx(linhas, titulo="Lançamentos", outras_abas=()):
    """monta um .xlsx na memoria: `linhas` na aba principal; outras_abas = [(titulo, linhas, estado)]"""
    livro = Workbook()
    folha = livro.active
    folha.title = titulo
    for linha in linhas:
        folha.append(list(linha))
    for nome, conteudo, estado in outras_abas:
        outra = livro.create_sheet(nome)
        for linha in conteudo:
            outra.append(list(linha))
        outra.sheet_state = estado
    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()


CABECALHO = ["Data", "Descrição", "Valor", "Tipo", "Categoria", "Conta"]


# ===================================================================== valores e datas do Excel
def test_data_de_verdade_do_excel_e_numero_de_serie():
    assert parse_data(datetime(2026, 10, 15, 13, 45)) == datetime(2026, 10, 15)
    assert parse_data(date(2026, 10, 15)) == datetime(2026, 10, 15)
    serial = (datetime(2026, 10, 15) - EXCEL_BASE).days
    assert parse_data(serial) == datetime(2026, 10, 15) and parse_data(float(serial)) == datetime(2026, 10, 15)


@pytest.mark.parametrize("entrada", [5, 100, 3_000_000, True, False, None, float("nan"), datetime(1800, 1, 1), datetime(2300, 1, 1)])
def test_datas_impossiveis(entrada):
    assert parse_data(entrada) is None


def test_valor_numerico_do_excel():
    assert parse_valor(250.5) == 250.5 and parse_valor(-12) == -12.0 and parse_valor(1 / 3) == 0.33
    assert parse_valor(True) is None and parse_valor(float("nan")) is None and parse_valor(float("inf")) is None and parse_valor(10 ** 12) is None


# ==================================================================================== CSV e XLSX
def test_csv_com_as_colunas_novas():
    csv = "Data;Descrição;Valor;Tipo;Categoria;Conta\n15/10/2026;Supermercado;250,00;Despesa;Alimentação;Cartão Nubank\n20/10/2026;Salário;4.500,00;Receita;Salário;\n"
    lanc, erros = ler_extrato("csv", csv.encode())
    assert erros == [] and lanc[0] == {"data": datetime(2026, 10, 15), "descricao": "Supermercado", "valor": -250.0, "tipo_explicito": True, "categoria": "Alimentação", "conta": "Cartão Nubank"}
    assert lanc[1]["valor"] == 4500.0 and "conta" not in lanc[1]


def test_xlsx_le_datas_e_numeros_de_verdade():
    dados = xlsx([CABECALHO, [datetime(2026, 10, 15), "Supermercado", 250.5, "Despesa", "Alimentação", "Cartão Nubank"], [datetime(2026, 10, 20), "Salário", 4500, "Receita", None, None]])
    lanc, erros = ler_extrato("xlsx", dados)
    assert erros == [] and [(l["descricao"], l["valor"]) for l in lanc] == [("Supermercado", -250.5), ("Salário", 4500.0)]
    assert lanc[0]["categoria"] == "Alimentação" and lanc[0]["conta"] == "Cartão Nubank" and "categoria" not in lanc[1]


def test_xlsx_com_texto_no_lugar_de_numero_e_data():
    lanc, _ = ler_extrato("xlsx", xlsx([["Data", "Descrição", "Valor"], ["05/10/2026", "Padaria", "-R$ 1.234,56"], [46309, "Farmácia", "(80,00)"]]))
    assert [(l["data"].day, l["valor"]) for l in lanc] == [(5, -1234.56), (parse_data(46309).day, -80.0)]


@pytest.mark.parametrize("tipo,sinal", [("Despesa", -1), ("DESPESA", -1), ("saída", -1), ("Débito", -1), ("gasto", -1), ("Receita", 1), ("entrada", 1), ("Crédito", 1), ("C", 1), ("D", -1)])
def test_coluna_tipo_define_o_sinal_com_valor_positivo(tipo, sinal):
    lanc, _ = ler_extrato("xlsx", xlsx([CABECALHO, [datetime(2026, 10, 1), "X", 100, tipo, None, None]]))
    assert lanc[0]["valor"] == 100 * sinal and lanc[0]["tipo_explicito"] is True


def test_tipo_ignora_o_sinal_digitado_e_vazio_vale_o_sinal():
    lanc, _ = ler_extrato("xlsx", xlsx([CABECALHO, [datetime(2026, 10, 1), "A", -100, "Despesa", None, None], [datetime(2026, 10, 1), "B", -100, "Receita", None, None],
                                        [datetime(2026, 10, 1), "C", -100, None, None, None]]))
    assert [l["valor"] for l in lanc] == [-100, 100, -100] and "tipo_explicito" not in lanc[2]


def test_tipo_invalido_vira_erro_da_linha_sem_derrubar_as_outras():
    lanc, erros = ler_extrato("xlsx", xlsx([CABECALHO, [datetime(2026, 10, 1), "A", 10, "Talvez", None, None], [datetime(2026, 10, 2), "B", 20, "Despesa", None, None]]))
    assert len(lanc) == 1 and erros == [{"linha": 2, "motivo": "tipo inválido (use Despesa ou Receita)"}]


def test_linhas_de_exemplo_sao_ignoradas():
    lanc, _ = ler_extrato("xlsx", xlsx([CABECALHO, [datetime(2026, 10, 1), "EXEMPLO - Supermercado", 250, "Despesa", None, None], [datetime(2026, 10, 2), "exemplo - outro", 5, None, None, None],
                                         [datetime(2026, 10, 3), "Compra de verdade", 30, "Despesa", None, None]]))
    assert [l["descricao"] for l in lanc] == ["Compra de verdade"]


@pytest.mark.parametrize("cabecalho", [["data", "DESCRICAO", "valor", "tipo", "categoria", "cartao"], ["Data", "Histórico", "Valor (R$)", "Tipo", "Categoria", "Conta/Cartão"],
                                       ["DATA", "Lançamento", "VALOR", "Natureza", "CATEGORIA", "Cartão ou conta"]])
def test_nomes_de_coluna_variados(cabecalho):
    lanc, _ = ler_extrato("xlsx", xlsx([cabecalho, [datetime(2026, 10, 1), "X", 10, "Despesa", "Lazer", "Meu Cartão"]]))
    assert lanc[0]["categoria"] == "Lazer" and lanc[0]["conta"] == "Meu Cartão"


def test_colunas_opcionais_podem_nao_existir_e_linhas_vazias_sao_puladas():
    lanc, erros = ler_extrato("xlsx", xlsx([["Banco X"], [], ["Data", "Descrição", "Valor"], [datetime(2026, 10, 1), "A", -10], [None, None, None], [datetime(2026, 10, 2), "B", -20]]))
    assert [l["descricao"] for l in lanc] == ["A", "B"] and erros == []


def test_faltando_coluna_obrigatoria():
    for linhas in ([["Data", "Descrição"], [datetime(2026, 10, 1), "X"]], [["Descrição", "Valor"], ["X", 1]]):
        with pytest.raises(ExtratoInvalido, match="colunas de data, descrição e valor"):
            ler_extrato("xlsx", xlsx(linhas))


def test_escolhe_a_aba_lancamentos_mesmo_que_nao_seja_a_primeira():
    dados = xlsx([["Resumo"], ["nada aqui"]], titulo="Resumo", outras_abas=[("Lançamentos", [["Data", "Descrição", "Valor"], [datetime(2026, 10, 1), "Certo", -5]], "visible")])
    assert ler_extrato("xlsx", dados)[0][0]["descricao"] == "Certo"


def test_sem_aba_lancamentos_usa_a_primeira_visivel_e_ignora_abas_ocultas():
    dados = xlsx([["Data", "Descrição", "Valor"], [datetime(2026, 10, 1), "Da aba visivel", -5]], titulo="Gastos",
                 outras_abas=[("Oculta", [["Data", "Descrição", "Valor"], [datetime(2026, 10, 1), "Da aba oculta", -9]], "hidden")])
    assert ler_extrato("xlsx", dados)[0][0]["descricao"] == "Da aba visivel"


def test_limite_de_mil_linhas():
    mil = [CABECALHO] + [[datetime(2026, 10, 1), f"L{i}", 1, "Despesa", None, None] for i in range(1000)]
    assert len(ler_extrato("xlsx", xlsx(mil))[0]) == 1000
    with pytest.raises(ExtratoInvalido, match="linhas demais"):
        ler_extrato("xlsx", xlsx(mil + [[datetime(2026, 10, 1), "a mais", 1, "Despesa", None, None]]))


def test_planilha_sem_lancamentos_validos():
    with pytest.raises(ExtratoInvalido, match="nenhuma transação válida"):
        ler_extrato("xlsx", xlsx([CABECALHO]))


# ===================================================================== modelo de planilha (CSV)
def test_modelo_csv_tem_bom_cabecalho_e_exemplos():
    dados = gerar_modelo_csv()
    assert dados.startswith(b"\xef\xbb\xbf")
    linhas = dados.decode("utf-8-sig").splitlines()
    assert linhas[0] == ";".join(COLUNAS) and len(linhas) == 4 and all(l.split(";")[1].startswith("EXEMPLO -") for l in linhas[1:])


def test_modelo_csv_sem_preencher_nao_importa_nada():
    with pytest.raises(ExtratoInvalido, match="nenhuma transação válida"):
        ler_extrato("csv", gerar_modelo_csv())


def test_modelo_csv_com_linhas_do_usuario_importa_so_as_dele():
    preenchido = gerar_modelo_csv() + "02/10/2026;Padaria;18,50;Despesa;Alimentação;Cartão Itaú\r\n".encode("utf-8")
    lanc, erros = ler_extrato("csv", preenchido)
    assert erros == [] and [(l["descricao"], l["valor"], l["conta"]) for l in lanc] == [("Padaria", -18.5, "Cartão Itaú")]


# ===================================================================== modelo de planilha (Excel)
def test_modelo_xlsx_estrutura():
    livro = load_workbook(io.BytesIO(gerar_modelo_xlsx(["Cartão Nubank", "Vale Refeição"])))
    assert [(w.title, w.sheet_state) for w in livro.worksheets] == [("Lançamentos", "visible"), ("Instruções", "visible"), ("Listas", "hidden")]
    folha = livro["Lançamentos"]
    assert [c.value for c in folha[1]] == COLUNAS and folha.freeze_panes == "A2"
    assert folha["A2"].number_format == "DD/MM/YYYY" and folha["C2"].number_format == "#,##0.00"
    assert folha.max_row == 1001 and all(folha.cell(2, c).value is None for c in range(1, 7))       # a aba de lancamentos vem vazia
    listas = livro["Listas"]
    assert [listas.cell(i, 2).value for i in (2, 3)] == ["Cartão Nubank", "Vale Refeição"] and "Restaurante" in [listas.cell(i, 1).value for i in range(2, 14)]


def test_modelo_xlsx_listas_suspensas():
    folha = load_workbook(io.BytesIO(gerar_modelo_xlsx(["Cartão Nubank"])))["Lançamentos"]
    validacoes = {str(v.sqref): v for v in folha.data_validations.dataValidation}
    assert set(validacoes) == {"D2:D1001", "E2:E1001", "F2:F1001"}
    assert validacoes["D2:D1001"].formula1 == "=Listas!$C$2:$C$3" and validacoes["F2:F1001"].errorStyle == "warning"
    assert validacoes["E2:E1001"].errorStyle in (None, "stop")


def test_modelo_xlsx_sem_contas_nao_cria_a_lista_de_contas():
    folha = load_workbook(io.BytesIO(gerar_modelo_xlsx([])))["Lançamentos"]
    assert {str(v.sqref) for v in folha.data_validations.dataValidation} == {"D2:D1001", "E2:E1001"}


def test_modelo_xlsx_instrucoes_explicam_as_colunas():
    ajuda = load_workbook(io.BytesIO(gerar_modelo_xlsx([])))["Instruções"]
    texto = " ".join(str(c.value) for linha in ajuda.iter_rows() for c in linha if c.value)
    for esperado in ("Data", "Descrição", "Valor", "Tipo", "Categoria", "Conta", "PARC 02/10", "EXEMPLO -", "1.000 linhas", "Importar extrato"):
        assert esperado in texto


def test_modelo_xlsx_sem_preencher_nao_importa_nada_e_os_exemplos_nunca_entram():
    with pytest.raises(ExtratoInvalido, match="nenhuma transação válida"):
        ler_extrato("xlsx", gerar_modelo_xlsx(["Cartão Nubank"]))


def test_ida_e_volta_preencher_o_modelo_e_importar():
    livro = load_workbook(io.BytesIO(gerar_modelo_xlsx(["Cartão Nubank"])))
    folha = livro["Lançamentos"]
    for linha in ([datetime(2026, 10, 15), "Supermercado", 250.0, "Despesa", "Alimentação", "Cartão Nubank"], [datetime(2026, 10, 16), "Notebook PARC 02/10", 349.9, "Despesa", None, "Cartão Nubank"],
                  [datetime(2026, 10, 20), "Salário", 4500, "Receita", "Salário", None]):
        folha.append(linha)         # a aba de lancamentos esta "vazia" ate a linha 1001; o openpyxl acrescenta depois do ultimo uso
    saida = io.BytesIO()
    livro.save(saida)
    lanc, erros = ler_extrato("xlsx", saida.getvalue())
    assert erros == [] and [(l["descricao"], l["valor"]) for l in lanc] == [("Supermercado", -250.0), ("Notebook PARC 02/10", -349.9), ("Salário", 4500.0)]


# ============================================================================ seguranca do .xlsx
@pytest.mark.parametrize("lixo", [b"", b"isto nao e uma planilha", b"PK\x03\x04quebrado", bytes(range(256)) * 10])
def test_arquivo_corrompido_vira_erro_amigavel(lixo):
    with pytest.raises(ExtratoInvalido):
        ler_extrato("xlsx", lixo)


def test_csv_renomeado_para_xlsx_e_recusado():
    with pytest.raises(ExtratoInvalido, match="não é uma planilha"):
        ler_extrato("xlsx", "Data;Descrição;Valor\n01/10/2026;X;-1,00\n".encode())


def test_zip_bomb_e_recusado_sem_descompactar():
    corpo = io.BytesIO()
    with zipfile.ZipFile(corpo, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/worksheets/sheet1.xml", b"\0" * (MAX_DESCOMPACTADO + 1024 * 1024))       # ~31 MB de zeros: poucos KB comprimidos
    assert len(corpo.getvalue()) < 100_000
    inicio = time.time()
    with pytest.raises(ExtratoInvalido, match="grande demais"):
        ler_extrato("xlsx", corpo.getvalue())
    assert time.time() - inicio < 2


def test_zip_com_arquivos_demais_e_recusado():
    corpo = io.BytesIO()
    with zipfile.ZipFile(corpo, "w") as z:
        for i in range(400):
            z.writestr(f"f{i}.txt", "x")
    with pytest.raises(ExtratoInvalido, match="grande demais"):
        ler_extrato("xlsx", corpo.getvalue())


def test_planilha_protegida_por_senha_e_recusada():
    corpo = io.BytesIO()
    with zipfile.ZipFile(corpo, "w") as z:
        z.writestr("xl/workbook.xml", b"x")
    dados = bytearray(corpo.getvalue())
    dados[dados.find(b"PK\x01\x02") + 8] |= 0x1          # indicador de "criptografado" no diretorio central, como num zip com senha de verdade
    assert zipfile.ZipFile(io.BytesIO(bytes(dados))).infolist()[0].flag_bits & 0x1
    with pytest.raises(ExtratoInvalido, match="senha"):
        ler_extrato("xlsx", bytes(dados))


def trocar_membro(dados, membro, novo_conteudo):
    entrada, saida = zipfile.ZipFile(io.BytesIO(dados)), io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as z:
        for item in entrada.infolist():
            z.writestr(item.filename, novo_conteudo if item.filename == membro else entrada.read(item.filename))
    return saida.getvalue()


def xml_da_planilha(dados):
    return zipfile.ZipFile(io.BytesIO(dados)).read("xl/worksheets/sheet1.xml").decode()


def test_controle_a_planilha_reempacotada_sem_ataque_abre_normalmente():
    """garante que os testes de XML malicioso abaixo falham pelo motivo certo, e nao por um erro qualquer de empacotamento"""
    original = xlsx([["Data", "Descrição", "Valor"], [datetime(2026, 10, 1), "Normal", -5]])
    reempacotado = trocar_membro(original, "xl/worksheets/sheet1.xml", xml_da_planilha(original).encode())
    assert ler_extrato("xlsx", reempacotado)[0][0]["descricao"] == "Normal"


@pytest.mark.parametrize("doctype", [
    '<!DOCTYPE x [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>',                                            # entidade externa (XXE)
    '<!DOCTYPE x [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>',                # expansao de entidades ("billion laughs")
])
def test_xml_malicioso_dentro_da_planilha_e_barrado(doctype):
    original = xlsx([["Data", "Descrição", "Valor"], [datetime(2026, 10, 1), "Normal", -5]])
    xml = xml_da_planilha(original)
    malicioso = xml.replace("<worksheet", doctype + "<worksheet", 1) if xml.startswith("<?xml") is False else xml.replace("?>", "?>" + doctype, 1)
    assert doctype in malicioso
    with pytest.raises(ExtratoInvalido, match="não consegui ler a planilha"):
        ler_extrato("xlsx", trocar_membro(original, "xl/worksheets/sheet1.xml", malicioso.encode()))
