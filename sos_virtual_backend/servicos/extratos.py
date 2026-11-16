"""
leitura de extratos bancarios e planilhas (CSV, OFX e XLSX) e deteccao de compras parceladas
aqui ficam so funcoes puras (sem banco de dados), faceis de testar

colunas reconhecidas em CSV e XLSX (maiusculas e acentos nao importam; o nome pode variar um pouco):
  obrigatorias: data, descricao (ou historico, lancamento...), valor
  opcionais:    tipo (Despesa/Receita), categoria, conta (nome do cartao ou conta)
"""
import csv
import html
import io
import re
import unicodedata
import zipfile
from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta

from validacao import VALOR_MAX

LIMITE_LINHAS = 1000            # maximo de lancamentos por arquivo
MAX_PARCELAS = 36               # acima disso tratamos como falso positivo (ex.: "05/12" sendo data)
MAX_DESCOMPACTADO = 30 * 1024 * 1024   # .xlsx e um zip: limita o tamanho DEPOIS de descompactado (protege de "zip bomb")
MAX_ARQUIVOS_ZIP = 300
EXCEL_BASE = datetime(1899, 12, 30)    # as datas do Excel sao contadas em dias a partir daqui


class ExtratoInvalido(Exception):
    """erro de leitura do arquivo, com mensagem segura para mostrar ao usuario"""


# ---------------------------------------------------------------- utilitarios

def _sem_acento(texto):
    base = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in base if not unicodedata.combining(c)).strip().lower()


def _decodificar(conteudo: bytes) -> str:
    # extratos brasileiros vem em UTF-8 ou Latin-1 (latin-1 nunca falha na decodificacao)
    try:
        return conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        return conteudo.decode("latin-1")


FORMATOS_DATA = ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y")


def parse_data(texto):
    """
    aceita dd/mm/aaaa, dd/mm/aa, aaaa-mm-dd e variacoes; e tambem o que vem de planilhas Excel:
    datas de verdade (datetime/date) e o numero de serie do Excel (ex.: 46309). devolve datetime ou None
    """
    if isinstance(texto, bool):
        return None
    if isinstance(texto, datetime):
        data = texto.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    elif isinstance(texto, date):
        data = datetime(texto.year, texto.month, texto.day)
    elif isinstance(texto, (int, float)):
        if not 20000 <= texto <= 80000:           # fora do intervalo de datas plausiveis (anos 1954 a 2118)
            return None
        data = EXCEL_BASE + timedelta(days=int(texto))
    else:
        t = str(texto).strip()
        if not t:
            return None
        t = re.split(r"[ T]", t, maxsplit=1)[0]  # descarta a hora, se houver
        data = None
        for formato in FORMATOS_DATA:
            try:
                data = datetime.strptime(t, formato)
                break
            except ValueError:
                continue
        if data is None:
            return None
    return data if 1990 <= data.year <= 2100 else None


def parse_valor(texto):
    """
    converte valores como 'R$ 1.234,56', '-50.00', '(50,00)' ou '50,00 D' em numero (e aceita numeros do Excel)
    negativo = despesa. devolve None se nao der para entender
    """
    if isinstance(texto, bool):
        return None
    if isinstance(texto, (int, float)):
        numero = float(texto)
        if numero != numero or abs(numero) > VALOR_MAX:
            return None
        return round(numero, 2)

    t = str(texto).strip()
    if not t:
        return None

    negativo = "-" in t or (t.startswith("(") and t.endswith(")")) or t.upper().endswith(" D")
    limpo = re.sub(r"[^\d,.]", "", t)
    if not re.search(r"\d", limpo):
        return None

    if "," in limpo and "." in limpo:
        # o separador que aparece por ultimo e o decimal
        if limpo.rfind(",") > limpo.rfind("."):
            limpo = limpo.replace(".", "").replace(",", ".")
        else:
            limpo = limpo.replace(",", "")
    elif "," in limpo:
        limpo = limpo.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", limpo):
        # "1.234" ou "12.345.678": ponto seguido de 3 digitos e separador de milhar
        limpo = limpo.replace(".", "")

    try:
        numero = float(limpo)
    except ValueError:
        return None
    if numero != numero or numero > VALOR_MAX:
        return None
    numero = round(numero, 2)
    return -numero if negativo else numero


# ------------------------------------------------- tabelas (CSV e XLSX compartilham a leitura)

