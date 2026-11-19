"""
assistente de chat do SOS Virtual: registra gastos escritos em linguagem natural, responde perguntas com os dados do usuario
e da dicas. roda inteiro no servidor, sem enviar dados para servicos externos de IA

    responder(usuario_id, "gastei R$ 50 no mercado hoje")  ->  {"resposta": "...", "intencao": "registrar", "lancamento": {...}, "alertas": []}

o entendimento das frases fica em servicos/assistente_texto.py; as regras de gravacao, em servicos/lancamentos.py
(as mesmas do formulario), entao o assistente nunca registra nada que o formulario recusaria
"""
from collections import defaultdict
from datetime import datetime
from math import ceil

from dateutil.relativedelta import relativedelta

from database import db
from modelos.modelos import Alerta, Meta, Transacao, Usuario
from servicos import assistente_texto as T
from servicos.categorizacao import detectar_categoria
from servicos.contas import ContaInvalida, nomes_das_contas
from servicos.financeiro import gastos_por_categoria, limites_do_mes, resumo_mensal
from servicos.grafos_dados import calcular_do_mes
from servicos.importacao import projecao_mensal
from servicos.lancamentos import data_da_compra, gravar_transacao
from servicos.saldo import resumo_com_saldo
from servicos.tempo import hoje

brl, nome_do_mes, percentual = T.brl, T.nome_do_mes, T.percentual

EXEMPLO_GASTO = "«gastei R$ 50 no mercado»"
INTENCOES_COM_PERIODO = {"resumo", "saldo", "receitas", "maiores", "ultimas", "alertas", "otimizar"}
JANELA_DE_CONTEXTO = 3        # quantas perguntas anteriores do usuario valem para completar um "e em outubro?"


def _resp(texto, intencao, lancamento=None, alertas=None):
    return {"resposta": texto, "intencao": intencao, "lancamento": lancamento, "alertas": alertas or []}


class _Contexto:
    def __init__(self, usuario_id):
        self.uid = usuario_id
        self.hoje = hoje()
        self.usuario = db.session.get(Usuario, usuario_id)
        self.contas = nomes_das_contas(usuario_id)          # {id: nome}

    @property
    def mes_atual(self):
        return self.hoje.strftime("%Y-%m")

    @property
    def renda(self):
        return (self.usuario.renda_mensal or 0.0) if self.usuario else 0.0

    @property
    def primeiro_nome(self):
        return (self.usuario.nome.split()[0] if self.usuario and self.usuario.nome else "")


def _mes_anterior(mes, passos=1):
    return (datetime(int(mes[:4]), int(mes[5:7]), 1) - relativedelta(months=passos)).strftime("%Y-%m")


def _despesas_do_mes(uid, mes, categoria=None):
    inicio, fim = limites_do_mes(mes)
    consulta = Transacao.query.filter(Transacao.usuario_id == uid, Transacao.data >= inicio, Transacao.data < fim, Transacao.valor < 0)
    if categoria:
        consulta = consulta.filter(Transacao.categoria == categoria)
    return consulta.order_by(Transacao.valor.asc(), Transacao.id.desc()).all()       # a mais negativa (maior) primeiro


def _plural(n, singular, plural):
    return f"{n} {singular if n == 1 else plural}"


# =========================================================================== registrar

