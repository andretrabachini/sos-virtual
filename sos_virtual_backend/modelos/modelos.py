from database import db
from datetime import datetime


# tabela de usuarios — guarda nome, email, senha e renda mensal
class Usuario(db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(256), nullable=False)

    # renda mensal serve para calcular limites e alertas de gasto
    renda_mensal = db.Column(db.Float, default=0.0)

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # data e hora em que o usuario aceitou o tratamento de dados (prova do consentimento LGPD)
    lgpd_aceito_em = db.Column(db.DateTime, nullable=True)

    # relacionamentos: um usuario tem varias transacoes, metas e alertas
    # cascade garante que, ao excluir a conta, todos os dados dela somem junto (direito de eliminacao da LGPD)
    transacoes = db.relationship("Transacao", backref="usuario", lazy=True, cascade="all, delete-orphan")
    metas = db.relationship("Meta", backref="usuario", lazy=True, cascade="all, delete-orphan")
    alertas = db.relationship("Alerta", backref="usuario", lazy=True, cascade="all, delete-orphan")
    arestas = db.relationship("Aresta", backref="usuario", lazy=True, cascade="all, delete-orphan")
    nos = db.relationship("No", backref="usuario", lazy=True, cascade="all, delete-orphan")
    redefinicoes = db.relationship("RedefinicaoSenha", backref="usuario", lazy=True, cascade="all, delete-orphan")
    contas_categorias = db.relationship("ContaCategoria", backref="usuario", lazy=True, cascade="all, delete-orphan")
    parcelamentos = db.relationship("Parcelamento", backref="usuario", lazy=True, cascade="all, delete-orphan")

    def para_dict(self):
        return {
            "id": self.id,
            "nome": self.nome,
            "email": self.email,
            "renda_mensal": self.renda_mensal
        }


# tabela de transacoes — registra cada gasto ou receita do usuario
class Transacao(db.Model):
    __tablename__ = "transacoes"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    descricao = db.Column(db.String(255), nullable=False)

    # valor positivo = receita, valor negativo = despesa
    valor = db.Column(db.Float, nullable=False)

    categoria = db.Column(db.String(80), default="Outros")
    data = db.Column(db.DateTime, default=datetime.utcnow)

    def para_dict(self):
        return {
            "id": self.id,
            "descricao": self.descricao,
            "valor": self.valor,
            "categoria": self.categoria,
            "data": self.data.isoformat(),
            # define se e receita ou despesa com base no sinal do valor
            "tipo": "receita" if self.valor > 0 else "despesa"
        }


