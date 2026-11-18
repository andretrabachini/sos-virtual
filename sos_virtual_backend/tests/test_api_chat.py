"""
testes da API do assistente (/api/chat): registrar por frase, perguntas sobre os dados, dicas e seguranca
rodar: py -m pytest tests/test_api_chat.py -v   (banco SQLite em memoria; veja conftest.py)
"""
import pytest
from dateutil.relativedelta import relativedelta

from servicos.tempo import hoje


def iso(d):
    return d.strftime("%Y-%m-%d")


@pytest.fixture()
def ana(cliente):
    r = cliente.post("/api/auth/cadastro", json={"nome": "Ana Teste", "email": "ana@x.com", "senha": "senha1234", "renda_mensal": 5000, "lgpd_aceito": True})
    return {"Authorization": "Bearer " + r.get_json()["token"]}


@pytest.fixture()
def bia(cliente):
    r = cliente.post("/api/auth/cadastro", json={"nome": "Bia Teste", "email": "b@x.com", "senha": "senha1234", "lgpd_aceito": True})
    return {"Authorization": "Bearer " + r.get_json()["token"]}


def diz(c, h, mensagem, historico=None):
    r = c.post("/api/chat", headers=h, json={"mensagem": mensagem, **({"historico": historico} if historico is not None else {})})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def lancamentos(c, h, mes=None):
    return c.get("/api/transacoes" + (f"?mes={mes}" if mes else ""), headers=h).get_json()


def gasto(c, h, descricao, valor, **extra):
    r = c.post("/api/transacoes", headers=h, json={"descricao": descricao, "valor": valor, **extra})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def conta(c, h, nome, **extra):
    assert c.post("/api/contas", headers=h, json={"nome": nome, **extra}).status_code == 201


MES_PASSADO = lambda: hoje() - relativedelta(months=1, day=10)


# ================================================================================ contrato
def test_chat_exige_login(cliente):
    assert cliente.post("/api/chat", json={"mensagem": "oi"}).status_code == 401


def test_resposta_tem_os_campos_combinados(cliente, ana):
    r = diz(cliente, ana, "oi")
    assert set(r) == {"resposta", "intencao", "lancamento", "alertas"} and r["intencao"] == "saudacao" and r["lancamento"] is None and r["alertas"] == []
    assert "Ana" in r["resposta"]


@pytest.mark.parametrize("corpo", [{}, {"mensagem": ""}, {"mensagem": "   "}, {"mensagem": 5}, {"mensagem": ["oi"]}, {"mensagem": None}, {"mensagem": "a" * 501}])
def test_mensagem_invalida(cliente, ana, corpo):
    assert cliente.post("/api/chat", headers=ana, json=corpo).status_code == 400


def test_corpo_quebrado(cliente, ana):
    assert cliente.post("/api/chat", headers=ana, data="isto nao e json", content_type="application/json").status_code == 400


def test_mensagem_de_500_caracteres_e_aceita(cliente, ana):
    assert cliente.post("/api/chat", headers=ana, json={"mensagem": "a" * 500}).status_code == 200


@pytest.mark.parametrize("historico", ["texto", 5, [1, 2], [{"role": "system", "content": "x"}], [{"role": "user"}], [{"role": "user", "content": 5}], [None], {"role": "user"}])
def test_historico_fora_do_formato_e_ignorado(cliente, ana, historico):
    assert cliente.post("/api/chat", headers=ana, json={"mensagem": "oi", "historico": historico}).status_code == 200


def test_limite_de_mensagens_por_minuto(cliente, ana):
    from extensoes import limiter
    limiter.enabled = True
    limiter.reset()
    codigos = [cliente.post("/api/chat", headers=ana, json={"mensagem": "oi"}).status_code for _ in range(32)]
    assert codigos[:30] == [200] * 30 and 429 in codigos[30:]


