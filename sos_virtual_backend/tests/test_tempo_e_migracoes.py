"""
testes do horario do sistema (servicos/tempo.py) e da migracao automatica de colunas (servicos/migracoes.py)
rodar: py -m pytest tests/test_tempo_e_migracoes.py -v
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

from servicos import tempo
from servicos.migracoes import aplicar_migracoes


# ------------------------------------------------------------------------------ tempo
def fingir_agora(monkeypatch, instante_utc):
    class Falso(datetime):
        @classmethod
        def now(cls, tz=None):
            return instante_utc.astimezone(tz)
    monkeypatch.setattr(tempo, "datetime", Falso)


def test_compra_as_22h30_do_dia_31_continua_no_mes_certo(monkeypatch):
    """01h30 UTC de 1/11 ainda e 22h30 de 31/10 em Brasilia: a compra e de outubro"""
    fingir_agora(monkeypatch, datetime(2026, 11, 1, 1, 30, tzinfo=timezone.utc))
    assert tempo.agora() == datetime(2026, 10, 31, 22, 30)
    assert tempo.mes_atual() == "2026-10"
    assert tempo.hoje() == datetime(2026, 10, 31)


def test_virada_de_ano(monkeypatch):
    fingir_agora(monkeypatch, datetime(2027, 1, 1, 2, 10, tzinfo=timezone.utc))
    assert tempo.mes_atual() == "2026-12" and tempo.hoje() == datetime(2026, 12, 31)


def test_depois_das_3h_utc_ja_e_o_dia_novo(monkeypatch):
    fingir_agora(monkeypatch, datetime(2026, 11, 1, 3, 0, tzinfo=timezone.utc))
    assert tempo.mes_atual() == "2026-11"


def test_agora_e_sem_fuso_e_tres_horas_atras_do_utc():
    a = tempo.agora()
    assert a.tzinfo is None
    assert abs((datetime.utcnow() - a) - timedelta(hours=3)) < timedelta(seconds=5)


# ------------------------------------------------------------------------- migracoes
class BancoFalso:
    def __init__(self, engine):
        self.engine = engine


@pytest.fixture()
def banco_antigo(tmp_path):
    """banco como era antes da coluna conta_id, ja com dados do usuario"""
    engine = create_engine(f"sqlite:///{tmp_path / 'antigo.db'}")
    with engine.begin() as con:
        con.execute(text("CREATE TABLE usuarios (id INTEGER PRIMARY KEY, nome VARCHAR(120))"))
        con.execute(text("CREATE TABLE nos (id INTEGER PRIMARY KEY, usuario_id INTEGER, nome VARCHAR(100), tipo VARCHAR(50))"))
        con.execute(text("CREATE TABLE transacoes (id INTEGER PRIMARY KEY, usuario_id INTEGER NOT NULL, descricao VARCHAR(255) NOT NULL, "
                         "valor FLOAT NOT NULL, categoria VARCHAR(80), data DATETIME)"))
        con.execute(text("INSERT INTO usuarios VALUES (1, 'Ana')"))
        con.execute(text("INSERT INTO nos VALUES (1, 1, 'Cartão Itaú', 'conta')"))
        con.execute(text("INSERT INTO transacoes VALUES (1, 1, 'mercado', -50.0, 'Alimentação', '2026-10-05 10:00:00')"))
    yield BancoFalso(engine)
    engine.dispose()


def colunas(banco):
    with banco.engine.connect() as con:
        return [linha[1] for linha in con.execute(text("PRAGMA table_info(transacoes)"))]


def test_migracao_acrescenta_a_coluna_sem_perder_dados(banco_antigo):
    assert "conta_id" not in colunas(banco_antigo)
    assert aplicar_migracoes(banco_antigo) == ["transacoes.conta_id"]
    assert "conta_id" in colunas(banco_antigo)
    with banco_antigo.engine.connect() as con:
        linha = con.execute(text("SELECT descricao, valor, categoria, conta_id FROM transacoes")).fetchone()
    assert tuple(linha) == ("mercado", -50.0, "Alimentação", None)       # o lancamento antigo continua la, sem conta


def test_migracao_so_age_uma_vez(banco_antigo):
    aplicar_migracoes(banco_antigo)
    assert aplicar_migracoes(banco_antigo) == []


def test_coluna_nova_aceita_conta_e_zera_ao_excluir_a_conta(banco_antigo):
    aplicar_migracoes(banco_antigo)
    with banco_antigo.engine.begin() as con:
        con.execute(text("PRAGMA foreign_keys=ON"))
        con.execute(text("UPDATE transacoes SET conta_id = 1 WHERE id = 1"))
        assert con.execute(text("SELECT conta_id FROM transacoes")).scalar() == 1
        con.execute(text("DELETE FROM nos WHERE id = 1"))
        assert con.execute(text("SELECT conta_id FROM transacoes")).scalar() is None      # ON DELETE SET NULL


def test_banco_sem_a_tabela_nao_da_erro(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'vazio.db'}")
    assert aplicar_migracoes(BancoFalso(engine)) == []
    engine.dispose()


# ------------------------------------- compras parceladas antigas ganham o cartao automaticamente
@pytest.fixture()
def banco_com_parcelas(banco_antigo):
    with banco_antigo.engine.begin() as con:
        con.execute(text("CREATE TABLE parcelamentos (id INTEGER PRIMARY KEY, usuario_id INTEGER, descricao VARCHAR(255), numero_parcelas INTEGER, conta VARCHAR(100))"))
        con.execute(text("CREATE TABLE arestas (id INTEGER PRIMARY KEY, usuario_id INTEGER, origem_id INTEGER, descricao VARCHAR(255), projetada BOOLEAN)"))
        con.execute(text("INSERT INTO nos VALUES (2, 1, 'Cartão Meli', 'conta')"))
        con.execute(text("INSERT INTO parcelamentos VALUES (1, 1, 'Strap Academia', 2, 'Cartão Meli')"))               # compra cadastrada a mao
        con.execute(text("INSERT INTO transacoes VALUES (2, 1, 'Strap Academia (1/2)', -25.0, 'Saúde', '2026-10-29 10:00:00')"))
        con.execute(text("INSERT INTO arestas VALUES (1, 1, 1, 'TV 55 PARC 02/06', 1)"))                                 # vinda de extrato (Cartão Itaú)
        con.execute(text("INSERT INTO transacoes VALUES (3, 1, 'TV 55 PARC 02/06', -349.9, 'Outros', '2026-10-10 00:00:00')"))
        con.execute(text("INSERT INTO transacoes VALUES (4, 1, 'Strap Academia (1/2)', 50.0, 'Outros', '2026-10-30 00:00:00')"))   # receita de mesmo nome: nao mexe
    return banco_antigo


def conta_das_transacoes(banco):
    with banco.engine.connect() as con:
        return {linha[0]: linha[1] for linha in con.execute(text("SELECT id, conta_id FROM transacoes"))}


def test_migracao_liga_as_compras_parceladas_antigas_ao_cartao(banco_com_parcelas):
    resultado = aplicar_migracoes(banco_com_parcelas)
    assert resultado[0] == "transacoes.conta_id" and "2 lançamento(s) de compras parceladas antigas" in resultado[1]
    contas = conta_das_transacoes(banco_com_parcelas)
    assert contas[2] == 2          # Strap Academia (1/2) -> Cartão Meli (cadastro manual)
    assert contas[3] == 1          # TV 55 -> Cartão Itaú (veio do extrato dessa conta)
    assert contas[1] is None       # "mercado" sem informacao: continua sem conta
    assert contas[4] is None       # receita nao e tocada


def test_migracao_nao_repete_o_preenchimento(banco_com_parcelas):
    aplicar_migracoes(banco_com_parcelas)
    with banco_com_parcelas.engine.begin() as con:
        con.execute(text("UPDATE transacoes SET conta_id = NULL WHERE id = 2"))     # o usuario "tirou" a conta depois
    assert aplicar_migracoes(banco_com_parcelas) == []
    assert conta_das_transacoes(banco_com_parcelas)[2] is None                      # e a migracao nao desfaz a escolha dele
