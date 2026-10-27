"""
verificacao de alertas no momento em que um gasto e registrado

uso (em qualquer rota que cria ou altera despesas):
    antes = fotografar_alertas(usuario_id)        # ANTES de gravar
    ... grava e faz commit ...
    avisos = alertas_ultrapassados(usuario_id, antes)   # lista para o front mostrar em pop-up

um aviso sai para cada alerta ATIVO cuja categoria recebeu gasto nesta operacao e ficou no limite ou acima:
    cruzou = True   -> passou do limite agora (estava abaixo)
    cruzou = False  -> a categoria ja estava acima do limite e continuou crescendo
"""
from modelos.modelos import Alerta
from servicos.financeiro import gastos_por_categoria


def fotografar_alertas(usuario_id):
    """devolve None quando nao ha alertas ativos (assim nao gastamos consulta a toa)"""
    alertas = [(a.categoria, float(a.limite)) for a in Alerta.query.filter_by(usuario_id=usuario_id, ativo=True).all()]
    if not alertas:
        return None
    return {"alertas": alertas, "gastos": gastos_por_categoria(usuario_id)}


def alertas_ultrapassados(usuario_id, antes):
    if antes is None:
        return []
    depois = gastos_por_categoria(usuario_id)
    avisos = []
    for categoria, limite in antes["alertas"]:
        gasto_antes = antes["gastos"].get(categoria, 0.0)
        gasto_agora = depois.get(categoria, 0.0)
        if gasto_agora > gasto_antes and gasto_agora >= limite:
            avisos.append({
                "categoria": categoria,
                "limite": limite,
                "gasto": gasto_agora,
                "excesso": round(gasto_agora - limite, 2),
                "cruzou": gasto_antes < limite,
            })
    return avisos
