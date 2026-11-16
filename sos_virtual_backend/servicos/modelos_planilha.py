"""
modelo de planilha para importar lancamentos (Excel e CSV)

colunas:  Data | Descrição | Valor | Tipo | Categoria | Conta
  obrigatorias: Data, Descrição, Valor.  opcionais: Tipo, Categoria, Conta (veja a aba "Instruções")

as linhas de EXEMPLO (descricao comecando com "EXEMPLO -") ficam so na aba de instrucoes, e o importador
as ignora de qualquer jeito: esquecer um exemplo no arquivo nunca vira lancamento de verdade
"""
import csv
import io

from servicos.financeiro import CATEGORIAS
from servicos.tempo import hoje

COLUNAS = ["Data", "Descrição", "Valor", "Tipo", "Categoria", "Conta"]
NOME_ARQUIVO = "modelo-sos-virtual"
LINHAS_FORMATADAS = 1000               # o mesmo limite de lancamentos por arquivo do importador
CATEGORIAS_DO_MODELO = CATEGORIAS + ["Salário"]


def _exemplos():
    """tres linhas de exemplo, com datas do mes atual"""
    ano_mes = hoje().strftime("%m/%Y")
    return [
        (f"05/{ano_mes}", "EXEMPLO - Supermercado", "250,00", "Despesa", "Alimentação", "Cartão Nubank"),
        (f"12/{ano_mes}", "EXEMPLO - Notebook PARC 02/10", "349,90", "Despesa", "", "Cartão Nubank"),
        (f"20/{ano_mes}", "EXEMPLO - Salário", "4.500,00", "Receita", "Salário", ""),
    ]


def gerar_modelo_csv():
    """CSV como o Excel brasileiro espera: separador ';', decimal com virgula e UTF-8 com BOM (acentos corretos ao abrir)"""
    saida = io.StringIO(newline="")
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(COLUNAS)
    escritor.writerows(_exemplos())
    return ("\ufeff" + saida.getvalue()).encode("utf-8")


