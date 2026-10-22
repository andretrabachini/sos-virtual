"""
leitura de extratos bancarios (CSV e OFX) e deteccao de compras parceladas
aqui ficam so funcoes puras (sem banco de dados), faceis de testar
"""
import csv
import html
import io
import re
import unicodedata
from datetime import datetime

from dateutil.relativedelta import relativedelta

from validacao import VALOR_MAX

LIMITE_LINHAS = 1000   # maximo de lancamentos por arquivo
MAX_PARCELAS = 36      # acima disso tratamos como falso positivo (ex.: "05/12" sendo data)


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
    """aceita dd/mm/aaaa, dd/mm/aa, aaaa-mm-dd e variacoes; devolve datetime ou None"""
    t = str(texto).strip()
    if not t:
        return None
    t = re.split(r"[ T]", t, maxsplit=1)[0]  # descarta a hora, se houver
    for formato in FORMATOS_DATA:
        try:
            data = datetime.strptime(t, formato)
        except ValueError:
            continue
        return data if 1990 <= data.year <= 2100 else None
    return None


def parse_valor(texto):
    """
    converte valores como 'R$ 1.234,56', '-50.00', '(50,00)' ou '50,00 D' em numero
    negativo = despesa. devolve None se nao der para entender
    """
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


# ------------------------------------------------------------------------ CSV

DESC_NOMES = {"historico", "lancamento", "memo", "estabelecimento", "detalhes",
              "detalhe", "description", "titulo", "nome"}


def _achar_colunas(linha):
    """procura na linha o cabecalho (colunas de data, descricao e valor)"""
    nomes = [_sem_acento(c) for c in linha]
    achados = {}
    for i, n in enumerate(nomes):
        if "data" not in achados and (n.startswith("data") or n == "date"):
            achados["data"] = i
        elif "valor" not in achados and (n.startswith("valor") or n in {"amount", "value", "quantia"}):
            achados["valor"] = i
        elif "desc" not in achados and (n in DESC_NOMES or n.startswith("descri")):
            achados["desc"] = i
    return achados if len(achados) == 3 else None


def ler_csv(texto):
    """devolve (lancamentos, erros). cada lancamento: {data, descricao, valor}"""
    amostra = texto[:4096]
    delimitador = max([";", ",", "\t"], key=amostra.count)

    leitor = csv.reader(io.StringIO(texto), delimiter=delimitador)
    colunas = None
    lancamentos, erros = [], []

    for numero, linha in enumerate(leitor, start=1):
        if not any(c.strip() for c in linha):
            continue
        if colunas is None:
            # ignora linhas de apresentacao do banco ate achar o cabecalho
            colunas = _achar_colunas(linha)
            continue
        if len(lancamentos) + len(erros) >= LIMITE_LINHAS:
            raise ExtratoInvalido(f"o arquivo tem linhas demais (máximo {LIMITE_LINHAS})")

        try:
            data = parse_data(linha[colunas["data"]])
            valor = parse_valor(linha[colunas["valor"]])
            descricao = " ".join(linha[colunas["desc"]].split())[:255]
        except IndexError:
            erros.append({"linha": numero, "motivo": "linha incompleta"})
            continue

        if data is None:
            erros.append({"linha": numero, "motivo": "data inválida"})
        elif valor is None or valor == 0:
            erros.append({"linha": numero, "motivo": "valor inválido"})
        else:
            lancamentos.append({"data": data, "descricao": descricao or "Sem descrição", "valor": valor})

    if colunas is None:
        raise ExtratoInvalido("não encontrei as colunas de data, descrição e valor no CSV")
    return lancamentos, erros


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
    """ponto de entrada: escolhe o leitor pela extensao e valida o resultado"""
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