def _registrar(ctx, msg, tipo, status, valor, span):
    despesa = tipo == "despesa"
    if tipo == "ambos":
        return _resp(f"Vi um gasto e uma receita na mesma frase. Envie um lançamento por vez, por exemplo: {EXEMPLO_GASTO}.", "registrar")
    if status == "nenhum":
        return _resp(f"Entendi que é {'um gasto' if despesa else 'uma receita'}, mas não achei o valor. Escreva, por exemplo: {EXEMPLO_GASTO}.", "registrar")
    if status == "ambiguo":
        return _resp(f"Encontrei mais de um valor na frase e não quero registrar errado. Envie um lançamento por vez, por exemplo: {EXEMPLO_GASTO}.", "registrar")
    if status == "invalido":
        return _resp("Esse valor não é válido: use um valor maior que zero.", "registrar")

    data, span_data, erro_data = T.extrair_data(msg, ctx.hoje)
    if erro_data:
        return _resp(erro_data, "registrar")
    parcelas, span_parcelas = T.extrair_parcelas(msg)
    if despesa and (parcelas or T.menciona_parcelamento(msg)):
        return _resp("Compras parceladas precisam do cartão, do número de parcelas e dos juros, então cadastre em Transações > Compra parcelada "
                     "(lá o sistema calcula as parcelas e projeta os meses seguintes). Se a compra foi à vista, escreva sem «parcelei» ou «3x».", "registrar")

    conta, empatadas, palavras_conta = (T.achar_conta(msg, list(ctx.contas.values())) if despesa else (None, [], set()))
    if empatadas:
        return _resp(f"Você citou mais de uma conta ({', '.join(empatadas)}). Repita a frase informando só uma.", "registrar")
    desconhecida = T.conta_desconhecida(msg) if despesa and not conta else None

    spans = [x for x in (span, span_data, span_parcelas) if x]
    descricao = T.descricao_do_lancamento(msg, spans, palavras_conta | ({T.alinhado(desconhecida)} if desconhecida else set()))
    if not descricao:
        return _resp(f"Com o que foi {'esse gasto' if despesa else 'essa receita'} de {brl(valor)}? Escreva, por exemplo: {EXEMPLO_GASTO}.", "registrar")

    valor_assinado = -valor if despesa else valor
    categoria = detectar_categoria(descricao, valor_assinado)
    data_final = None
    if data is not None:
        data_final, erro = data_da_compra(data)
        if erro:
            return _resp(f"Não registrei: {erro}.", "registrar")

    try:
        lanc = gravar_transacao(ctx.uid, descricao, valor_assinado, categoria, data_final, conta)
    except ContaInvalida as e:
        return _resp(f"Não registrei esse lançamento. {e}", "registrar")

    quando = "hoje" if data is None or data == ctx.hoje else data.strftime("%d/%m/%Y")
    texto = f"Registrei {'o gasto' if despesa else 'a receita'}: {descricao}, {brl(valor)}, categoria {categoria}, {quando}"
    if despesa:
        texto += f", na conta {conta}." if conta else ", sem conta definida."
    else:
        texto += "."
    if desconhecida:
        texto += f" Não achei uma conta chamada «{desconhecida}», então ficou sem conta; você pode criá-la em Transações."
    for a in lanc["alertas"]:
        texto += f"\nAtenção: os gastos com {a['categoria']} chegaram a {brl(a['gasto'])}, acima do limite de {brl(a['limite'])}."
    texto += "\nSe algo estiver errado, toque em Desfazer ou ajuste no histórico de Transações."

    lancamento = {k: lanc[k] for k in ("id", "descricao", "valor", "categoria", "conta", "data")}
    return _resp(texto, "registrar", lancamento, lanc["alertas"])


def _valor_sem_verbo(valor):
    return _resp(f"Encontrei o valor {brl(valor)}, mas não sei se é um gasto ou uma receita. Escreva, por exemplo: {EXEMPLO_GASTO} ou «recebi R$ 3.000 de salário».", "registrar")


# =========================================================================== consultas

