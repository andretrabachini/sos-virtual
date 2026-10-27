"""
deteccao automatica da categoria de uma transacao pela descricao

como funciona
  1. a descricao e normalizada: minuscula, sem acento, e tudo que nao for letra ou numero vira
     espaco ("IFD*PIZZARIA" -> "ifd pizzaria"; "Farmácia" -> "farmacia")
  2. cada palavra da tabela REGRAS e procurada como PALAVRA INTEIRA (ou frase inteira), aceitando
     plural simples (+s / +es). por isso "luz" nao casa em "Luzia" nem "ação" em "doação"
  3. se varias palavras casarem, ganha a mais ESPECIFICA: palavra forte antes de fraca, frase mais
     longa antes de frase curta, palavra maior antes de menor. ex.: "uber eats" (2 palavras) vence
     "uber" (1), e "posto de saude" vence "posto"
  4. se nada casar, "Outros"

como editar a tabela (basta acrescentar palavras nas listas, com ou sem acento)
  "palavra"     palavra inteira ou frase ("pao de acucar"); plural simples e aceito
  "radical*"    qualquer palavra que COMECE com o radical ("supermerc*" pega supermercado, supermerc...)
                use so em radicais longos, para nao pegar palavras de outro assunto
  "?palavra"    palavra FRACA, generica: so vale se nenhuma palavra forte casar
"""
import unicodedata

CATEGORIA_PADRAO = "Outros"

# a ordem desempata quando duas categorias casam com a mesma forca
ORDEM = ["Alimentação", "Restaurante", "Transporte", "Saúde", "Educação", "Lazer", "Moradia",
         "Vestuário", "Investimentos", "Salário", "Outros"]

# categorias que so existem para receitas (valor positivo): nunca sao sugeridas para despesas
SO_RECEITA = {"Salário"}

REGRAS = {
    # compras de comida para levar para casa (o que o vale-alimentacao costuma pagar)
    "Alimentação": [
        "mercado", "mercadinho", "mercearia", "supermerc*", "hipermerc*", "minimerc*", "atacadao", "atacarejo",
        "assai", "carrefour", "pao de acucar", "sams club", "makro", "hortifruti", "sacolao", "feira livre", "?feira",
        "acougue", "acougu*", "padaria", "padari*", "panificadora", "pao", "confeitaria",
        "adega", "cerveja", "bebida",
    ],
    # refeicoes fora de casa e delivery (o que o vale-refeicao costuma pagar)
    "Restaurante": [
        "restaurante", "restaurant*", "lanchonete", "lanchonet*", "lanche", "pizzaria", "pizzari*", "pizza",
        "hamburgueria", "hamburguer", "burger king", "mcdonald", "mc donald", "subway", "outback", "habib",
        "giraffas", "spoleto", "china in box", "madero", "sushi", "temaki", "pastelaria",
        "ifood", "ifd", "rappi", "uber eats", "ubereats", "99 food", "99food",
        "almoco", "jantar", "refeicao", "cafeteria", "starbucks", "sorveteria", "sorvete", "acai", "churrascaria",
        "churrasco", "marmita", "marmitex", "bar e restaurante", "?cafe", "?delivery", "?comida",
    ],
    "Transporte": [
        "uber", "99 pop", "99pop", "99 taxi", "99taxi", "99app", "99 app", "99 tecnologia", "cabify", "indrive",
        "taxi", "estacionamento", "estapar", "pedagio", "sem parar", "semparar", "conectcar", "veloe",
        "ipva", "licenciamento", "dpvat", "combustivel", "gasolina", "etanol", "diesel", "?posto",
        "shell", "ipiranga", "petrobras", "oficina", "mecanica", "mecanico", "borracharia", "pneu",
        "lava jato", "lava rapido", "onibus", "metro", "cptm", "sptrans", "bilhete unico", "passagem",
        "rodoviaria", "trem", "brt", "moto taxi", "aluguel de carro", "aluguel de veiculo", "locadora de veiculos",
        "seguro auto", "seguro do carro", "?carro", "?veiculo",
    ],
    "Saúde": [
        "farmacia", "farmac*", "drogaria", "drogari*", "droga raia", "drogaraia", "drogasil", "pague menos",
        "ultrafarma", "panvel", "medico", "consulta", "exame", "laboratorio", "laborat*", "hospital", "clinica",
        "dentista", "odonto*", "plano de saude", "unimed", "amil", "hapvida", "sulamerica", "bradesco saude",
        "psicologo", "psiquiatra", "terapia", "terapeuta", "fisioterapia", "fono", "fonoaudiologo", "nutricionista",
        "oculos", "otica", "vacina", "remedio", "medicamento", "posto de saude", "pronto socorro",
        "academia", "smartfit", "smart fit", "bluefit", "pilates",
    ],
    "Educação": [
        "curso", "faculdade", "universidade", "uniso", "unip", "estacio", "anhanguera", "senac", "senai",
        "escola", "escolar", "colegio", "creche", "livro", "livraria", "apostila", "material escolar", "papelaria",
        "?mensalidade", "matricula", "udemy", "alura", "coursera", "duolingo", "idioma", "wizard", "fisk", "ccaa",
        "enem", "vestibular", "pos graduacao", "mba",
    ],
    "Lazer": [
        "cinema", "cinemark", "kinoplex", "ingresso", "sympla", "eventim", "show", "teatro", "netflix", "spotify",
        "disney", "hbo max", "prime video", "amazon prime", "youtube premium", "deezer", "globoplay", "apple music",
        "playstation", "psn", "xbox", "steam", "nintendo", "epic games", "jogo", "?viagem", "hotel", "pousada",
        "airbnb", "booking", "decolar", "hostel", "resort", "parque", "zoologico", "bar", "balada", "boate",
        "clube", "festival", "festa", "boliche", "museu", "cvc", "hurb",
    ],
    "Moradia": [
        "aluguel", "condominio", "iptu", "taxa condominial", "luz", "agua", "gas", "energia", "energia eletrica",
        "enel", "cpfl", "cemig", "copel", "celesc", "equatorial", "sabesp", "copasa", "sanepar", "embasa", "comgas",
        "naturgy", "ultragaz", "liquigas", "internet", "wifi", "fibra", "vivo fibra", "?vivo", "?claro", "?tim",
        "reforma", "material de construcao", "leroy merlin", "telhanorte", "tok stok", "mobly", "moveis", "colchao",
        "diarista", "faxineira", "imobiliaria", "financiamento imobiliario", "financiamento habitacional",
        "seguro residencial", "dedetizacao", "chaveiro", "encanador", "eletricista",
    ],
    "Vestuário": [
        "roupa", "calcado", "tenis", "sapato", "camisa", "camiseta", "calca", "bermuda", "vestido", "saia", "blusa",
        "jaqueta", "casaco", "cueca", "lingerie", "moda", "renner", "riachuelo", "marisa", "zara", "hering",
        "centauro", "netshoes", "shein", "dafiti", "arezzo", "havaianas", "nike", "adidas", "puma", "alfaiataria",
        "costureira", "brecho",
    ],
    "Investimentos": [
        "investimento", "poupanca", "tesouro direto", "tesouro", "?acao", "?acoes", "fundo de investimento", "?fundo",
        "cdb", "lci", "lca", "fii", "rdb", "previdencia", "corretora", "xp investimentos", "nu invest", "nuinvest",
        "btg pactual", "bitcoin", "cripto", "criptomoeda", "mercado bitcoin", "binance", "dividendo", "rendimento",
        "jcp", "juros sobre capital", "aplicacao", "aplicacao financeira", "resgate",
    ],
    # so para receitas (valor positivo)
    "Salário": [
        "salario", "folha de pagamento", "pagamento de salario", "pgto salario", "vencimentos", "proventos",
        "remuneracao", "decimo terceiro", "13 salario", "13o salario", "ferias", "pro labore", "prolabore",
        "holerite", "adiantamento salarial", "adiantamento de salario", "bonus", "plr", "participacao nos lucros",
        "comissao",
    ],
    # casos que PRECISAM ficar em Outros mesmo contendo palavra de outra categoria
    "Outros": [
        "mercado livre", "mercadolivre", "mercado pago", "mercadopago", "pet shop", "petshop", "veterinari*",
        "petz", "cobasi", "racao", "amazon", "shopee", "aliexpress", "magazine luiza", "magalu", "americanas",
        "casas bahia", "olx",
    ],
}