DESC_NOMES = {"historico", "lancamento", "memo", "estabelecimento", "detalhes",
              "detalhe", "description", "titulo", "nome"}
TIPO_NOMES = {"tipo", "type", "natureza", "d/c", "debito/credito", "tipo de lancamento"}
CATEGORIA_NOMES = {"categoria", "category"}
CONTA_NOMES = {"conta", "cartao", "conta/cartao", "cartao/conta", "conta ou cartao", "cartao ou conta"}

# valor da coluna Tipo (sem acento) -> despesa ou receita
TIPOS = {"despesa": "despesa", "gasto": "despesa", "saida": "despesa", "debito": "despesa", "pagamento": "despesa", "d": "despesa",
         "receita": "receita", "entrada": "receita", "credito": "receita", "ganho": "receita", "c": "receita"}


def _achar_colunas(linha):
    """procura na linha o cabecalho; devolve {campo: indice} ou None se faltar data, descricao ou valor"""
    achados = {}
    for i, celula in enumerate(linha):
        n = _sem_acento("" if celula is None else celula)
        if "data" not in achados and (n.startswith("data") or n == "date"):
            achados["data"] = i
        elif "valor" not in achados and (n.startswith("valor") or n in {"amount", "value", "quantia"}):
            achados["valor"] = i
        elif "desc" not in achados and (n in DESC_NOMES or n.startswith("descri")):
            achados["desc"] = i
        elif "tipo" not in achados and n in TIPO_NOMES:
            achados["tipo"] = i
        elif "categoria" not in achados and n in CATEGORIA_NOMES:
            achados["categoria"] = i
        elif "conta" not in achados and n in CONTA_NOMES:
            achados["conta"] = i
    return achados if {"data", "valor", "desc"} <= set(achados) else None


def _vazio(celula):
    return celula is None or not str(celula).strip()


def _texto_da_celula(celula, maximo):
    return "" if _vazio(celula) else " ".join(str(celula).split())[:maximo]


def _processar_linhas(linhas):
    """
    le linhas (listas de celulas, de CSV ou de XLSX) e devolve (lancamentos, erros)
    cada lancamento: {data, descricao, valor} e, quando a planilha informa, {categoria, conta, tipo_explicito}
    """
    colunas = None
    lancamentos, erros = [], []

    for numero, linha in enumerate(linhas, start=1):
        linha = list(linha)
        if all(_vazio(c) for c in linha):
            continue
        if colunas is None:
            # ignora linhas de apresentacao do banco ate achar o cabecalho
            colunas = _achar_colunas(linha)
            continue
        if len(lancamentos) + len(erros) >= LIMITE_LINHAS:
            raise ExtratoInvalido(f"o arquivo tem linhas demais (máximo {LIMITE_LINHAS})")

        def celula(campo):
            i = colunas.get(campo)
            return linha[i] if i is not None and i < len(linha) else None

        try:
            data = parse_data(linha[colunas["data"]])
            valor = parse_valor(linha[colunas["valor"]])
            descricao = _texto_da_celula(linha[colunas["desc"]], 255)
        except IndexError:
            erros.append({"linha": numero, "motivo": "linha incompleta"})
            continue

        if descricao.upper().startswith("EXEMPLO -"):      # linhas de exemplo do modelo de planilha nunca sao importadas
            continue

        tipo = None
        if not _vazio(celula("tipo")):
            tipo = TIPOS.get(_sem_acento(celula("tipo")))
            if tipo is None:
                erros.append({"linha": numero, "motivo": "tipo inválido (use Despesa ou Receita)"})
                continue

        if data is None:
            erros.append({"linha": numero, "motivo": "data inválida"})
        elif valor is None or valor == 0:
            erros.append({"linha": numero, "motivo": "valor inválido"})
        else:
            if tipo:                                         # com a coluna Tipo, o valor pode vir sempre positivo
                valor = -abs(valor) if tipo == "despesa" else abs(valor)
            lanc = {"data": data, "descricao": descricao or "Sem descrição", "valor": valor}
            if tipo:
                lanc["tipo_explicito"] = True
            categoria, conta = _texto_da_celula(celula("categoria"), 80), _texto_da_celula(celula("conta"), 100)
            if categoria:
                lanc["categoria"] = categoria
            if conta:
                lanc["conta"] = conta
            lancamentos.append(lanc)

    if colunas is None:
        raise ExtratoInvalido("não encontrei as colunas de data, descrição e valor no arquivo")
    return lancamentos, erros