def _resumo(ctx, mes, **_):
    s = resumo_com_saldo(ctx.uid, mes)
    r = {"receita": s["receita"], "despesa": s["despesa"], "saldo": s["saldo_do_mes"]}
    nome = nome_do_mes(mes)
    if not r["receita"] and not r["despesa"]:
        return _resp(f"Ainda não há lançamentos em {nome}. Registre um gasto escrevendo, por exemplo, {EXEMPLO_GASTO}.", "resumo")
    # o saldo continua de um mes para o outro: so mostra o "inicio" e o "fim" quando ha algo que veio do passado
    com_saldo = s["saldo_anterior"] is not None and (s["saldo_anterior"] != 0 or s["saldo_inicial_informado"])
    linhas = [f"Resumo de {nome}:"]
    if com_saldo:
        linhas.append(f"• Saldo no início do mês: {brl(s['saldo_anterior'])}")
    linhas += [f"• Receitas: {brl(r['receita'])}", f"• Despesas: {brl(r['despesa'])}",
               f"• Saldo do mês: {brl(r['saldo'])}" + (" (no vermelho)" if r["saldo"] < 0 else "")]
    if com_saldo:
        linhas.append(f"• Saldo no fim do mês: {brl(s['saldo_final'])}" + (" (no vermelho)" if s["saldo_final"] < 0 else ""))
    categorias = sorted(gastos_por_categoria(ctx.uid, mes).items(), key=lambda x: -x[1])[:3]
    if categorias:
        linhas.append("Onde mais gastou: " + "; ".join(f"{c} {brl(v)} ({percentual(v, r['despesa'])}%)" for c, v in categorias) + ".")
    anterior = resumo_mensal(ctx.uid, _mes_anterior(mes))["despesa"]
    if anterior and r["despesa"]:
        variacao = round(100 * (r["despesa"] - anterior) / anterior)
        comparacao = f"subiram {variacao}%" if variacao > 0 else f"caíram {-variacao}%" if variacao < 0 else "ficaram iguais"
        linhas.append(f"Em relação a {nome_do_mes(_mes_anterior(mes))}, as despesas {comparacao}.")
    if ctx.renda and r["despesa"]:
        linhas.append(f"As despesas equivalem a {percentual(r['despesa'], ctx.renda)}% da renda mensal informada ({brl(ctx.renda)}).")
    gastos = gastos_por_categoria(ctx.uid, mes)
    for alerta in Alerta.query.filter_by(usuario_id=ctx.uid, ativo=True).all():
        if gastos.get(alerta.categoria, 0.0) >= alerta.limite:
            linhas.append(f"Atenção: {alerta.categoria} passou do limite ({brl(gastos[alerta.categoria])} de {brl(alerta.limite)}).")
    return _resp("\n".join(linhas), "resumo")


def _saldo(ctx, mes, **_):
    s = resumo_com_saldo(ctx.uid, mes)
    nome = nome_do_mes(mes)
    if s["saldo_final"] is None:
        desde = nome_do_mes(ctx.usuario.saldo_inicial_mes)
        return _resp(f"Não sei o saldo de {nome}: o saldo inicial que você informou vale a partir de {desde}. "
                     f"Em {nome}, o saldo do mês (o que entrou menos o que saiu) foi {brl(s['saldo_do_mes'])}.", "saldo")
    if not s["receita"] and not s["despesa"] and not s["saldo_anterior"] and not s["saldo_inicial_informado"]:
        return _resp(f"Ainda não há lançamentos até {nome} para calcular o saldo. Registre uma receita ou um gasto, por exemplo, {EXEMPLO_GASTO}. "
                     "Se você já tinha dinheiro em conta antes de usar o sistema, informe o saldo inicial em Minha conta > Perfil.", "saldo")
    verbo = "está em" if mes == ctx.mes_atual else "ficou em" if mes < ctx.mes_atual else "deve ficar em"
    texto = (f"Em {nome}: começou com {brl(s['saldo_anterior'])}, entraram {brl(s['receita'])} e saíram {brl(s['despesa'])}. "
             f"O saldo {verbo} {brl(s['saldo_final'])}" + (" (no vermelho)." if s["saldo_final"] < 0 else "."))
    if not s["saldo_inicial_informado"]:
        texto += "\nSe você já tinha dinheiro em conta antes de usar o sistema, informe o saldo inicial em Minha conta > Perfil para o saldo bater com o do seu banco."
    return _resp(texto, "saldo")


def _gasto_categoria(ctx, mes, categoria, **_):
    nome = nome_do_mes(mes)
    itens = _despesas_do_mes(ctx.uid, mes, categoria)
    if not itens:
        return _resp(f"Não encontrei gastos de {categoria} em {nome}.", "gasto_categoria")
    total = round(sum(-t.valor for t in itens), 2)
    total_mes = resumo_mensal(ctx.uid, mes)["despesa"]
    linhas = [f"Em {nome} você gastou {brl(total)} com {categoria} ({percentual(total, total_mes)}% das despesas do mês, {_plural(len(itens), 'compra', 'compras')})."]
    linhas.append("Maiores: " + "; ".join(f"{t.descricao} {brl(-t.valor)} ({t.data.strftime('%d/%m')})" for t in itens[:3]) + ".")
    alerta = Alerta.query.filter_by(usuario_id=ctx.uid, categoria=categoria, ativo=True).first()
    if alerta:
        resto = round(alerta.limite - total, 2)
        linhas.append(f"Seu limite de {categoria} é {brl(alerta.limite)}: " + (f"ainda restam {brl(resto)}." if resto >= 0 else f"você passou {brl(-resto)}."))
    return _resp("\n".join(linhas), "gasto_categoria")