# ============================================================================== registrar
def test_registrar_um_gasto(cliente, ana):
    r = diz(cliente, ana, "gastei R$ 50 no mercado hoje")
    assert r["intencao"] == "registrar" and r["resposta"].startswith("Registrei o gasto: Mercado, R$ 50,00, categoria Alimentação, hoje, sem conta definida.")
    saved = lancamentos(cliente, ana)
    assert len(saved) == 1 and (saved[0]["descricao"], saved[0]["valor"], saved[0]["categoria"], saved[0]["conta"]) == ("Mercado", -50, "Alimentação", None)
    assert saved[0]["data"].startswith(iso(hoje()))
    assert {k: r["lancamento"][k] for k in ("id", "descricao", "valor", "categoria", "conta")} == {"id": saved[0]["id"], "descricao": "Mercado", "valor": -50, "categoria": "Alimentação", "conta": None}


def test_registrar_uma_receita(cliente, ana):
    r = diz(cliente, ana, "recebi 3000 de salário")
    assert r["resposta"].startswith("Registrei a receita: Salário, R$ 3.000,00, categoria Salário, hoje.")
    t = lancamentos(cliente, ana)[0]
    assert (t["valor"], t["categoria"], t["conta"]) == (3000, "Salário", None)


def test_registrar_com_conta_e_data(cliente, ana):
    conta(cliente, ana, "Cartão Itaú")
    r = diz(cliente, ana, "paguei 120,50 de luz ontem no cartão Itaú")
    ontem = hoje() - relativedelta(days=1)
    assert f"{ontem.strftime('%d/%m/%Y')}, na conta Cartão Itaú." in r["resposta"]
    t = lancamentos(cliente, ana)[0]
    assert (t["descricao"], t["valor"], t["categoria"], t["conta"]) == ("Luz", -120.5, "Moradia", "Cartão Itaú") and t["data"].startswith(iso(ontem))


@pytest.mark.parametrize("frase,esperada", [("dia 3", lambda h: h.replace(day=3)), ("em 3 de outubro", lambda h: h.replace(month=10, day=3) if h.month >= 10 else h.replace(year=h.year - 1, month=10, day=3)),
                                              ("anteontem", lambda h: h - relativedelta(days=2))])
def test_registrar_com_varias_formas_de_data(cliente, ana, frase, esperada):
    if frase == "dia 3" and hoje().day < 3:
        pytest.skip("o dia 3 ainda nao chegou neste mes")
    diz(cliente, ana, f"gastei 20 no pão {frase}")
    assert lancamentos(cliente, ana)[0]["data"].startswith(iso(esperada(hoje())))


def test_dia_que_ainda_nao_chegou_vai_para_o_mes_passado(cliente, ana):
    if hoje().day >= 28:
        pytest.skip("so testavel antes do dia 28")
    dia = hoje().day + 1
    diz(cliente, ana, f"gastei 20 no pão dia {dia}")
    esperada = hoje().replace(day=1) - relativedelta(months=1)
    assert lancamentos(cliente, ana)[0]["data"].startswith(iso(esperada.replace(day=dia)))


def test_registrar_usa_as_mesmas_regras_do_formulario(cliente, ana):
    gasto(cliente, ana, "mercado do bairro", -50)
    diz(cliente, ana, "gastei 50 no mercado do bairro")
    a, b = lancamentos(cliente, ana)
    assert (a["categoria"], a["valor"]) == (b["categoria"], b["valor"])


def test_registrar_dispara_o_alerta_de_limite(cliente, ana):
    cliente.post("/api/alertas", headers=ana, json={"categoria": "Lazer", "limite": 100})
    r = diz(cliente, ana, "gastei 150 no cinema")
    assert len(r["alertas"]) == 1 and r["alertas"][0]["categoria"] == "Lazer" and r["alertas"][0]["excesso"] == 50
    assert "Atenção: os gastos com Lazer chegaram a R$ 150,00, acima do limite de R$ 100,00." in r["resposta"]
    outro = diz(cliente, ana, "gastei 10 no cinema")                                  # continua acima do limite: avisa de novo, como o formulario
    assert [a["categoria"] for a in outro["alertas"]] == ["Lazer"] and outro["alertas"][0]["excesso"] == 60
    assert "R$ 160,00, acima do limite de R$ 100,00" in outro["resposta"]


