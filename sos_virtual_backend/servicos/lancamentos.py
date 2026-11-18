"""
regras de gravacao de uma despesa ou receita, compartilhadas pelo formulario (rota /api/transacoes) e pelo assistente (/api/chat)
assim as duas portas de entrada seguem exatamente as mesmas regras: vale so paga as categorias dele, alertas, intervalo de datas
"""
from dateutil.relativedelta import relativedelta

from database import db
from modelos.modelos import Transacao
from servicos.alertas_service import alertas_ultrapassados, fotografar_alertas
from servicos.contas import ContaInvalida, checar_categoria, conta_por_nome, nomes_das_contas, transacao_com_conta
from servicos.tempo import agora, hoje


def data_da_compra(data):
    """
    confere o intervalo permitido (de 5 anos atras ate 12 meses a frente) e devolve (datetime, None) ou (None, mensagem)
    uma compra de hoje guarda a hora de agora (ordem dentro do dia); as demais, meia-noite
    """
    data = data.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    hoje_ = hoje()
    if not hoje_ - relativedelta(years=5) <= data <= hoje_ + relativedelta(months=12):
        return None, "a data deve estar entre 5 anos atrás e 12 meses à frente"
    return (agora() if data == hoje_ else data), None


def gravar_transacao(usuario_id, descricao, valor, categoria, data=None, nome_conta=None):
    """
    grava a transacao (valor negativo = despesa) e devolve o dicionario dela com a lista "alertas" (limites ultrapassados por ela)
    a conta so vale para despesas; uma conta nova e criada na hora. levanta ContaInvalida (com o banco ja desfeito)
    se a conta nao puder receber a categoria (vale) ou o limite de contas foi atingido
    os campos ja devem estar validados por quem chama
    """
    antes = fotografar_alertas(usuario_id) if valor < 0 else None       # so despesas mexem nos alertas

    conta_id = None
    if nome_conta and valor < 0:
        try:
            conta = conta_por_nome(usuario_id, nome_conta, criar=True)
            checar_categoria(usuario_id, conta, categoria)
        except ContaInvalida:
            db.session.rollback()
            raise
        conta_id = conta.id

    nova = Transacao(usuario_id=usuario_id, descricao=descricao, valor=valor, categoria=categoria, conta_id=conta_id)
    if data is not None:
        nova.data = data
    db.session.add(nova)
    db.session.commit()

    resposta = transacao_com_conta(nova, nomes_das_contas(usuario_id))
    resposta["alertas"] = alertas_ultrapassados(usuario_id, antes)       # o front mostra um pop-up com eles
    return resposta