def _receitas(ctx, mes, **_):
    inicio, fim = limites_do_mes(mes)
    itens = Transacao.query.filter(Transacao.usuario_id == ctx.uid, Transacao.data >= inicio, Transacao.data < fim, Transacao.valor > 0).order_by(Transacao.valor.desc()).all()
    nome = nome_do_mes(mes)
    if not itens:
        return _resp(f"Não encontrei receitas em {nome}. Para registrar, escreva, por exemplo, «recebi R$ 3.000 de salário».", "receitas")
    total = round(sum(t.valor for t in itens), 2)
    linhas = [f"Em {nome} você recebeu {brl(total)} ({_plural(len(itens), 'entrada', 'entradas')}):"]
    linhas += [f"• {t.descricao}: {brl(t.valor)} ({t.data.strftime('%d/%m')})" for t in itens[:5]]
    return _resp("\n".join(linhas), "receitas")


def _ultimas(ctx, **_):
    itens = Transacao.query.filter_by(usuario_id=ctx.uid).order_by(Transacao.data.desc(), Transacao.id.desc()).limit(5).all()
    if not itens:
        return _resp(f"Você ainda não tem lançamentos. Registre o primeiro escrevendo, por exemplo, {EXEMPLO_GASTO}.", "ultimas")
    linhas = ["Seus últimos lançamentos:"]
    for t in itens:
        conta = ctx.contas.get(t.conta_id)
        linhas.append(f"• {t.data.strftime('%d/%m')} {t.descricao}: {'+' if t.valor > 0 else '-'}{brl(abs(t.valor))}" + (f" ({conta})" if conta else ""))
    return _resp("\n".join(linhas), "ultimas")


def _maiores(ctx, mes, categoria=None, **_):
    nome = nome_do_mes(mes)
    itens = _despesas_do_mes(ctx.uid, mes, categoria)
    if not itens:
        return _resp(f"Não encontrei despesas{f' de {categoria}' if categoria else ''} em {nome}.", "maiores")
    linhas = [f"Maiores despesas de {nome}{f' em {categoria}' if categoria else ''}:"]
    linhas += [f"{i}) {t.descricao}: {brl(-t.valor)} ({t.categoria}, {t.data.strftime('%d/%m')})" for i, t in enumerate(itens[:5], start=1)]
    if not categoria:
        total = sum(-t.valor for t in itens)
        categorias = sorted(gastos_por_categoria(ctx.uid, mes).items(), key=lambda x: -x[1])[:3]
        linhas.append("Por categoria: " + "; ".join(f"{c} {brl(v)} ({percentual(v, total)}%)" for c, v in categorias) + ".")
    return _resp("\n".join(linhas), "maiores")


def _metas(ctx, **_):
    metas = Meta.query.filter_by(usuario_id=ctx.uid).order_by(Meta.id).all()
    if not metas:
        return _resp("Você ainda não tem metas. Crie a primeira em Metas: defina um valor-alvo e, se quiser, um prazo; depois é só depositar conforme for guardando.", "metas")
    linhas = ["Suas metas:"]
    for m in metas:
        if m.valor_atual >= m.valor_alvo:
            linhas.append(f"• {m.titulo}: concluída ({brl(m.valor_alvo)}).")
            continue
        falta = round(m.valor_alvo - m.valor_atual, 2)
        linha = f"• {m.titulo}: {brl(m.valor_atual)} de {brl(m.valor_alvo)} ({m.progresso:g}%), faltam {brl(falta)}"
        if m.prazo and m.prazo > ctx.hoje:
            diferenca = relativedelta(m.prazo, ctx.hoje)
            meses = max(1, diferenca.years * 12 + diferenca.months + (1 if diferenca.days else 0))
            linha += f"; até {m.prazo.strftime('%d/%m/%Y')} dá cerca de {brl(falta / meses)} por mês"
        elif m.prazo:
            linha += f"; o prazo ({m.prazo.strftime('%d/%m/%Y')}) já passou"
        linhas.append(linha + ".")
    return _resp("\n".join(linhas), "metas")