# ------------------------------------------------------------------------ CSV

def ler_csv(texto):
    """devolve (lancamentos, erros)"""
    amostra = texto[:4096]
    delimitador = max([";", ",", "\t"], key=amostra.count)
    return _processar_linhas(csv.reader(io.StringIO(texto), delimiter=delimitador))


# ------------------------------------------------------------------------ XLSX

def _validar_zip(conteudo):
    """um .xlsx e um zip: confere o tamanho descompactado e a senha antes de abrir, para nao esgotar a memoria do servidor"""
    try:
        with zipfile.ZipFile(io.BytesIO(conteudo)) as arquivo:
            itens = arquivo.infolist()
    except zipfile.BadZipFile:
        raise ExtratoInvalido("o arquivo não é uma planilha .xlsx válida (está corrompido ou tem outro formato)")
    if len(itens) > MAX_ARQUIVOS_ZIP or sum(i.file_size for i in itens) > MAX_DESCOMPACTADO:
        raise ExtratoInvalido("a planilha é grande demais depois de descompactada")
    if any(i.flag_bits & 0x1 for i in itens):
        raise ExtratoInvalido("planilhas protegidas por senha não são aceitas")


def ler_xlsx(conteudo: bytes):
    """
    planilha do Excel ou do Google Planilhas. le a aba "Lançamentos" (ou a primeira visivel); formulas sem valor
    calculado vem vazias: salve o arquivo no Excel antes de enviar. o openpyxl usa o defusedxml quando instalado,
    o que barra XML malicioso (entidades externas e "billion laughs")
    """
    _validar_zip(conteudo)
    try:
        from openpyxl import load_workbook
    except ImportError:
        raise ExtratoInvalido("a leitura de planilhas Excel não está disponível neste servidor (instale o openpyxl)")
    try:
        livro = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
        try:
            planilha = (next((w for w in livro.worksheets if _sem_acento(w.title) == "lancamentos"), None)
                        or next((w for w in livro.worksheets if w.sheet_state == "visible"), None))
            if planilha is None:
                raise ExtratoInvalido("a planilha não tem nenhuma aba visível")
            # le so as linhas necessarias: planilhas costumam ter formatacao ate a linha 1 milhao
            linhas = list(planilha.iter_rows(min_row=1, max_row=LIMITE_LINHAS + 60, values_only=True))
            resto = list(planilha.iter_rows(min_row=LIMITE_LINHAS + 61, max_row=LIMITE_LINHAS + 61, values_only=True))
        finally:
            livro.close()
    except ExtratoInvalido:
        raise
    except Exception:
        raise ExtratoInvalido("não consegui ler a planilha. Confira se é um arquivo .xlsx do Excel ou do Google Planilhas")
    if resto and any(not _vazio(c) for c in resto[0]):
        raise ExtratoInvalido(f"o arquivo tem linhas demais (máximo {LIMITE_LINHAS})")
    return _processar_linhas(linhas)


# ------------------------------------------------------------------------ OFX

def _tag(bloco, nome):
    # OFX 1.x nao fecha as tags das folhas (<TRNAMT>-50.00 sem </TRNAMT>), por isso usamos regex
    # e nao um parser de XML: assim tambem nao existe risco de ataque por entidades externas (XXE)
    m = re.search(rf"<{nome}>\s*([^<\r\n]*)", bloco, flags=re.I)
    return html.unescape(m.group(1).strip()) if m else ""


def ler_ofx(texto):
    lancamentos, erros = [], []
    partes = re.split(r"<STMTTRN>", texto, flags=re.I)[1:]

    for numero, parte in enumerate(partes, start=1):
        if len(lancamentos) + len(erros) >= LIMITE_LINHAS:
            raise ExtratoInvalido(f"o arquivo tem linhas demais (máximo {LIMITE_LINHAS})")

        bloco = re.split(r"</STMTTRN>|</BANKTRANLIST>", parte, maxsplit=1, flags=re.I)[0]

        achou = re.match(r"(\d{4})(\d{2})(\d{2})", _tag(bloco, "DTPOSTED"))
        data = parse_data("-".join(achou.groups())) if achou else None

        try:
            valor = float(_tag(bloco, "TRNAMT").replace(",", "."))
        except ValueError:
            valor = None
        if valor is not None and (valor != valor or abs(valor) > VALOR_MAX):
            valor = None

        # alguns bancos mandam o nome do estabelecimento em NAME e o detalhe em MEMO: juntamos os dois
        nome, memo = _tag(bloco, "NAME"), _tag(bloco, "MEMO")
        if nome and memo and nome.lower() not in memo.lower():
            descricao = f"{nome} {memo}"
        else:
            descricao = memo or nome
        descricao = " ".join(descricao.split())[:255]

        if data is None:
            erros.append({"linha": numero, "motivo": "data inválida"})
        elif not valor:
            erros.append({"linha": numero, "motivo": "valor inválido"})
        else:
            lancamentos.append({"data": data, "descricao": descricao or "Sem descrição",
                                "valor": round(valor, 2)})

    return lancamentos, erros


