from flask_jwt_extended import get_jwt_identity
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# limitador de requisicoes por IP (protege login e cadastro contra forca bruta)
# fica aqui, separado do app.py, para as rotas poderem importar sem import circular
# storage em memoria serve para desenvolvimento; em producao use redis
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["300 per hour"],
    storage_uri="memory://",
)


def usuario_id_atual() -> int:
    """
    o token guarda o id como texto (exigencia das versoes novas do JWT),
    entao convertemos de volta para inteiro antes de usar nas consultas
    """
    return int(get_jwt_identity())