def _alertas(ctx, mes, **_):
    alertas = Alerta.query.filter_by(usuario_id=ctx.uid).order_by(Alerta.categoria).all()
    if not alertas:
        return _resp("Você ainda não tem alertas. Em Alertas, defina um limite mensal por categoria e o sistema avisa quando o gasto passar dele.", "alertas")
    gastos = gastos_por_categoria(ctx.uid, mes)
    linhas = [f"Seus alertas em {nome_do_mes(mes)}:"]
    for a in alertas:
        gasto = gastos.get(a.categoria, 0.0)
        situacao = "desativado" if not a.ativo else "ULTRAPASSADO" if gasto >= a.limite else f"restam {brl(a.limite - gasto)}"
        linhas.append(f"• {a.categoria}: {brl(gasto)} de {brl(a.limite)} ({situacao})")
    return _resp("\n".join(linhas), "alertas")


def _parcelas(ctx, **_):
    meses = projecao_mensal(ctx.uid, ctx.renda, 6)
    comprometidos = [m for m in meses if m["comprometido"] > 0]
    if not comprometidos:
        return _resp("Você não tem parcelas futuras registradas. Compras parceladas cadastradas em Transações (ou vindas de um extrato) aparecem aqui.", "parcelas")
    linhas = ["Parcelas que já estão comprometidas nos próximos meses:"]
    for m in meses:
        linha = f"• {nome_do_mes(m['mes'])}: {brl(m['comprometido'])}"
        if m["saldo_livre"] is not None and m["comprometido"] > 0:
            linha += f" (sobram {brl(m['saldo_livre'])} da renda)"
        linhas.append(linha)
    return _resp("\n".join(linhas), "parcelas")


def _otimizar(ctx, mes, **_):
    g = calcular_do_mes(ctx.uid, mes)
    if "nos" not in g:                                                    # sem contas ou sem despesas
        return _resp(g["mensagem"], "otimizar")
    nome = nome_do_mes(mes)
    linhas = [f"Como pagar as despesas de {nome}:"]
    if g["total_registrado"] > 0:
        linhas.append(f"• Já pago em contas: {brl(g['total_registrado'])}.")
    if g["total_pendente"] <= 0:
        linhas.append("• Todas as despesas já têm conta definida: não há o que redistribuir.")
    else:
        linhas.append(f"• Ainda sem conta: {brl(g['total_pendente'])}. Sugestão:")
        por_conta = defaultdict(lambda: defaultdict(float))
        for p in g["plano"]:
            por_conta[p["conta"]][p["categoria"]] += p["valor"]
        for conta, categorias in por_conta.items():
            linhas.append(f"   – {conta}: {brl(sum(categorias.values()))} ({', '.join(categorias)})")
        if g["status"] == "gargalo":
            linhas.append(f"Atenção: {g['mensagem']}")
    beneficio = g["beneficio_total"]
    if beneficio:
        linhas.append(("Benefício estimado de cashback: " if beneficio > 0 else "Custo estimado de juros e taxas: ") + brl(abs(beneficio)) + ".")
    for x in g.get("excedeu_limite", []):
        linhas.append(f"Atenção: {x['conta']} passou do limite em {brl(x['excedeu'])} nas compras já registradas.")
    linhas.append("O mapa completo está no Otimizador.")
    return _resp("\n".join(linhas), "otimizar")


# ============================================================================= dicas

DICAS_CATEGORIA = {
    "Alimentação": "planejar as compras com lista e comparar preços costuma cortar o gasto com mercado sem mudar o que você come.",
    "Restaurante": "reduzir pedidos por aplicativo (taxas de entrega pesam) e combinar um número fixo de refeições fora por semana ajuda bastante.",
    "Transporte": "veja se dá para agrupar deslocamentos, usar transporte coletivo em alguns dias ou comparar o custo por quilômetro do aplicativo com o do carro.",
    "Lazer": "defina um teto mensal de lazer (um alerta aqui no sistema ajuda) e prefira programas gratuitos ou de baixo custo em parte do mês.",
    "Moradia": "é o gasto mais difícil de mexer, mas vale renegociar aluguel e condomínio, revisar contas de luz, água e internet e comparar planos.",
    "Vestuário": "esperar promoções e comprar só o que está na lista evita compras por impulso.",
    "Saúde": "compare preços de medicamentos (genéricos) e revise se o plano de saúde atual ainda é o mais adequado.",
    "Educação": "veja bolsas, descontos de pagamento antecipado e materiais usados ou digitais.",
    "Investimentos": "aportes não são gasto perdido, mas confirme que a sua reserva de emergência está em dia antes de aumentar.",
}


