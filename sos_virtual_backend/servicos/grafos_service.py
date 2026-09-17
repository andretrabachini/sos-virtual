import networkx as nx

def calcular_roteamento_otimizado(orcamento_total, contas, despesas, transacoes):
    """
    Constrói a rede de fluxo financeiro e retorna a melhor estratégia de pagamento.
    
    :param orcamento_total: Float com o total de despesas do mês.
    :param contas: Lista de dicionários vindos da tabela 'nos' (tipo 'conta').
    :param despesas: Lista de dicionários vindos da tabela 'nos' (tipo 'categoria').
    :param transacoes: Lista de dicionários vindos da tabela 'arestas'.
    """
    # 1. Inicializa o Grafo Direcionado
    G = nx.DiGraph()

    # 2. Injeta os Nós Virtuais (Super Fonte S e Super Sumidouro T)
    G.add_node('S', demand=-orcamento_total)  # Injeta o dinheiro
    G.add_node('T', demand=orcamento_total)   # Consome o dinheiro

    # 3. Camada 1: Conecta a Fonte (S) aos Ativos (Contas/Cartões)
    for conta in contas:
        # Exemplo de 'conta': {'id': 'Conta Corrente', 'capacidade': 5000, 'custo': 0}
        G.add_edge('S', conta['id'], capacity=conta['capacidade'], weight=conta['custo'])

    # 4. Camada 2: O Miolo (Transações reais entre Contas e Despesas)
    for t in transacoes:
        # Exemplo de 't': {'origem': 'Conta Corrente', 'destino': 'Aluguel', 'limite': 2000}
        # O peso aqui é 0 porque o benefício (cashback/juros) já foi cobrado na Camada 1
        G.add_edge(t['origem'], t['destino'], capacity=t['limite'], weight=0)

    # 5. Camada 3: Conecta as Demandas (Despesas) ao Sumidouro (T)
    for despesa in despesas:
        # Exemplo de 'despesa': {'id': 'Aluguel', 'valor_fatura': 2000}
        G.add_edge(despesa['id'], 'T', capacity=despesa['valor_fatura'], weight=0)

    # 6. Roda o Algoritmo de Custo Mínimo e Fluxo Máximo
    try:
        custo_fluxo, dicionario_fluxo = nx.capacity_scaling(G)
        
        # Formata a resposta para o Front-End (JSON)
        return {
            "status": "sucesso",
            "retorno_financeiro": abs(custo_fluxo), # Mostra o quanto o usuário economizou
            "estrategia_pagamento": dicionario_fluxo['S'] # Mostra quanto tirar de cada conta
        }
    except nx.NetworkXUnfeasible:
        return {
            "status": "erro",
            "mensagem": "Gargalo detectado! O limite das contas não cobre as despesas."
        }