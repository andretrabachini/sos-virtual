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

    # relacionamentos: um usuario tem varias transacoes e metas
    transacoes = db.relationship("Transacao", backref="usuario", lazy=True)
    metas = db.relationship("Meta", backref="usuario", lazy=True)

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