from datetime import datetime

from flask import request, jsonify

# teto para qualquer valor em R$ (evita numeros absurdos que estouram o banco ou os calculos)
VALOR_MAX = 1_000_000_000


def erro(mensagem, status=400):
    return jsonify({"erro": mensagem}), status


def corpo_json():
    # get_json(silent=True) nao estoura erro se o corpo vier quebrado ou vazio
    dados = request.get_json(silent=True)
    return dados if isinstance(dados, dict) else None


def texto(valor, minimo=1, maximo=255):
    """devolve o texto sem espacos nas pontas, ou None se nao for texto valido"""
    if not isinstance(valor, str):
        return None
    valor = valor.strip()
    return valor if minimo <= len(valor) <= maximo else None


def numero(valor, minimo, maximo):
    """
    devolve o numero arredondado em 2 casas, ou None se for invalido
    rejeita texto, listas, True/False, NaN e infinito
    """
    # bool e subclasse de int em Python, por isso rejeitamos explicitamente
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    # valor != valor detecta NaN
    if valor != valor or valor < minimo or valor > maximo:
        return None
    return round(float(valor), 2)


def data_iso(valor):
    """converte 'AAAA-MM-DD' (ou ISO completo) em datetime, ou None se for invalido"""
    if not isinstance(valor, str) or len(valor) > 32:
        return None
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        return None