def test_desfazer_pelo_id_devolvido(cliente, ana):
    r = diz(cliente, ana, "gastei 50 no mercado")
    assert cliente.delete(f"/api/transacoes/{r['lancamento']['id']}", headers=ana).status_code == 200
    assert lancamentos(cliente, ana) == []


def test_conta_desconhecida_registra_sem_conta_e_avisa(cliente, ana):
    r = diz(cliente, ana, "gastei 30 no cartão Nubank no uber")
    assert "Não achei uma conta chamada «Nubank»" in r["resposta"] and "sem conta definida" in r["resposta"]
    assert lancamentos(cliente, ana)[0]["conta"] is None and lancamentos(cliente, ana)[0]["descricao"] == "Uber"
    assert cliente.get("/api/contas", headers=ana).get_json() == []                     # o assistente nunca cria conta sozinho


def test_vale_recusa_categoria_fora_da_regra_e_nada_e_salvo(cliente, ana):
    conta(cliente, ana, "Vale Alimentação", categorias=["Alimentação"])
    r = diz(cliente, ana, "gastei 400 de aluguel no vale alimentação")
    assert r["resposta"].startswith("Não registrei esse lançamento.") and "só paga: Alimentação" in r["resposta"] and r["lancamento"] is None
    assert lancamentos(cliente, ana) == []
    diz(cliente, ana, "gastei 80 no mercado no vale alimentação")
    assert lancamentos(cliente, ana)[0]["conta"] == "Vale Alimentação"


def test_conta_ambigua_pergunta(cliente, ana):
    conta(cliente, ana, "Cartão Itaú")
    conta(cliente, ana, "Conta Itaú")
    r = diz(cliente, ana, "gastei 50 no itaú")
    assert "mais de uma conta" in r["resposta"] and lancamentos(cliente, ana) == []


@pytest.mark.parametrize("frase,trecho", [
    ("comprei um notebook de 3000 em 10x", "Compra parcelada"), ("parcelei uma TV de 2000", "Compra parcelada"),
    ("gastei 50 e 30", "mais de um valor"), ("gastei 10 de gasolina e 20 de lanche", "mais de um valor"),
    ("recebi e gastei 50", "um gasto e uma receita"), ("gastei no mercado", "não achei o valor"), ("gastei 0 no mercado", "não é válido"),
    ("gastei 50", "Com o que foi esse gasto"), ("recebi 100", "Com o que foi essa receita"),
    ("gastei 50 no mercado em 31/02", "não existe"), ("gastei 50 no mercado em 10/05/2018", "5 anos atrás"), ("gastei 15 em outubro no mercado", "Em que dia de outubro"),
    ("50", "não sei se é um gasto ou uma receita"), ("mercado 50", "não sei se é um gasto ou uma receita"),
])
def test_o_que_nao_pode_ser_registrado_nao_e_salvo(cliente, ana, frase, trecho):
    r = diz(cliente, ana, frase)
    assert trecho in r["resposta"] and r["lancamento"] is None and lancamentos(cliente, ana) == [], frase


def test_pergunta_com_valor_nao_registra(cliente, ana):
    r = diz(cliente, ana, "quanto gastei com mercado 50?")
    assert r["intencao"] != "registrar" and lancamentos(cliente, ana) == []


def test_so_registra_na_conta_de_quem_pediu(cliente, ana, bia):
    conta(cliente, bia, "Cartão da Bia")
    r = diz(cliente, ana, "gastei 50 no mercado no cartão da bia")
    assert "Não achei uma conta chamada «bia»" in r["resposta"]
    assert lancamentos(cliente, ana)[0]["conta"] is None and lancamentos(cliente, bia) == []


