"""
interpretacao de frases em portugues para o assistente: funcoes puras (sem banco de dados), faceis de testar
o assistente roda no proprio servidor e nao envia nenhum dado a servicos externos de IA

regra de ouro: na duvida, perguntar. registrar um lancamento errado e pior do que fazer uma pergunta a mais
"""
import re
import unicodedata
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from servicos.categorizacao import detectar_categoria, normalizar
from servicos.financeiro import CATEGORIAS
from validacao import VALOR_MAX

MESES = ["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
MESES_COM_ACENTO = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
DIAS_SEMANA = {"segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5, "domingo": 6}


# ---------------------------------------------------------------- utilitarios

def alinhado(texto):
    """minuscula e sem acento, com exatamente o mesmo comprimento do original (as posicoes valem para os dois textos)"""
    saida = []
    for c in str(texto):
        base = "".join(x for x in unicodedata.normalize("NFKD", c) if not unicodedata.combining(x))
        saida.append((base[:1] or c).lower()[:1])
    return "".join(saida)


def brl(valor):
    """1234.5 -> 'R$ 1.234,50'"""
    texto = f"{abs(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-" if valor < 0 else "") + "R$ " + texto


def nome_do_mes(mes):
    """'2026-11' -> 'novembro de 2026'"""
    return f"{MESES_COM_ACENTO[int(mes[5:7]) - 1]} de {mes[:4]}"


def percentual(parte, total):
    return round(100 * parte / total) if total else 0


# ---------------------------------------------------------------------- valor

_NUM = r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?"
_RE_VALOR = re.compile(
    rf"(?<![\w.,/:-])(?P<rs>r\$\s*)?(?P<num>{_NUM})(?P<mil>\s*mil\b)?(?P<reais>\s*(?:reais|real|conto|contos|pila|pilas)\b)?"
)
# o que, logo depois do numero, mostra que ele NAO e um valor em dinheiro (3x, 2 parcelas, 14h, 10 de novembro, 15/10...)
_RE_NAO_VALOR = re.compile(
    r"\s*(?:x\b|vezes\b|vez\b|parcelas?\b|/\s*\d|-\s*\d|:|%|h\b|hs\b|horas?\b|dias\b|dia\b(?!\s*\d)|semanas?\b|mes(?:es)?\b|anos?\b|"
    rf"de\s+(?:{'|'.join(MESES)})\b)"
)
_RE_ANO_APOS_MES = re.compile(rf"(?:{'|'.join(MESES)})\s+de\s*$")
_PALAVRAS_DE_PRECO = {"por", "custou", "custando", "valor", "total"}


def _numero(texto):
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", texto):
        texto = texto.replace(".", "")
    return float(texto)


def extrair_valor(texto):
    """
    procura o valor em dinheiro da frase. devolve (status, valor, (inicio, fim)):
      "ok"       -> achou um valor so (ou um que se destaca: com R$, "reais" ou depois de "por")
      "nenhum"   -> sem numero que seja dinheiro
      "ambiguo"  -> mais de um valor possivel: o assistente pergunta em vez de adivinhar
      "invalido" -> zero ou grande demais
    datas, parcelas ("3x"), horas e "dia 10" nao contam como valor
    """
    n = alinhado(texto)
    candidatos = []
    for m in _RE_VALOR.finditer(n):
        antes, depois = n[max(0, m.start() - 24):m.start()], n[m.end():m.end() + 16]
        marcado = bool(m.group("rs") or m.group("reais"))
        if re.search(r"\bdia\s*$", antes) or _RE_NAO_VALOR.match(depois):
            continue
        numero_inteiro = m.group("num").isdigit() and 1990 <= int(m.group("num")) <= 2100
        if not marcado and numero_inteiro and (_RE_ANO_APOS_MES.search(antes) or re.search(r"\bem\s*$", antes)):          # "novembro de 2026", "em 2026"
            continue
        try:
            valor = _numero(m.group("num")) * (1000 if m.group("mil") else 1)
        except ValueError:
            continue
        palavra = re.search(r"(\w+)\W*$", n[:m.start()])
        candidatos.append({"valor": valor, "span": (m.start(), m.end()), "marcado": marcado, "preco": bool(palavra and palavra.group(1) in _PALAVRAS_DE_PRECO)})

    if not candidatos:
        return "nenhum", None, None
    escolhidos = [c for c in candidatos if c["marcado"]] or candidatos
    if len(escolhidos) > 1:
        escolhidos = [c for c in escolhidos if c["preco"]] or escolhidos
    if len(escolhidos) > 1:
        return "ambiguo", None, None
    c = escolhidos[0]
    if not 0 < c["valor"] <= VALOR_MAX:
        return "invalido", None, None
    return "ok", round(c["valor"], 2), c["span"]


# ----------------------------------------------------------------------- data

_RE_DATA_BARRAS = re.compile(r"(?<![\w/])(\d{1,2})\s*/\s*(\d{1,2})(?:\s*/\s*(\d{4}|\d{2}))?(?![\w/])")
_RE_DATA_POR_EXTENSO = re.compile(rf"(?<!\w)(\d{{1,2}})\s+de\s+({'|'.join(MESES)})(?:\s+de\s+(\d{{4}}))?\b")
_RE_DIA = re.compile(r"\bdia\s+(\d{1,2})\b")
_RE_SEMANA = re.compile(rf"\b({'|'.join(DIAS_SEMANA)})(?:[- ]feira)?\b")


def extrair_data(texto, hoje):
    """
    data citada na frase: dd/mm, dd/mm/aaaa, "10 de novembro", "dia 10", "ontem", "anteontem", "hoje", "sexta"...
    devolve (datetime a meia-noite | None, (inicio, fim) | None, mensagem de erro | None)
    sem ano, assume a data mais recente que ja passou (lancamentos sao quase sempre do passado)
    """
    n = alinhado(texto)

    m = _RE_DATA_BARRAS.search(n)
    if m:
        dia, mes = int(m.group(1)), int(m.group(2))
        ano = m.group(3)
        try:
            if ano:
                data = datetime(int(ano) + (2000 if len(ano) == 2 else 0), mes, dia)
            else:
                data = datetime(hoje.year, mes, dia)
                if data > hoje:
                    data = datetime(hoje.year - 1, mes, dia)
        except ValueError:
            return None, m.span(), f"A data {dia:02d}/{mes:02d} não existe."
        return data, m.span(), None

    m = _RE_DATA_POR_EXTENSO.search(n)
    if m:
        dia, mes = int(m.group(1)), MESES.index(m.group(2)) + 1
        try:
            if m.group(3):
                data = datetime(int(m.group(3)), mes, dia)
            else:
                data = datetime(hoje.year, mes, dia)
                if data > hoje:
                    data = datetime(hoje.year - 1, mes, dia)
        except ValueError:
            return None, m.span(), f"A data {dia:02d}/{mes:02d} não existe."
        return data, m.span(), None

    m = re.search(rf"\b(?:em|no mes de|durante)\s+({'|'.join(MESES)})\b(?:\s+de\s+\d{{4}})?", n)
    if m and not _RE_DIA.search(n):
        return None, m.span(), f"Em que dia de {MESES_COM_ACENTO[MESES.index(m.group(1))]} foi? Diga o dia, por exemplo: «dia 10 de {MESES_COM_ACENTO[MESES.index(m.group(1))]}»."

    m = _RE_DIA.search(n)
    if m:
        dia = int(m.group(1))
        referencia = hoje.replace(day=1)
        if dia > hoje.day:                                    # o dia ainda nao chegou neste mes: assume o mes passado
            referencia -= relativedelta(months=1)
        try:
            return referencia.replace(day=dia), m.span(), None
        except ValueError:
            return None, m.span(), f"O dia {dia} não existe em {nome_do_mes(referencia.strftime('%Y-%m'))}."

    for palavra, delta in (("anteontem", 2), ("ontem", 1), ("hoje", 0)):
        m = re.search(rf"\b{palavra}\b", n)
        if m:
            return hoje - timedelta(days=delta), m.span(), None

    m = _RE_SEMANA.search(n)
    if m:
        atraso = (hoje.weekday() - DIAS_SEMANA[m.group(1)]) % 7
        if atraso == 0 and re.match(r"\s*passad", n[m.end():m.end() + 10]):
            atraso = 7
        return hoje - timedelta(days=atraso), m.span(), None

    return None, None, None


# ------------------------------------------------------------- parcelas e tipo

_RE_PARCELAS = re.compile(r"(?:\bem\s+)?\b(\d{1,2})\s*(?:x|vezes|parcelas?)\b")


def extrair_parcelas(texto):
    """'em 10x', '3 parcelas', '12 vezes' -> (quantidade, (inicio, fim)); (None, None) se nao houver"""
    m = _RE_PARCELAS.search(alinhado(texto))
    if m and 2 <= int(m.group(1)) <= 60:
        return int(m.group(1)), m.span()
    return None, None


def menciona_parcelamento(texto):
    return bool(re.search(r"\bparcel\w*|\ba prazo\b", alinhado(texto))) or extrair_parcelas(texto)[0] is not None


VERBOS_DESPESA = {"gastei", "gastamos", "paguei", "pagamos", "comprei", "compramos", "desembolsei", "torrei", "investi", "apliquei", "abasteci", "recarreguei", "parcelei"}
VERBOS_RECEITA = {"recebi", "recebemos", "ganhei", "ganhamos", "faturei", "vendi", "entrou", "entraram", "caiu", "cairam", "depositaram"}


def tipo_do_lancamento(texto):
    """'despesa', 'receita', 'ambos' (os dois na mesma frase) ou None (nao parece um registro)"""
    s = normalizar(texto)
    palavras = set(s.split())
    despesa, receita = bool(palavras & VERBOS_DESPESA), bool(palavras & VERBOS_RECEITA) or "me pagaram" in s
    return "ambos" if despesa and receita else "despesa" if despesa else "receita" if receita else None


_RE_PERGUNTA = re.compile(
    r"^(quanto|quanta|quantos|quantas|qual|quais|como|onde|quando|quem|porque|por que|o que|oq|me diga|me fale|me mostre|mostre|mostra|"
    r"liste|lista|calcule|quero saber|gostaria de saber|preciso saber|tem como|consigo|posso|devo|vale a pena|pode|poderia|sera que|existe)\b"
)


def eh_pergunta(texto):
    return "?" in texto or bool(_RE_PERGUNTA.match(normalizar(texto)))


# ------------------------------------------------------------------ conta/cartao

_GENERICAS = {"cartao", "conta", "banco", "de", "do", "da", "dos", "das", "e", "credito", "debito"}


def _palavras(texto):
    return re.findall(r"[a-z0-9]+", alinhado(texto))


def achar_conta(texto, nomes):
    """
    qual das contas do usuario a frase cita ("no itau" -> "Cartão Itaú"): todas as palavras do nome (menos as genericas)
    precisam aparecer. devolve (nome | None, [nomes empatados], palavras_do_nome)
    """
    palavras = set(_palavras(texto))
    achadas = []
    for nome in nomes:
        tokens = [t for t in _palavras(nome) if t not in _GENERICAS] or _palavras(nome)
        if tokens and all(t in palavras for t in tokens):
            achadas.append((len(tokens), nome, tokens))
    if not achadas:
        return None, [], set()
    melhor = max(a[0] for a in achadas)
    topo = [a for a in achadas if a[0] == melhor]
    if len(topo) > 1:
        return None, [a[1] for a in topo], set()
    return topo[0][1], [], set(topo[0][2])


def conta_desconhecida(texto):
    """'no cartão Nubank' (sem ter essa conta): devolve a palavra citada, como foi escrita, ou None. 'conta de luz' nao e uma conta"""
    m = re.search(r"\b(?:cartao|vale)\s+(?:de\s+|do\s+|da\s+)?([a-z0-9]+)", alinhado(texto))
    return texto[m.start(1):m.end(1)] if m and m.group(1) not in _GENERICAS else None


# --------------------------------------------------------------------- descricao

_STOP = {"a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "da", "do", "das", "dos", "no", "na", "nos", "nas", "em", "com", "por", "pra", "para",
         "pelo", "pela", "pelos", "pelas", "e", "ao", "aos", "reais", "real", "hoje", "ontem", "anteontem", "dia", "que", "foi", "foram", "eu", "meu",
         "minha", "meus", "minhas", "la", "aqui", "tambem", "so", "apenas", "entao", "cartao", "agora", "ou", "r"}
_PONTUACAO = " .,;:!?-–—\"'()[]"


def descricao_do_lancamento(texto, spans, conta_palavras=()):
    """
    o que sobra da frase depois de tirar o valor, a data, as parcelas, os verbos e a conta:
    "gastei R$ 50 no mercado hoje" -> "Mercado"; "comprei um tênis por 200 no itaú" -> "Tênis"
    """
    n = alinhado(texto)
    coberto = set()
    for a, b in spans:
        coberto.update(range(a, b))
    mantidos = []
    for m in re.finditer(r"\S+", texto):
        if coberto & set(range(m.start(), m.end())):
            continue
        nucleo = re.sub(r"^\W+|\W+$", "", n[m.start():m.end()])
        if nucleo in VERBOS_DESPESA or nucleo in VERBOS_RECEITA:
            continue
        if re.fullmatch(r"\d{1,2}(?:h\d{0,2}|hs|:\d{2})", nucleo):               # "14h", "14:30"
            continue
        if nucleo in conta_palavras:
            if mantidos and mantidos[-1][1] in ("cartao", "conta"):
                mantidos.pop()
            continue
        mantidos.append((m.group(), nucleo))
    while mantidos and mantidos[0][1] in _STOP:
        mantidos.pop(0)
    while mantidos and mantidos[-1][1] in _STOP:
        mantidos.pop()
    descricao = " ".join(t for t, _ in mantidos).strip(_PONTUACAO)
    return (descricao[:1].upper() + descricao[1:])[:255]


# ---------------------------------------------------------------- periodo e categoria

def extrair_periodo(texto, hoje):
    """
    mes a que a pergunta se refere: ("AAAA-MM", explicito). "este mes" e o padrao; entende "mês passado", "retrasado",
    "outubro", "outubro de 2025". sem ano, usa o mes mais recente que ja comecou
    """
    s = normalizar(texto)
    atual = hoje.replace(day=1)
    m = re.search(rf"\b({'|'.join(MESES)})(?:\s+de)?(?:\s+(\d{{4}}))?\b", s)
    if m:
        mes = MESES.index(m.group(1)) + 1
        ano = int(m.group(2)) if m.group(2) else atual.year - (1 if mes > atual.month else 0)
        return f"{ano:04d}-{mes:02d}", True
    if re.search(r"\bretrasado\b", s):
        return (atual - relativedelta(months=2)).strftime("%Y-%m"), True
    if re.search(r"\b(mes passado|mes anterior|ultimo mes|mes que passou)\b", s):
        return (atual - relativedelta(months=1)).strftime("%Y-%m"), True
    return atual.strftime("%Y-%m"), bool(re.search(r"\b(este|esse|neste|nesse|deste|desse|atual)\s+mes\b|\bmes atual\b", s))


_CATEGORIAS_POR_NOME = {normalizar(c): c for c in CATEGORIAS if c != "Outros"}


def extrair_categoria(texto):
    """categoria citada na pergunta: pelo nome ('alimentação') ou por uma palavra do dicionario ('mercado', 'uber'); None se nao houver"""
    s = normalizar(texto)
    palavras = set(s.split())
    for nome, categoria in _CATEGORIAS_POR_NOME.items():
        if nome in palavras:
            return categoria
    categoria = detectar_categoria(s)
    return None if categoria == "Outros" else categoria


# ------------------------------------------------------------------- intencao

# a ordem importa: temas especificos primeiro; ajuda, agradecimento e saudacao so valem quando nada mais combina
INTENCOES = [
    ("reserva", r"\b(reserva|fundo) (de )?emergenc|\breserva financeira\b"),
    ("educ_orcamento", r"\b50 30 20\b|\bregra (dos )?50\b|\b(montar|fazer|criar|planejar|organizar) (um |meu |o )?(orcamento|planejamento)|\borcamento (pessoal|mensal|domestico)\b"),
    ("educ_dividas", r"\b(divida|dividas|endividad\w*|devendo|negativad\w*|nome sujo|sair do vermelho|quitar|rotativo|juros do cartao)\b"),
    ("educ_investir", r"\b(investir|investimentos?|tesouro|cdb|lci|lca|renda fixa|poupanca|bolsa|acoes|selic|cdi)\b"),
    ("educ_cartao", r"\b(como usar (bem )?(o )?cartao|cartao de credito|fatura|limite do cartao)\b"),
    ("educ_juros", r"\bjuros (compostos?|simples)\b"),
    ("educ_parcelar", r"\b(vale a pena|devo|compensa|melhor)\b.*\bparcel|\bparcelar (ou|vs)\b"),
    ("otimizar", r"\b(qual|que|melhor) (cartao|conta)\b|\bcomo pagar\b|\bforma de pagar\b|\botimiz\w*|\bcashback\b|\bonde pagar\b|\bcaminho do dinheiro\b|\bgrafo\b|\bpagar (minhas |as )?despesas\b"),
    ("parcelas", r"\bparcel\w*|\bcomprometid\w*|\bproximos meses\b|\bfatura futura\b|\ba prazo\b"),
    ("metas", r"\bmetas?\b|\bobjetivos?\b|\bsonhos?\b"),
    ("alertas", r"\balertas?\b|\blimites? (de )?(gasto|gastos|categoria|categorias)\b|\bestourei\b|\bultrapass\w*"),
    ("ultimas", r"\bultim[oa]s? (transac\w*|lancament\w*|gastos?|compras?|despesas?|movimentac\w*|registros?)\b|\b(o que|oq) (eu )?(gastei|comprei|paguei) (por )?ultimo\b|\bmovimentacoes recentes\b"),
    ("maiores", r"\bmaiores? (gasto|despesa|compra)s?\b|\bonde (eu )?(mais )?(gast\w+|esta indo)\b|\bem que (eu )?(mais )?gast\w+|\bpara onde (foi|vai|esta indo) (o |meu )?dinheiro\b|\bmais gast\w+"),
    ("dicas", r"\bdicas?\b|\beconomiz\w*|\beconomia\b|\bgastar menos\b|\b(cortar|reduzir|diminuir) (os |meus )?(gastos?|despesas?)\b|\bpoupar\b|\bguardar dinheiro\b|\bsobrar dinheiro\b"),
    ("receitas", r"\bquanto (eu )?(recebi|ganhei|entrou)\b|\bminhas? (receita|renda|entrada)s?\b|\bo que (eu )?(recebi|ganhei)\b"),
    ("saldo", r"\bsaldo\b|\bquanto (eu )?(tenho|sobrou|sobra|resta|restou|vou ter)\b|\bquanto (dinheiro )?(tenho|sobrou|sobra)\b|\btenho dinheiro\b"),
    ("resumo", r"\bresumo\b|\bbalanco\b|\bcomo (estao|esta|anda|andam|vao|vai) (os |as |meus |minhas |o |a )?(meus |minhas )?(gastos?|financas|contas|dinheiro|saldo|despesas|mes)\b|\bsaldo\b|\bcomo estou\b|\bsituacao financeira\b|\bquanto (eu )?(gastei|gasto|paguei)\b|\btotal (de |dos )?(gastos|despesas)\b|\bgastos? (do|de|deste|desse|neste) mes\b|\bminhas despesas\b|\bmeus gastos\b|\bquanto (eu )?(ainda )?(posso|consigo) gastar\b"),
    ("ajuda", r"\b(ajuda|ajudar|o que (voce|vc|tu) (faz|pode|sabe)|como (voce|vc) funciona|como funciona|comandos?|funcionalidades|help)\b|\bo que (eu )?posso (te )?(pedir|perguntar|fazer)\b"),
    ("agradecimento", r"\b(obrigad[oa]|valeu|vlw|brigad[oa]|agradeco)\b"),
    ("saudacao", r"^(oi+|ola|opa|e ai|eai|salve|bom dia|boa tarde|boa noite|tudo bem|hey|hello)\b.{0,25}$"),
]
_INTENCOES_COMPILADAS = [(nome, re.compile(padrao)) for nome, padrao in INTENCOES]


def classificar(texto):
    """a intencao da frase (uma das chaves de INTENCOES) ou 'desconhecida'"""
    s = normalizar(texto)
    for nome, padrao in _INTENCOES_COMPILADAS:
        if padrao.search(s):
            return nome
    return "desconhecida"


def eh_complemento(texto):
    """'e em outubro?', 'e no mês passado?', 'e com transporte?': continua a pergunta anterior"""
    s = normalizar(texto)
    return bool(re.match(r"^e\s+\w+", s)) and len(s.split()) <= 7