def normalizar(texto):
    """minuscula, sem acento; tudo que nao for letra ou numero vira espaco"""
    base = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in base if not unicodedata.combining(c))
    limpo = "".join(c if (c.isascii() and c.isalnum()) else " " for c in sem_acento.lower())
    return " ".join(limpo.split())


def _compilar():
    regras = []
    for categoria, palavras in REGRAS.items():
        for bruta in palavras:
            fraca = bruta.startswith("?")
            termo = bruta.lstrip("?")
            radical = termo.endswith("*")
            termo = normalizar(termo.rstrip("*"))
            regras.append({
                "categoria": categoria,
                "exibir": termo,
                "termo": termo,
                "radical": radical,
                "fraca": fraca,
                "palavras": len(termo.split()),
                "tamanho": len(termo),
                "so_receita": categoria in SO_RECEITA,
                "ordem": ORDEM.index(categoria),
            })
    return regras


_REGRAS = _compilar()


def _casa(regra, texto_pad, tokens):
    termo = regra["termo"]
    if regra["radical"]:
        return any(t.startswith(termo) for t in tokens)
    # palavra/frase inteira, com plural simples
    return f" {termo} " in texto_pad or f" {termo}s " in texto_pad or f" {termo}es " in texto_pad


def detectar_categoria_com_motivo(texto, valor=None):
    """
    devolve (categoria, palavra_que_casou). sem correspondencia: ("Outros", None)
    `valor` positivo = receita (libera a categoria Salário); negativo ou None = despesa
    """
    if not isinstance(texto, str):
        return CATEGORIA_PADRAO, None
    normal = normalizar(texto[:500])
    if not normal:
        return CATEGORIA_PADRAO, None

    receita = isinstance(valor, (int, float)) and not isinstance(valor, bool) and valor > 0
    texto_pad = f" {normal} "
    tokens = normal.split()

    melhor, melhor_chave = None, None
    for regra in _REGRAS:
        if regra["so_receita"] and not receita:
            continue
        if not _casa(regra, texto_pad, tokens):
            continue
        # forte antes de fraca; frase longa antes de curta; palavra maior antes de menor; depois a ordem da tabela
        chave = (not regra["fraca"], regra["palavras"], regra["tamanho"], -regra["ordem"])
        if melhor_chave is None or chave > melhor_chave:
            melhor, melhor_chave = regra, chave

    if melhor is None:
        return CATEGORIA_PADRAO, None
    return melhor["categoria"], melhor["exibir"]


def detectar_categoria(texto, valor=None):
    return detectar_categoria_com_motivo(texto, valor)[0]