# =============================================================================== consultas
def popular(c, h):
    gasto(c, h, "Salário", 5000)
    gasto(c, h, "Aluguel", -1600)
    gasto(c, h, "Mercado", -300)
    gasto(c, h, "Uber", -100)
    gasto(c, h, "Compra antiga", -1000, categoria="Lazer", data=iso(MES_PASSADO()))


def test_resumo_do_mes(cliente, ana):
    popular(cliente, ana)
    r = diz(cliente, ana, "Como estão meus gastos este mês?")
    texto = r["resposta"]
    assert r["intencao"] == "resumo" and "Receitas: R$ 5.000,00" in texto and "Despesas: R$ 2.000,00" in texto and "Saldo: R$ 3.000,00" in texto
    assert "Moradia R$ 1.600,00 (80%)" in texto and "Alimentação R$ 300,00 (15%)" in texto
    assert "as despesas subiram 100%" in texto                                         # 1.000 no mes passado -> 2.000
    assert "40% da renda mensal informada (R$ 5.000,00)" in texto


def test_resumo_no_vermelho(cliente, ana):
    gasto(cliente, ana, "Salário", 1000)
    gasto(cliente, ana, "Aluguel", -1500)
    assert "Saldo: -R$ 500,00 (no vermelho)" in diz(cliente, ana, "resumo")["resposta"]


def test_resumo_de_mes_sem_dados(cliente, ana):
    r = diz(cliente, ana, "como estão meus gastos?")
    assert "Ainda não há lançamentos em" in r["resposta"] and r["lancamento"] is None


def test_resumo_avisa_alerta_ultrapassado(cliente, ana):
    cliente.post("/api/alertas", headers=ana, json={"categoria": "Lazer", "limite": 100})
    gasto(cliente, ana, "Cinema", -150)
    assert "Atenção: Lazer passou do limite (R$ 150,00 de R$ 100,00)." in diz(cliente, ana, "resumo do mês")["resposta"]


def test_gasto_por_categoria(cliente, ana):
    popular(cliente, ana)
    cliente.post("/api/alertas", headers=ana, json={"categoria": "Alimentação", "limite": 500})
    r = diz(cliente, ana, "quanto gastei com mercado?")
    assert r["intencao"] == "gasto_categoria" and "gastou R$ 300,00 com Alimentação (15% das despesas do mês, 1 compra)" in r["resposta"]
    assert "Mercado R$ 300,00" in r["resposta"] and "ainda restam R$ 200,00" in r["resposta"]


def test_gasto_por_categoria_sem_gastos(cliente, ana):
    popular(cliente, ana)
    assert "Não encontrei gastos de Saúde em" in diz(cliente, ana, "quanto gastei com saúde?")["resposta"]


def test_outro_mes_por_nome_e_por_expressao(cliente, ana):
    popular(cliente, ana)
    mes = MES_PASSADO()
    nome = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"][mes.month - 1]
    for frase in ("quanto gastei com lazer no mês passado?", f"quanto gastei com lazer em {nome}?"):
        assert "gastou R$ 1.000,00 com Lazer" in diz(cliente, ana, frase)["resposta"], frase


def test_receitas(cliente, ana):
    popular(cliente, ana)
    r = diz(cliente, ana, "quanto recebi este mês?")
    assert r["intencao"] == "receitas" and "recebeu R$ 5.000,00 (1 entrada)" in r["resposta"] and "• Salário: R$ 5.000,00" in r["resposta"]
    assert "Não encontrei receitas" in diz(cliente, ana, "quanto recebi no mês passado?")["resposta"]


def test_ultimas_transacoes_com_a_conta(cliente, ana):
    conta(cliente, ana, "Cartão Itaú")
    gasto(cliente, ana, "Gasolina", -85, conta="Cartão Itaú")
    gasto(cliente, ana, "Salário", 3000)
    r = diz(cliente, ana, "últimas transações")["resposta"]
    assert "-R$ 85,00 (Cartão Itaú)" in r and "+R$ 3.000,00" in r