def _dicas(ctx, **_):
    mes = ctx.mes_atual
    r = resumo_mensal(ctx.uid, mes)
    categorias = sorted(gastos_por_categoria(ctx.uid, mes).items(), key=lambda x: -x[1])
    dicas = []
    if r["receita"] and r["despesa"] > r["receita"]:
        dicas.append(f"Suas despesas ({brl(r['despesa'])}) passaram das receitas do mês ({brl(r['receita'])}). Reveja o que dá para adiar ou cortar nas maiores categorias.")
    elif ctx.renda and r["despesa"] > 0.8 * ctx.renda:
        dicas.append(f"Você já usou {percentual(r['despesa'], ctx.renda)}% da renda mensal informada. Se possível, segure gastos não essenciais até o fim do mês.")
    if categorias and r["despesa"]:
        categoria, valor = categorias[0]
        participacao = percentual(valor, r["despesa"])
        if participacao >= 35 and categoria in DICAS_CATEGORIA:
            dicas.append(f"{categoria} é {participacao}% dos seus gastos ({brl(valor)}): {DICAS_CATEGORIA[categoria]}")
    gastos = dict(categorias)
    estourados = [a.categoria for a in Alerta.query.filter_by(usuario_id=ctx.uid, ativo=True).all() if gastos.get(a.categoria, 0.0) >= a.limite]
    if estourados:
        dicas.append(f"Você passou do limite em {', '.join(estourados)}. Segure novos gastos dessas categorias até virar o mês.")
    if ctx.renda:
        proximo = projecao_mensal(ctx.uid, ctx.renda, 1)[0]["comprometido"]
        if proximo >= 0.3 * ctx.renda:
            dicas.append(f"As parcelas já comprometem {percentual(proximo, ctx.renda)}% da renda do próximo mês. Evite novas compras parceladas por enquanto.")
    if not Meta.query.filter_by(usuario_id=ctx.uid).first():
        dicas.append("Crie uma meta em Metas, mesmo pequena. Guardar um valor fixo assim que o dinheiro entra funciona melhor do que guardar o que sobra.")
    if not Alerta.query.filter_by(usuario_id=ctx.uid).first():
        dicas.append("Crie alertas de gasto nas categorias em que você mais escorrega: o aviso na hora da compra ajuda a frear.")
    gerais = ["Anote todos os gastos por 30 dias: quem enxerga para onde o dinheiro vai quase sempre encontra o que cortar.",
              "Experimente a regra 50/30/20: 50% da renda para necessidades, 30% para desejos e 20% para guardar ou quitar dívidas.",
              "Use o Otimizador para escolher qual cartão ou conta paga cada despesa: o cashback acumulado de um ano pode virar um bom reforço.",
              "Compare preços antes de compras grandes e espere 48 horas antes de comprar por impulso."]
    for dica in gerais:
        if len(dicas) >= 4:
            break
        dicas.append(dica)
    cabecalho = f"Dicas com base nos seus números de {nome_do_mes(mes)}:" if r["despesa"] else "Dicas para economizar:"
    return _resp(cabecalho + "\n" + "\n".join(f"{i}) {d}" for i, d in enumerate(dicas[:4], start=1)), "dicas")


