"""
testes da API da tela "Minha conta": perfil, troca de senha, exportar dados e excluir conta
rodar: py -m pytest tests/test_api_conta.py -v   (usa banco SQLite em memoria; veja conftest.py)
"""
import pytest


def cadastrar(c, email="ana@x.com", senha="senha1234", nome="Ana Teste", renda=3000):
    r = c.post("/api/auth/cadastro", json={"nome": nome, "email": email, "senha": senha, "renda_mensal": renda, "lgpd_aceito": True})
    assert r.status_code == 201
    return {"Authorization": "Bearer " + r.get_json()["token"]}


def login(c, email, senha):
    return c.post("/api/auth/login", json={"email": email, "senha": senha}).status_code


# ------------------------------------------------------------------------ perfil
def test_perfil_devolve_os_dados_sem_a_senha(cliente):
    h = cadastrar(cliente)
    dados = cliente.get("/api/auth/perfil", headers=h).get_json()
    assert dados["email"] == "ana@x.com" and dados["renda_mensal"] == 3000 and "senha_hash" not in dados


def test_perfil_exige_login_e_cada_usuario_ve_so_o_proprio(cliente):
    a, b = cadastrar(cliente), cadastrar(cliente, "b@x.com", nome="Outra Pessoa")
    assert cliente.get("/api/auth/perfil").status_code == 401
    assert cliente.get("/api/auth/perfil", headers=b).get_json()["email"] == "b@x.com"
    assert cliente.get("/api/auth/perfil", headers=a).get_json()["email"] == "ana@x.com"


def test_atualizar_nome_e_renda(cliente):
    h = cadastrar(cliente)
    r = cliente.put("/api/auth/perfil", headers=h, json={"nome": "Ana Nova", "renda_mensal": 4500.5})
    assert r.status_code == 200 and r.get_json()["nome"] == "Ana Nova" and r.get_json()["renda_mensal"] == 4500.5
    assert cliente.put("/api/auth/perfil", headers=h, json={"renda_mensal": 0}).get_json()["renda_mensal"] == 0


@pytest.mark.parametrize("corpo", [{"nome": "A"}, {"nome": "x" * 121}, {"renda_mensal": -5}, {"renda_mensal": "muito"}, {"renda_mensal": True}])
def test_perfil_recusa_dados_invalidos(cliente, corpo):
    assert cliente.put("/api/auth/perfil", headers=cadastrar(cliente), json=corpo).status_code == 400


def test_o_email_nao_pode_ser_alterado_pelo_perfil(cliente):
    h = cadastrar(cliente)
    r = cliente.put("/api/auth/perfil", headers=h, json={"nome": "Ana Teste", "email": "hacker@x.com"})
    assert r.get_json()["email"] == "ana@x.com"


# ------------------------------------------------------------------------- senha
def trocar(c, h, atual, nova):
    return c.put("/api/auth/senha", headers=h, json={"senha_atual": atual, "nova_senha": nova})


def test_senha_atual_errada_devolve_403_e_nao_troca(cliente):
    h = cadastrar(cliente)
    r = trocar(cliente, h, "errada123", "novasenha456")
    assert r.status_code == 403 and "incorreta" in r.get_json()["erro"]       # 403 (nao 401): o front nao desloga quem so errou a senha
    assert login(cliente, "ana@x.com", "senha1234") == 200


@pytest.mark.parametrize("corpo,status", [
    ({"senha_atual": "senha1234", "nova_senha": "curta"}, 400), ({"senha_atual": "senha1234", "nova_senha": "x" * 129}, 400),
    ({"senha_atual": "senha1234", "nova_senha": 12345678}, 400), ({"senha_atual": "senha1234", "nova_senha": "senha1234"}, 400),
    ({"senha_atual": 123, "nova_senha": "novasenha456"}, 403), ({"senha_atual": "x" * 500, "nova_senha": "novasenha456"}, 403),
    ({"nova_senha": "novasenha456"}, 403), ({}, 403),
])
def test_senha_recusas(cliente, corpo, status):
    h = cadastrar(cliente)
    assert cliente.put("/api/auth/senha", headers=h, json=corpo).status_code == status
    assert login(cliente, "ana@x.com", "senha1234") == 200


def test_senha_sem_login_ou_com_corpo_invalido(cliente):
    h = cadastrar(cliente)
    assert cliente.put("/api/auth/senha", json={"senha_atual": "senha1234", "nova_senha": "novasenha456"}).status_code == 401
    assert cliente.put("/api/auth/senha", headers=h, data="x", content_type="text/plain").status_code == 400