def ler_extrato(extensao, conteudo: bytes):
    """ponto de entrada: escolhe o leitor pela extensao (csv, ofx ou xlsx) e valida o resultado"""
    if extensao == "xlsx":
        lancamentos, erros = ler_xlsx(conteudo)
    else:
        texto = _decodificar(conteudo)
        lancamentos, erros = ler_csv(texto) if extensao == "csv" else ler_ofx(texto)
    if not lancamentos:
        raise ExtratoInvalido("nenhuma transação válida encontrada no arquivo")
    return lancamentos, erros


# ------------------------------------------------------------------- parcelas

# "Parc 02/05", "PARCELA 2 DE 5", "parc.3/6"
RE_PARC_PALAVRA = re.compile(r"(?i)\bparc(?:ela)?\.?\s*(\d{1,2})\s*(?:/|de)\s*(\d{1,2})\b")
# "1/3" solto na descricao (sem ser parte de uma data como 05/10/2026)
RE_PARC_BARRA = re.compile(r"(?<![\d/])(\d{1,2})\s*/\s*(\d{1,2})(?![\d/])")


def detectar_parcela(descricao):
    """devolve (parcela_atual, total) se a descricao indicar compra parcelada, senao None"""
    for regex in (RE_PARC_PALAVRA, RE_PARC_BARRA):
        for m in regex.finditer(descricao):
            atual, total = int(m.group(1)), int(m.group(2))
            if 1 <= atual <= total <= MAX_PARCELAS and total >= 2:
                return atual, total
    return None


def limpar_descricao_parcela(descricao):
    """
    nome da compra sem o marcador de parcela, para mostrar ao usuario ao lado da coluna "parcela":
    "TV 55 PARC 02/06" -> "TV 55"; "Notebook (2/10)" -> "Notebook"; datas como 05/10/2026 ficam intactas
    """
    base = RE_PARC_PALAVRA.sub(" ", descricao)
    base = RE_PARC_BARRA.sub(" ", base)
    base = re.sub(r"\(\s*\)|\[\s*\]", " ", base)               # parenteses vazios que sobraram
    base = " ".join(base.split()).strip(" -–—:;,.")             # separadores soltos nas pontas
    return base or descricao


def chave_compra(descricao, total):
    """identifica a mesma compra entre extratos de meses diferentes (descricao sem o marcador de parcela)"""
    base = RE_PARC_PALAVRA.sub(" ", descricao)
    base = RE_PARC_BARRA.sub(" ", base)
    base = " ".join(base.upper().split())[:200]
    return f"{base}|{total}"


def calcular_parcelas(valor_abs, atual, total, valor_e_total):
    """
    devolve a lista com o valor de cada parcela (indice 0 = parcela 1)
    - valor_e_total=False: o valor do extrato ja e o de UMA parcela (o mais comum nos bancos)
    - valor_e_total=True: o valor e o total da compra e e dividido entre as parcelas;
      a divisao e feita em centavos e o resto vai para as primeiras parcelas, assim a soma bate
    """
    if not valor_e_total:
        return [round(valor_abs, 2)] * total

    centavos = int(round(valor_abs * 100))
    base, resto = divmod(centavos, total)
    valores = []
    for i in range(total):
        valores.append((base + (1 if i < resto else 0)) / 100)
    return valores


def gerar_projecoes(data_base, atual, total, valores):
    """
    cria as parcelas futuras: um lancamento por mes, avancando a data com relativedelta
    (que ja cuida de fim de mes: 31/01 + 1 mes = 28/02)
    """
    projecoes = []
    for numero in range(atual + 1, total + 1):
        projecoes.append({
            "numero": numero,
            "data": data_base + relativedelta(months=numero - atual),
            "valor": valores[numero - 1],
        })
    return projecoes