def _reserva(ctx, **_):
    base = [d for d in (resumo_mensal(ctx.uid, _mes_anterior(ctx.mes_atual, i))["despesa"] for i in (1, 2, 3)) if d > 0]
    media = round(sum(base) / len(base), 2) if base else None
    fonte = "média dos últimos meses"
    if media is None:                                          # sem meses fechados: usa o mes atual, avisando que ainda pode crescer
        media = resumo_mensal(ctx.uid, ctx.mes_atual)["despesa"] or None
        fonte = "só as despesas deste mês, que ainda podem crescer"
    linhas = ["Reserva de emergência é um dinheiro separado para imprevistos (perda de renda, problema de saúde, conserto urgente). "
              "A regra geral é guardar de 3 a 6 meses do seu custo de vida mensal (6 ou mais se a sua renda for instável)."]
    if media:
        meta3 = round(media * 3, 2)
        linhas.append(f"Pelas suas despesas ({brl(media)} por mês; {fonte}), isso seria:\n• 3 meses: {brl(meta3)}\n• 6 meses: {brl(media * 6)}")
        aporte = round((ctx.renda or media) * 0.10, 2)
        if aporte > 0:
            linhas.append(f"Guardando {brl(aporte)} por mês (10%), você chega aos 3 meses em cerca de {_plural(ceil(meta3 / aporte), 'mês', 'meses')}.")
    reserva = next((m for m in Meta.query.filter_by(usuario_id=ctx.uid).all() if "reserva" in T.alinhado(m.titulo)), None)
    if reserva:
        linhas.append(f"Você já tem a meta «{reserva.titulo}»: {brl(reserva.valor_atual)} de {brl(reserva.valor_alvo)} ({reserva.progresso:g}%).")
    else:
        linhas.append("Para acompanhar, crie uma meta em Metas com esse valor-alvo e vá depositando." if media else
                      "Registre alguns meses de gastos que eu calculo o valor ideal para você. Enquanto isso, crie uma meta em Metas e comece com um valor pequeno e fixo.")
    linhas.append("Onde manter: em algo com liquidez diária e baixo risco (por exemplo, Tesouro Selic ou CDB de liquidez diária). É orientação geral, não recomendação personalizada.")
    return _resp("\n".join(linhas), "reserva")


EDUCACAO = {
    "educ_orcamento": "A regra 50/30/20 divide a renda líquida em três partes: 50% para necessidades (moradia, comida, transporte, saúde), 30% para desejos (lazer, restaurantes, compras) "
                      "e 20% para guardar, investir ou quitar dívidas.\nÉ um ponto de partida: ajuste conforme a sua realidade. No SOS Virtual, o Painel mostra os gastos por categoria "
                      "para você comparar, e os Alertas ajudam a respeitar os limites que escolher.",
    "educ_dividas": "Para sair do vermelho:\n1) Liste todas as dívidas com valor, juros e atraso.\n2) Priorize as de juros mais altos (rotativo do cartão, cheque especial).\n"
                    "3) Procure o credor para renegociar: costuma haver desconto para pagamento à vista ou parcelamento menor.\n4) Corte gastos não essenciais por alguns meses e direcione o que sobrar para a dívida.\n"
                    "5) Evite novas dívidas enquanto isso.\nÉ orientação geral, não consultoria financeira.",
    "educ_investir": "Antes de investir: tenha a reserva de emergência e não invista dinheiro que você pode precisar no curto prazo.\nDepois, conheça o seu perfil e o prazo de cada objetivo: "
                     "renda fixa (Tesouro, CDB) tende a ser mais previsível; renda variável (ações, fundos) oscila mais e pede prazo longo. Diversificar reduz o risco.\n"
                     "É informação geral, não recomendação de investimento.",
    "educ_cartao": "Cartão de crédito é meio de pagamento, não renda extra. Boas práticas: pagar sempre a fatura inteira (o rotativo tem juros muito altos), "
                   "não usar o limite todo, acompanhar as parcelas já comprometidas e comparar benefícios (cashback, pontos). "
                   "Para ver qual cartão compensa mais para cada despesa, pergunte «qual cartão devo usar?» ou abra o Otimizador.",
    "educ_juros": "Juros compostos são juros sobre juros: o valor cresce cada vez mais rápido. Exemplo: R$ 1.000 a 2% ao mês viram cerca de R$ 1.268 em 12 meses (e não R$ 1.240). "
                  "Ótimo quando rende a seu favor; péssimo numa dívida, por isso o rotativo do cartão cresce tão depressa.",
    "educ_parcelar": "Parcelar sem juros pode valer a pena se você não perde desconto à vista e o valor cabe na renda dos próximos meses. Com juros, compare o total pago com o preço à vista: "
                     "em geral só compensa em emergências. Cuidado para não comprometer demais a renda: pergunte «tenho parcelas nos próximos meses?» para ver o quanto já está comprometido. "
                     "Em Transações > Compra parcelada o sistema calcula as parcelas e os juros.",
}