def test_ultimas_sem_lancamentos(cliente, ana):
    assert "ainda não tem lançamentos" in diz(cliente, ana, "últimas transações")["resposta"]


def test_maiores_gastos(cliente, ana):
    popular(cliente, ana)
    r = diz(cliente, ana, "maiores gastos")["resposta"]
    assert r.index("1) Aluguel: R$ 1.600,00") < r.index("2) Mercado: R$ 300,00") < r.index("3) Uber: R$ 100,00") and "Moradia R$ 1.600,00 (80%)" in r
    assert "Maiores despesas de" in diz(cliente, ana, "maiores gastos de transporte")["resposta"] and "1) Uber" in diz(cliente, ana, "maiores gastos de transporte")["resposta"]


def test_metas(cliente, ana):
    prazo = hoje() + relativedelta(months=10)
    cliente.post("/api/metas", headers=ana, json={"titulo": "Viagem", "valor_alvo": 5000, "valor_atual": 500, "prazo": iso(prazo)})
    cliente.post("/api/metas", headers=ana, json={"titulo": "Celular", "valor_alvo": 1000, "valor_atual": 1000})
    r = diz(cliente, ana, "minhas metas")["resposta"]
    assert "• Viagem: R$ 500,00 de R$ 5.000,00 (10%), faltam R$ 4.500,00" in r and "por mês" in r and "• Celular: concluída (R$ 1.000,00)." in r


def test_metas_vazio_e_prazo_vencido(cliente, ana):
    assert "ainda não tem metas" in diz(cliente, ana, "minhas metas")["resposta"]
    cliente.post("/api/metas", headers=ana, json={"titulo": "Antiga", "valor_alvo": 100, "prazo": iso(hoje() + relativedelta(days=1))})
    assert "• Antiga: R$ 0,00 de R$ 100,00" in diz(cliente, ana, "metas")["resposta"]


def test_alertas(cliente, ana):
    gasto(cliente, ana, "Cinema", -150)
    cliente.post("/api/alertas", headers=ana, json={"categoria": "Lazer", "limite": 100})
    cliente.post("/api/alertas", headers=ana, json={"categoria": "Transporte", "limite": 300})
    a = cliente.get("/api/alertas", headers=ana).get_json()
    cliente.put(f"/api/alertas/{[x for x in a if x['categoria'] == 'Transporte'][0]['id']}", headers=ana, json={"ativo": False})
    r = diz(cliente, ana, "meus alertas")["resposta"]
    assert "• Lazer: R$ 150,00 de R$ 100,00 (ULTRAPASSADO)" in r and "• Transporte: R$ 0,00 de R$ 300,00 (desativado)" in r


def test_alertas_vazio(cliente, ana):
    assert "ainda não tem alertas" in diz(cliente, ana, "meus alertas")["resposta"]


def test_parcelas_futuras(cliente, ana):
    conta(cliente, ana, "Cartão Meli")
    assert cliente.post("/api/parcelamentos", headers=ana, json={"descricao": "TV", "valor_vista": 600, "parcelas": 3, "conta": "Cartão Meli"}).status_code == 201
    r = diz(cliente, ana, "tenho parcelas nos próximos meses?")["resposta"]
    assert "comprometidas" in r and "R$ 200,00" in r and "sobram R$ 4.800,00 da renda" in r


def test_parcelas_vazio(cliente, ana):
    assert "não tem parcelas futuras" in diz(cliente, ana, "tenho parcelas nos próximos meses?")["resposta"]