def test_troca_correta_vale_so_para_a_senha_nova(cliente):
    h = cadastrar(cliente)
    cadastrar(cliente, "b@x.com")
    assert trocar(cliente, h, "senha1234", "novasenha456").status_code == 200
    assert login(cliente, "ana@x.com", "novasenha456") == 200 and login(cliente, "ana@x.com", "senha1234") == 401
    assert trocar(cliente, h, "senha1234", "outra12345").status_code == 403       # a antiga nao serve mais como "senha atual"
    assert login(cliente, "b@x.com", "senha1234") == 200                          # outro usuario nao foi afetado


def test_troca_invalida_links_de_redefinicao_pendentes(cliente):
    from app import app
    from modelos.modelos import RedefinicaoSenha
    h = cadastrar(cliente)
    cliente.post("/api/auth/esqueci-senha", json={"email": "ana@x.com"})
    with app.app_context():
        assert RedefinicaoSenha.query.filter_by(usado_em=None).count() == 1
    trocar(cliente, h, "senha1234", "novasenha456")
    with app.app_context():
        assert RedefinicaoSenha.query.filter_by(usado_em=None).count() == 0


def test_limite_de_tentativas_por_usuario(cliente):
    from extensoes import limiter
    a, b = cadastrar(cliente), cadastrar(cliente, "b@x.com")
    limiter.enabled = True
    limiter.reset()
    codigos = [trocar(cliente, b, "errada", "novasenha789").status_code for _ in range(7)]
    assert codigos[:5] == [403] * 5 and 429 in codigos[5:]                         # freia a forca bruta da senha atual
    assert trocar(cliente, a, "errada", "novasenha789").status_code == 403         # o limite de um usuario nao bloqueia o outro


# ---------------------------------------------------------------- exportar e excluir
def test_exportar_inclui_tudo_do_usuario_e_nada_sensivel(cliente):
    h = cadastrar(cliente)
    cadastrar(cliente, "b@x.com", nome="Outra Pessoa")
    cliente.post("/api/contas", headers=h, json={"nome": "Vale Refeição", "capacidade": 600, "categorias": ["Restaurante"]})
    cliente.post("/api/parcelamentos", headers=h, json={"descricao": "Notebook", "valor_vista": 1000, "parcelas": 5, "juros_mensal": 2, "conta": "Cartão X"})
    cliente.post("/api/transacoes", headers=h, json={"descricao": "mercado", "valor": -50})
    d = cliente.get("/api/auth/meus-dados", headers=h).get_json()

    assert {"usuario", "transacoes", "metas", "alertas", "contas", "compras_parceladas", "parcelas_futuras"} <= set(d)
    vale = next(x for x in d["contas"] if x["nome"] == "Vale Refeição")
    assert vale["categorias_aceitas"] == ["Restaurante"] and vale["capacidade"] == 600
    assert d["compras_parceladas"][0]["juros_mensal"] == 2.0 and d["compras_parceladas"][0]["numero_parcelas"] == 5
    assert len(d["parcelas_futuras"]) == 4
    texto = str(d)
    assert "senha_hash" not in texto and "Outra Pessoa" not in texto


def test_excluir_conta_exige_a_senha(cliente):
    h = cadastrar(cliente)
    assert cliente.delete("/api/auth/conta", headers=h, json={"senha": "errada"}).status_code == 403
    assert login(cliente, "ana@x.com", "senha1234") == 200


def test_excluir_conta_apaga_tudo_do_usuario(cliente):
    from app import app
    from modelos.modelos import Aresta, ContaCategoria, No, Parcelamento, Transacao
    h = cadastrar(cliente)
    cliente.post("/api/contas", headers=h, json={"nome": "Vale", "categorias": ["Alimentação"]})
    cliente.post("/api/parcelamentos", headers=h, json={"descricao": "TV", "valor_vista": 600, "parcelas": 3})
    cliente.post("/api/transacoes", headers=h, json={"descricao": "mercado", "valor": -50})
    assert cliente.delete("/api/auth/conta", headers=h, json={"senha": "senha1234"}).status_code == 200
    assert login(cliente, "ana@x.com", "senha1234") == 401
    with app.app_context():
        assert all(m.query.count() == 0 for m in (Transacao, No, Aresta, ContaCategoria, Parcelamento))
