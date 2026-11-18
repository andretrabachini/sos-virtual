from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from extensoes import limiter, usuario_id_atual
from servicos.assistente import responder
from validacao import corpo_json, erro, texto

chat_bp = Blueprint("chat", __name__, url_prefix="/api/chat")

MAX_MENSAGEM = 500       # caracteres por mensagem
MAX_HISTORICO = 20       # mensagens anteriores consideradas
MAX_TEXTO_HISTORICO = 2000


def _historico(valor):
    """mensagens anteriores validadas; o que vier fora do formato e ignorado (o historico so ajuda a completar perguntas curtas)"""
    if not isinstance(valor, list):
        return []
    itens = []
    for item in valor[-MAX_HISTORICO:]:
        if isinstance(item, dict) and item.get("role") in ("user", "assistant") and isinstance(item.get("content"), str):
            itens.append({"role": item["role"], "content": item["content"][:MAX_TEXTO_HISTORICO]})
    return itens


@chat_bp.route("", methods=["POST"])
@jwt_required()
@limiter.limit("30 per minute; 600 per hour")
def conversar():
    """
    {"mensagem": "gastei R$ 50 no mercado", "historico": [{"role": "user", "content": "..."}]}
    -> {"resposta": texto, "intencao": nome, "lancamento": {...} | null, "alertas": [...]}
    """
    dados = corpo_json()
    if dados is None:
        return erro("corpo da requisição inválido")
    mensagem = texto(dados.get("mensagem"), 1, MAX_MENSAGEM)
    if mensagem is None:
        return erro(f"escreva uma mensagem de até {MAX_MENSAGEM} caracteres")
    return jsonify(responder(usuario_id_atual(), mensagem, _historico(dados.get("historico"))))