def test_otimizador_sugere_a_conta(cliente, ana):
    conta(cliente, ana, "Cartão Itaú", capacidade=3000, custo=-2)
    gasto(cliente, ana, "Aluguel", -1000)
    gasto(cliente, ana, "Gasolina", -200, conta="Cartão Itaú")
    r = diz(cliente, ana, "qual cartão devo usar para pagar minhas despesas?")
    assert r["intencao"] == "otimizar" and "Já pago em contas: R$ 200,00" in r["resposta"] and "Ainda sem conta: R$ 1.000,00" in r["resposta"]
    assert "– Cartão Itaú: R$ 1.000,00 (Moradia)" in r["resposta"] and "cashback: R$ 24,00" in r["resposta"]


def test_otimizador_sem_contas_nem_despesas_nao_quebra(cliente, ana):
    for frase in ("qual cartão devo usar?", "como pagar minhas despesas?"):
        r = diz(cliente, ana, frase)
        assert r["intencao"] == "otimizar" and r["resposta"]
    gasto(cliente, ana, "Aluguel", -1000)
    assert diz(cliente, ana, "qual cartão devo usar?")["resposta"]               # despesas, mas nenhuma conta cadastrada


def test_otimizador_tudo_ja_com_conta(cliente, ana):
    conta(cliente, ana, "Cartão Itaú", capacidade=3000)
    gasto(cliente, ana, "Aluguel", -1000, conta="Cartão Itaú")
    assert "não há o que redistribuir" in diz(cliente, ana, "qual cartão devo usar?")["resposta"]


def test_dicas_personalizadas(cliente, ana):
    popular(cliente, ana)
    r = diz(cliente, ana, "me dê dicas para economizar")["resposta"]
    assert r.startswith("Dicas com base nos seus números de") and "Moradia é 80% dos seus gastos (R$ 1.600,00)" in r and "Crie uma meta em Metas" in r and r.count(")") >= 4


def test_dicas_no_vermelho_e_gerais(cliente, ana):
    gasto(cliente, ana, "Salário", 1000)
    gasto(cliente, ana, "Aluguel", -1500)
    assert "passaram das receitas do mês" in diz(cliente, ana, "dicas")["resposta"]


def test_dicas_sem_dados(cliente, ana):
    r = diz(cliente, ana, "me dê dicas para economizar")["resposta"]
    assert r.startswith("Dicas para economizar:") and "1)" in r and "regra 50/30/20" in r


def test_reserva_de_emergencia_com_historico(cliente, ana):
    for meses_atras in (1, 2, 3):
        gasto(cliente, ana, "Gastos do mês", -2000, data=iso(hoje().replace(day=10) - relativedelta(months=meses_atras)))
    r = diz(cliente, ana, "Como montar uma reserva de emergência?")["resposta"]
    assert "2.000,00 por mês; média dos últimos meses" in r and "3 meses: R$ 6.000,00" in r and "6 meses: R$ 12.000,00" in r and "em cerca de 12 meses" in r


def test_reserva_com_meta_existente_e_sem_dados(cliente, ana):
    assert "Registre alguns meses de gastos" in diz(cliente, ana, "reserva de emergência")["resposta"]
    cliente.post("/api/metas", headers=ana, json={"titulo": "Reserva de emergência", "valor_alvo": 10000, "valor_atual": 2500})
    assert "Você já tem a meta «Reserva de emergência»: R$ 2.500,00 de R$ 10.000,00 (25%)" in diz(cliente, ana, "reserva de emergência")["resposta"]


@pytest.mark.parametrize("frase,intencao,trecho", [
    ("como funciona a regra 50/30/20?", "educ_orcamento", "50% para necessidades"), ("quero sair do vermelho", "educ_dividas", "Para sair do vermelho"),
    ("devo investir?", "educ_investir", "não recomendação de investimento"), ("como usar o cartão de crédito?", "educ_cartao", "pagar sempre a fatura inteira"),
    ("o que são juros compostos?", "educ_juros", "R$ 1.268"), ("vale a pena parcelar?", "educ_parcelar", "Parcelar sem juros"),
])
def test_educacao_financeira(cliente, ana, frase, intencao, trecho):
    r = diz(cliente, ana, frase)
    assert r["intencao"] == intencao and trecho in r["resposta"]