# tabela de metas — o usuario define um objetivo financeiro e acompanha o progresso
class Meta(db.Model):
    __tablename__ = "metas"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    titulo = db.Column(db.String(120), nullable=False)
    valor_alvo = db.Column(db.Float, nullable=False)

    # valor_atual vai sendo atualizado conforme o usuario deposita na meta
    valor_atual = db.Column(db.Float, default=0.0)

    prazo = db.Column(db.DateTime, nullable=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def progresso(self):
        # calcula a porcentagem de progresso da meta
        if self.valor_alvo == 0:
            return 0
        return round((self.valor_atual / self.valor_alvo) * 100, 1)

    def para_dict(self):
        return {
            "id": self.id,
            "titulo": self.titulo,
            "valor_alvo": self.valor_alvo,
            "valor_atual": self.valor_atual,
            "progresso": self.progresso,
            "prazo": self.prazo.isoformat() if self.prazo else None
        }


# tabela de alertas — define limites de gasto por categoria
class Alerta(db.Model):
    __tablename__ = "alertas"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    categoria = db.Column(db.String(80), nullable=False)

    # quando o gasto da categoria ultrapassar esse limite, o alerta dispara
    limite = db.Column(db.Float, nullable=False)

    # ativo define se o alerta esta ligado ou nao
    ativo = db.Column(db.Boolean, default=True)

    def para_dict(self):
        return {
            "id": self.id,
            "categoria": self.categoria,
            "limite": self.limite,
            "ativo": self.ativo
        }


# tabela de nos — os vertices do grafo financeiro (contas, cartoes, categorias, metas, rendas)
class No(db.Model):
    __tablename__ = "nos"
    # o mesmo usuario nao pode ter dois nos com o mesmo nome e tipo
    __table_args__ = (
        db.UniqueConstraint("usuario_id", "nome", "tipo", name="uq_no_usuario_nome_tipo"),
    )

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    nome = db.Column(db.String(100), nullable=False)

    # tipo do no: 'conta', 'categoria', 'meta' ou 'renda'
    tipo = db.Column(db.String(50), nullable=False)

    # so para contas/cartoes (usados pelo servico de grafos):
    # capacidade = quanto a conta consegue pagar no mes (limite do cartao, saldo disponivel)
    capacidade = db.Column(db.Numeric(12, 2, asdecimal=False), nullable=True)
    # custo = percentual por R$ movimentado: negativo = cashback/beneficio, positivo = juros/taxa
    custo = db.Column(db.Float, default=0.0)

    def para_dict(self):
        return {
            "id": self.id,
            "nome": self.nome,
            "tipo": self.tipo,
            "capacidade": self.capacidade,
            "custo": self.custo
        }


# tabela de arestas — as ligacoes direcionadas do grafo: de onde o dinheiro sai e para onde vai
# aqui ficam principalmente as parcelas FUTURAS de compras parceladas (projetada=True),
# que mostram quanto da renda dos proximos meses ja esta comprometido
class Aresta(db.Model):
    __tablename__ = "arestas"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    origem_id = db.Column(db.Integer, db.ForeignKey("nos.id"), nullable=False)
    destino_id = db.Column(db.Integer, db.ForeignKey("nos.id"), nullable=False)

    # valor em R$ (sempre positivo; a direcao ja diz quem paga e quem recebe)
    peso = db.Column(db.Numeric(12, 2, asdecimal=False), nullable=False)
    data = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    descricao = db.Column(db.String(255))

    # True = parcela futura ainda nao paga (projecao); False = movimento real
    projetada = db.Column(db.Boolean, default=False, nullable=False)
    parcela_atual = db.Column(db.Integer, nullable=True)
    total_parcelas = db.Column(db.Integer, nullable=True)

    # grupo_parcelamento: todas as parcelas criadas juntas; chave_compra: identifica a mesma
    # compra em extratos de meses diferentes (evita contar a mesma parcela duas vezes)
    grupo_parcelamento = db.Column(db.String(32), nullable=True)
    chave_compra = db.Column(db.String(220), nullable=True, index=True)

    def para_dict(self):
        return {
            "id": self.id,
            "origem_id": self.origem_id,
            "destino_id": self.destino_id,
            "peso": self.peso,
            "data": self.data.isoformat() if self.data else None,
            "descricao": self.descricao,
            "projetada": self.projetada,
            "parcela_atual": self.parcela_atual,
            "total_parcelas": self.total_parcelas
        }


# tabela de redefinicoes de senha — um registro por pedido de "esqueci minha senha"
# guardamos so o HASH do token (o token em si vai apenas no link do e-mail): se o banco vazar,
# ninguem consegue usar os pedidos pendentes
class RedefinicaoSenha(db.Model):
    __tablename__ = "redefinicoes_senha"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    expira_em = db.Column(db.DateTime, nullable=False)

    # preenchido quando o link e usado (ou quando um pedido mais novo o substitui): uso unico
    usado_em = db.Column(db.DateTime, nullable=True)


# tabela de categorias aceitas por cada conta/cartao — ex.: um Vale Alimentação so paga "Alimentação"
# conta SEM nenhuma linha aqui = aceita qualquer categoria (comportamento padrao)
# conta COM linhas = restrita: so paga essas categorias e e usada primeiro nelas pelo otimizador
class ContaCategoria(db.Model):
    __tablename__ = "contas_categorias"
    __table_args__ = (
        db.UniqueConstraint("conta_id", "categoria", name="uq_conta_categoria"),
    )

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    conta_id = db.Column(db.Integer, db.ForeignKey("nos.id"), nullable=False, index=True)
    categoria = db.Column(db.String(80), nullable=False)


# tabela de compras parceladas registradas A MAO na tela de transacoes ("parcelei em 10x no cartao X com 2,5% de juros")
# guarda os detalhes da compra (juros, valor a vista, total); as parcelas em si ficam em transacoes (as ja
# vencidas) e em arestas (as futuras), ligadas por `grupo`. compras parceladas vindas de extratos nao usam
# esta tabela: elas sao descritas pelas proprias arestas
class Parcelamento(db.Model):
    __tablename__ = "parcelamentos"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    grupo = db.Column(db.String(32), unique=True, nullable=False)     # liga as arestas desta compra (chave_compra = "manual:<grupo>")
    descricao = db.Column(db.String(255), nullable=False)
    valor_vista = db.Column(db.Numeric(12, 2, asdecimal=False), nullable=False)    # preco sem juros
    valor_parcela = db.Column(db.Numeric(12, 2, asdecimal=False), nullable=False)
    valor_total = db.Column(db.Numeric(12, 2, asdecimal=False), nullable=False)    # soma das parcelas (com juros)
    numero_parcelas = db.Column(db.Integer, nullable=False)
    juros_mensal = db.Column(db.Float, default=0.0)                                # % ao mes; 0 = sem juros
    conta = db.Column(db.String(100), nullable=False)                              # nome do cartao/conta
    categoria = db.Column(db.String(80), nullable=False)
    data_inicio = db.Column(db.DateTime, nullable=False)                           # data da primeira parcela
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