def gerar_modelo_xlsx(contas=()):
    """
    planilha do Excel com 3 abas: "Lançamentos" (vazia, com formatos e listas suspensas), "Instruções" e "Listas" (oculta).
    `contas`: nomes das contas e cartoes do usuario, para a lista suspensa da coluna Conta
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    contas = [c for c in contas if c][:100]
    livro = Workbook()

    # ---------------- aba de lancamentos
    folha = livro.active
    folha.title = "Lançamentos"
    folha.append(COLUNAS)
    for coluna, largura in zip("ABCDEF", (14, 38, 14, 12, 18, 24)):
        folha.column_dimensions[coluna].width = largura
    for celula in folha[1]:
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = PatternFill("solid", fgColor="0E2A47")
        celula.alignment = Alignment(horizontal="center", vertical="center")
    folha.row_dimensions[1].height = 22
    folha.freeze_panes = "A2"
    for linha in range(2, LINHAS_FORMATADAS + 2):
        folha.cell(linha, 1).number_format = "DD/MM/YYYY"
        folha.cell(linha, 3).number_format = "#,##0.00"

    # ---------------- aba oculta com as listas das listas suspensas
    listas = livro.create_sheet("Listas")
    listas["A1"], listas["B1"], listas["C1"] = "Categorias", "Contas", "Tipos"
    for i, nome in enumerate(CATEGORIAS_DO_MODELO, start=2):
        listas.cell(i, 1, nome)
    for i, nome in enumerate(contas, start=2):
        listas.cell(i, 2, nome)
    listas["C2"], listas["C3"] = "Despesa", "Receita"
    listas.sheet_state = "hidden"

    fim = LINHAS_FORMATADAS + 1
    tipo = DataValidation(type="list", formula1="=Listas!$C$2:$C$3", allow_blank=True, showErrorMessage=True,
                          errorTitle="Tipo", error="Escolha Despesa ou Receita.")
    categoria = DataValidation(type="list", formula1=f"=Listas!$A$2:$A${len(CATEGORIAS_DO_MODELO) + 1}", allow_blank=True,
                               showErrorMessage=True, errorTitle="Categoria", error="Escolha uma categoria da lista (ou deixe em branco).")
    tipo.add(f"D2:D{fim}")
    categoria.add(f"E2:E{fim}")
    folha.add_data_validation(tipo)
    folha.add_data_validation(categoria)
    if contas:
        # aviso (e nao bloqueio): um nome novo cria uma conta nova na importacao
        conta = DataValidation(type="list", formula1=f"=Listas!$B$2:$B${len(contas) + 1}", allow_blank=True, errorStyle="warning",
                               showErrorMessage=True, errorTitle="Conta", error="Esse nome não está na sua lista: uma conta nova será criada na importação.")
        conta.add(f"F2:F{fim}")
        folha.add_data_validation(conta)

    # ---------------- aba de instrucoes
    ajuda = livro.create_sheet("Instruções", 1)
    ajuda.column_dimensions["A"].width = 16
    ajuda.column_dimensions["B"].width = 12
    ajuda.column_dimensions["C"].width = 90
    ajuda["A1"] = "Como preencher o modelo do SOS Virtual"
    ajuda["A1"].font = Font(bold=True, size=14)
    ajuda["A2"] = "Preencha a aba \"Lançamentos\", uma linha por gasto ou receita, sem mudar os títulos da primeira linha. Depois envie em Transações > Importar extrato."

    ajuda.append([])
    ajuda.append(["Coluna", "Obrigatória", "O que colocar"])
    for celula in ajuda[4]:
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = PatternFill("solid", fgColor="0E2A47")
    regras = [
        ("Data", "Sim", "Dia da compra, no formato 15/10/2026 (ou 2026-10-15). Pode ser uma data do Excel."),
        ("Descrição", "Sim", "O que foi comprado ou onde. Para compra parcelada, escreva a parcela na descrição: \"Notebook PARC 02/10\" "
                             "(o sistema projeta as parcelas dos meses seguintes)."),
        ("Valor", "Sim", "Valor em reais, como 250,00. Se a coluna Tipo estiver preenchida, use sempre valor positivo. "
                         "Sem Tipo: despesas com sinal de menos (-250,00) e receitas positivas."),
        ("Tipo", "Não", "Despesa ou Receita (escolha na lista). Em branco, vale o sinal do valor."),
        ("Categoria", "Não", "Escolha na lista. Em branco, o sistema descobre pela descrição. Salário só vale para receitas."),
        ("Conta", "Não", "Cartão ou conta em que a compra foi paga. Suas contas aparecem na lista; um nome novo cria a conta. "
                         "Em branco, usa a conta escolhida na tela de importação. Receitas não têm conta."),
    ]
    for r in regras:
        ajuda.append(list(r))

    ajuda.append([])
    ajuda.append(["Regras"])
    ajuda.cell(ajuda.max_row, 1).font = Font(bold=True)
    for texto in (
        "Máximo de 1.000 linhas e 2 MB por arquivo.",
        "O que já foi importado antes (mesma data, descrição e valor) é ignorado, então você pode enviar o arquivo de novo.",
        "Linhas cuja descrição começa com \"EXEMPLO -\" são ignoradas.",
        "Se usar fórmulas, salve o arquivo no Excel antes de enviar (o sistema lê os valores já calculados).",
        "Uma conta que só aceita certas categorias (um vale) recebe o lançamento mesmo assim; o sistema avisa o que ficou fora das categorias dela.",
    ):
        ajuda.append([None, None, texto])

    ajuda.append([])
    ajuda.append(["Exemplos (não são importados)"])
    ajuda.cell(ajuda.max_row, 1).font = Font(bold=True)
    ajuda.append(COLUNAS)
    for celula in ajuda[ajuda.max_row]:
        celula.font = Font(bold=True)
    for exemplo in _exemplos():
        ajuda.append(list(exemplo))
    for linha in ajuda.iter_rows():
        for celula in linha:
            celula.alignment = Alignment(wrap_text=True, vertical="top")

    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()