def test_ajuda_saudacao_agradecimento_e_desconhecida(cliente, ana):
    assert "nenhum dado seu é enviado a serviços externos" in diz(cliente, ana, "o que você faz?")["resposta"]
    assert diz(cliente, ana, "bom dia")["intencao"] == "saudacao" and diz(cliente, ana, "obrigado!")["intencao"] == "agradecimento"
    r = diz(cliente, ana, "asdfgh")
    assert r["intencao"] == "desconhecida" and "Não entendi bem" in r["resposta"]


# ============================================================================ continuacao
def test_complemento_usa_a_pergunta_anterior(cliente, ana):
    popular(cliente, ana)
    h = [{"role": "user", "content": "quanto gastei com lazer?"}, {"role": "assistant", "content": "..."}, {"role": "user", "content": "e no mês passado?"}]
    r = diz(cliente, ana, "e no mês passado?", h)
    assert "gastou R$ 1.000,00 com Lazer" in r["resposta"]                              # manteve a categoria e trocou o mes


def test_complemento_troca_a_categoria_e_mantem_o_mes(cliente, ana):
    popular(cliente, ana)
    h = [{"role": "user", "content": "quanto gastei com lazer no mês passado?"}, {"role": "assistant", "content": "..."}, {"role": "user", "content": "e com transporte?"}]
    assert "Não encontrei gastos de Transporte em" in diz(cliente, ana, "e com transporte?", h)["resposta"]


def test_complemento_sem_contexto_ou_com_contexto_velho_nao_adivinha(cliente, ana):
    assert diz(cliente, ana, "e em outubro?")["intencao"] == "desconhecida"
    velho = [{"role": "user", "content": "quanto gastei com lazer?"}] + [{"role": "user", "content": x} for x in ("oi", "obrigado", "asdf", "e em outubro?")]
    assert diz(cliente, ana, "e em outubro?", velho)["intencao"] == "desconhecida"


# =============================================================================== isolamento
def test_cada_usuario_ve_so_os_proprios_dados(cliente, ana, bia):
    popular(cliente, ana)
    gasto(cliente, bia, "Padaria", -30)
    resumo_bia = diz(cliente, bia, "como estão meus gastos?")["resposta"]
    assert "Despesas: R$ 30,00" in resumo_bia and "1.600" not in resumo_bia
    assert "Aluguel" not in diz(cliente, bia, "últimas transações")["resposta"] and "Aluguel" not in diz(cliente, bia, "maiores gastos")["resposta"]
    assert "Padaria" not in diz(cliente, ana, "últimas transações")["resposta"]
    cliente.post("/api/metas", headers=ana, json={"titulo": "Meta da Ana", "valor_alvo": 100})
    assert "Meta da Ana" not in diz(cliente, bia, "minhas metas")["resposta"]


def test_o_texto_digitado_nao_vira_comando(cliente, ana):
    """a descricao vem do que o usuario digitou: e guardada como texto (a tela escapa na exibicao), nunca executada"""
    r = diz(cliente, ana, "gastei 50 em <script>alert('x')</script> hoje'; DROP TABLE transacoes;--")
    assert r["intencao"] == "registrar" and r["lancamento"]["id"]
    salvo = lancamentos(cliente, ana)
    assert len(salvo) == 1 and "<script>" in salvo[0]["descricao"]                       # guardado como texto puro
    assert cliente.get("/api/dashboard", headers=ana).status_code == 200 and cliente.get("/api/transacoes", headers=ana).status_code == 200   # a tabela continua la


def test_numeros_dentro_de_codigo_deixam_a_frase_ambigua_e_nada_e_salvo(cliente, ana):
    r = diz(cliente, ana, "gastei 50 em <script>alert(1)</script>")
    assert r["lancamento"] is None and lancamentos(cliente, ana) == [] and "mais de um valor" in r["resposta"]