AJUDA = ("Posso ajudar com:\n"
         f"• Registrar gastos e receitas: {EXEMPLO_GASTO}, «recebi R$ 3.000 de salário», «paguei 120 de luz ontem no cartão Itaú».\n"
         "• Seus números: «como estão meus gastos este mês?», «qual meu saldo?», «quanto gastei com alimentação no mês passado?», «maiores gastos», «últimas transações», «quanto recebi em outubro?».\n"
         "• Metas, alertas e parcelas: «minhas metas», «meus alertas», «tenho parcelas nos próximos meses?».\n"
         "• Qual conta usar: «qual cartão devo usar para pagar minhas despesas?».\n"
         "• Dicas e educação financeira: «me dê dicas para economizar», «como montar uma reserva de emergência?», «como funciona a regra 50/30/20?».\n"
         "Tudo roda no próprio sistema: nenhum dado seu é enviado a serviços externos.")


# ========================================================================= orquestracao

def _tratar(ctx, intencao, msg, anterior=None):
    """executa a intencao; `anterior` (a pergunta anterior) completa o que faltar numa pergunta curta como 'e em outubro?'"""
    mes, explicito = T.extrair_periodo(msg, ctx.hoje)
    if not explicito and anterior:
        mes, _ = T.extrair_periodo(anterior, ctx.hoje)
    categoria = T.extrair_categoria(msg) or (T.extrair_categoria(anterior) if anterior else None)

    if intencao == "resumo" and categoria:
        return _gasto_categoria(ctx, mes=mes, categoria=categoria)
    if intencao in EDUCACAO:
        return _resp(EDUCACAO[intencao], intencao)
    simples = {"resumo": _resumo, "saldo": _saldo, "receitas": _receitas, "ultimas": _ultimas, "maiores": _maiores, "metas": _metas, "alertas": _alertas,
               "parcelas": _parcelas, "otimizar": _otimizar, "dicas": _dicas, "reserva": _reserva}
    if intencao in simples:
        return simples[intencao](ctx, mes=mes, categoria=categoria)
    if intencao == "ajuda":
        return _resp(AJUDA, "ajuda")
    if intencao == "saudacao":
        nome = f", {ctx.primeiro_nome}" if ctx.primeiro_nome else ""
        return _resp(f"Olá{nome}! Sou o assistente do SOS Virtual. Posso registrar seus gastos, mostrar seus números e dar dicas. "
                     f"Experimente: {EXEMPLO_GASTO}, «como estão meus gastos este mês?» ou «me dê dicas para economizar». Digite «ajuda» para ver tudo.", "saudacao")
    if intencao == "agradecimento":
        return _resp("De nada! Se precisar de mais alguma coisa, é só chamar.", "agradecimento")
    return None


def _pergunta_anterior(msg, historico):
    """a ultima pergunta do usuario (antes desta) que o assistente sabia responder, para completar 'e em outubro?'"""
    anteriores = [i for i in historico if i.get("role") == "user" and i.get("content", "").strip() != msg]
    for item in reversed(anteriores[-JANELA_DE_CONTEXTO:]):            # so as ultimas perguntas: contexto velho confunde
        if T.classificar(item["content"]) in INTENCOES_COM_PERIODO:
            return item["content"]
    return None


def responder(usuario_id, mensagem, historico=()):
    """
    devolve {"resposta": texto, "intencao": nome, "lancamento": dict | None, "alertas": [...]}
    `historico`: mensagens anteriores [{"role": "user" | "assistant", "content": texto}] (so usadas para completar perguntas curtas)
    """
    ctx = _Contexto(usuario_id)
    msg = mensagem.strip()
    tipo = T.tipo_do_lancamento(msg)
    status, valor, span = T.extrair_valor(msg)
    pergunta = T.eh_pergunta(msg)

    if tipo and not pergunta:
        return _registrar(ctx, msg, tipo, status, valor, span)

    intencao = T.classificar(msg)
    if intencao != "desconhecida":
        return _tratar(ctx, intencao, msg)

    if T.eh_complemento(msg):
        anterior = _pergunta_anterior(msg, historico)
        if anterior:
            return _tratar(ctx, T.classificar(anterior), msg, anterior=anterior)
    if status == "ok" and not pergunta:
        return _valor_sem_verbo(valor)
    return _resp("Não entendi bem. Posso registrar gastos (" + EXEMPLO_GASTO + "), mostrar resumos («como estão meus gastos?», «quanto gastei com alimentação no mês passado?»), "
                 "listar metas e alertas, sugerir qual conta usar e dar dicas. Digite «ajuda» para ver tudo.", "desconhecida")
