"""
migracoes simples do banco

o db.create_all() so cria tabelas que NAO existem: ele nao acrescenta colunas novas em tabelas antigas.
quando o sistema ganha uma coluna, ela e criada aqui, sozinha, na proxima vez que o servidor sobe
(sem apagar nada e sem voce rodar SQL). cada migracao so age se a coluna ainda nao existir
"""
import logging

from sqlalchemy import inspect, text

log = logging.getLogger(__name__)


def _colunas(engine, tabela):
    insp = inspect(engine)
    return {c["name"] for c in insp.get_columns(tabela)} if tabela in insp.get_table_names() else None


def _ligar_compras_parceladas_antigas(engine):
    """
    compras parceladas lancadas antes da coluna existir ja sabiam o cartao (nas compras manuais e nas parcelas futuras
    vindas de extrato): liga a parcela ja lancada a esse cartao. so mexe em despesas que ainda estao sem conta
    """
    tabelas = set(inspect(engine).get_table_names())
    ligacoes = []   # (usuario_id, descricao da transacao, conta_id)
    with engine.connect() as con:
        if {"parcelamentos", "nos"} <= tabelas:
            contas = {(u, nome): i for i, u, nome in con.execute(text("SELECT id, usuario_id, nome FROM nos WHERE tipo = 'conta'"))}
            for u, descricao, n, conta in con.execute(text("SELECT usuario_id, descricao, numero_parcelas, conta FROM parcelamentos")):
                if (u, conta) in contas:
                    ligacoes += [(u, f"{descricao} ({k}/{n})", contas[(u, conta)]) for k in range(1, n + 1)]
        if "arestas" in tabelas:
            for u, descricao, origem in con.execute(text("SELECT DISTINCT usuario_id, descricao, origem_id FROM arestas WHERE projetada = :p"), {"p": True}):
                if descricao:
                    ligacoes.append((u, descricao, origem))
    atualizados = 0
    if ligacoes:
        with engine.begin() as con:
            for u, descricao, conta_id in ligacoes:
                resultado = con.execute(text("UPDATE transacoes SET conta_id = :c WHERE usuario_id = :u AND descricao = :d AND conta_id IS NULL AND valor < 0"),
                                        {"c": conta_id, "u": u, "d": descricao})
                atualizados += max(resultado.rowcount, 0)
    return atualizados             # quantos lancamentos realmente foram ligados


def aplicar_migracoes(db):
    """devolve a lista do que foi criado (vazia quando o banco ja esta em dia)"""
    engine, aplicadas = db.engine, []

    # transacoes.conta_id: em qual conta ou cartao a compra foi paga
    colunas = _colunas(engine, "transacoes")
    if colunas is not None and "conta_id" not in colunas:
        sqlite = engine.dialect.name == "sqlite"
        passos = (
            ["ALTER TABLE transacoes ADD COLUMN conta_id INTEGER REFERENCES nos(id) ON DELETE SET NULL",
             "CREATE INDEX IF NOT EXISTS ix_transacoes_conta_id ON transacoes (conta_id)"]
            if sqlite else
            ["ALTER TABLE transacoes ADD COLUMN conta_id INT NULL",
             "CREATE INDEX ix_transacoes_conta_id ON transacoes (conta_id)"]
        )
        try:
            with engine.begin() as con:
                for sql in passos:
                    con.execute(text(sql))
        except Exception as erro:
            raise RuntimeError(
                "Nao consegui atualizar o banco automaticamente. Rode isto no MySQL e suba o servidor de novo:\n"
                "  ALTER TABLE transacoes ADD COLUMN conta_id INT NULL;\n"
                "  CREATE INDEX ix_transacoes_conta_id ON transacoes (conta_id);\n"
                f"(erro original: {erro})"
            ) from erro
        if not sqlite:
            try:    # a chave estrangeira e um reforco: se falhar, o sistema segue (ele ja limpa conta_id ao excluir uma conta)
                with engine.begin() as con:
                    con.execute(text("ALTER TABLE transacoes ADD CONSTRAINT fk_transacoes_conta "
                                     "FOREIGN KEY (conta_id) REFERENCES nos(id) ON DELETE SET NULL"))
            except Exception as erro:
                log.warning("coluna transacoes.conta_id criada sem chave estrangeira: %s", erro)
        aplicadas.append("transacoes.conta_id")
        ligadas = _ligar_compras_parceladas_antigas(engine)
        if ligadas:
            aplicadas.append(f"{ligadas} lançamento(s) de compras parceladas antigas ligado(s) ao cartão em que foram cadastrados")

    return aplicadas
