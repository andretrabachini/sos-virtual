// Desenha o grafo "contas → despesas" em SVG puro (sem bibliotecas externas).
// Usa as funções esc() e brl() do app.js. `dados` é a resposta de /api/grafo ou /api/grafo/otimizar
// (campos nos e arestas). A espessura de cada ligação mostra quanto dinheiro passa por ela;
// a cor mostra o benefício da conta: verde = cashback, azul = neutro, vermelho = juros/taxa.
(function () {
  const COR = { pos: '#12805C', neutro: '#1C4A7A', neg: '#D2415A', tinta: '#0E2A47', suave: '#52667E', linha: '#DDE5ED' };
  const cortar = (s, n) => (s.length > n ? s.slice(0, n - 1) + '…' : s);
  const corDaConta = c => (c.custo < 0 ? COR.pos : c.custo > 0 ? COR.neg : COR.neutro);
  const pct = v => Math.abs(v).toLocaleString('pt-BR', { maximumFractionDigits: 2 }) + '%';

  function legenda() {
    const item = (cor, texto) =>
      '<span style="display:inline-flex;align-items:center;gap:.4rem;margin-right:1rem"><i style="width:.8rem;height:.8rem;border-radius:3px;background:' +
      cor + ';display:inline-block"></i>' + texto + '</span>';
    return '<div class="rot" style="margin-top:.6rem">' + item(COR.pos, 'conta com cashback') + item(COR.neutro, 'conta sem benefício') +
      item(COR.neg, 'conta com juros/taxa') + '<span>· quanto mais grossa a linha, mais dinheiro passa por ela</span></div>';
  }

  window.desenharGrafo = function (alvo, dados) {
    const contas = dados.nos.filter(n => n.tipo === 'conta');
    const cats = dados.nos.filter(n => n.tipo === 'categoria');
    const porId = Object.fromEntries(dados.nos.map(n => [n.id, n]));

    const L = 600, X_CONTA = 10, X_CAT = 440, LARG = 150, ALT = 46, PASSO = 66, MARGEM = 14;
    const linhas = Math.max(contas.length, cats.length, 1);
    const H = MARGEM * 2 + linhas * PASSO;
    // cada coluna ocupa a altura toda, com os itens bem distribuídos
    const posY = (i, n) => MARGEM + ((H - MARGEM * 2) * (i + 0.5)) / n;
    const yConta = {}, yCat = {};
    contas.forEach((c, i) => { yConta[c.id] = posY(i, contas.length); });
    cats.forEach((c, i) => { yCat[c.id] = posY(i, cats.length); });

    const maior = Math.max(...dados.arestas.map(a => a.valor), 1);
    const xa = X_CONTA + LARG, xb = X_CAT, xm = (xa + xb) / 2;

    const ligacoes = dados.arestas.map(a => {
      const conta = porId[a.origem], cat = porId[a.destino];
      const largura = (2 + (12 * a.valor) / maior).toFixed(1);
      return '<path d="M' + xa + ' ' + yConta[a.origem] + ' C' + xm + ' ' + yConta[a.origem] + ',' + xm + ' ' + yCat[a.destino] + ',' + xb + ' ' + yCat[a.destino] +
        '" fill="none" stroke="' + corDaConta(conta) + '" stroke-opacity=".5" stroke-width="' + largura + '" stroke-linecap="round">' +
        '<title>' + esc(conta.nome) + ' → ' + esc(cat.nome) + ': ' + brl(a.valor) + '</title></path>';
    }).join('');

    const nosConta = contas.map(c => {
      const y = yConta[c.id] - ALT / 2;
      const sub = c.usado > 0
        ? 'paga ' + brl(c.usado)
        : 'não usada';
      const info = c.custo < 0 ? 'cashback ' + pct(c.custo) : c.custo > 0 ? 'juros/taxa ' + pct(c.custo) : 'sem benefício';
      return '<g><title>' + esc(c.nome) + ' — ' + esc(info) + ' — ' + esc(sub) + '</title>' +
        '<rect x="' + X_CONTA + '" y="' + y + '" width="' + LARG + '" height="' + ALT + '" rx="10" fill="' + COR.tinta + '" opacity="' + (c.usado > 0 ? 1 : 0.55) + '"/>' +
        '<rect x="' + X_CONTA + '" y="' + y + '" width="6" height="' + ALT + '" rx="3" fill="' + corDaConta(c) + '"/>' +
        '<text x="' + (X_CONTA + 16) + '" y="' + (y + 19) + '" fill="#fff" font-size="13" font-weight="600">' + esc(cortar(c.nome, 15)) + '</text>' +
        '<text x="' + (X_CONTA + 16) + '" y="' + (y + 35) + '" fill="#B9C8DA" font-size="11">' + esc(sub) + '</text></g>';
    }).join('');

    const nosCat = cats.map(c => {
      const y = yCat[c.id] - ALT / 2;
      return '<g><title>' + esc(c.nome) + ': ' + brl(c.valor) + '</title>' +
        '<rect x="' + X_CAT + '" y="' + y + '" width="' + LARG + '" height="' + ALT + '" rx="23" fill="#fff" stroke="' + COR.linha + '" stroke-width="2"/>' +
        '<text x="' + (X_CAT + LARG / 2) + '" y="' + (y + 20) + '" text-anchor="middle" fill="' + COR.tinta + '" font-size="13" font-weight="600">' + esc(cortar(c.nome, 16)) + '</text>' +
        '<text x="' + (X_CAT + LARG / 2) + '" y="' + (y + 36) + '" text-anchor="middle" fill="' + COR.suave + '" font-size="11">' + esc(brl(c.valor)) + '</text></g>';
    }).join('');

    const resumo = 'Mapa de pagamentos: ' + contas.length + ' conta(s) pagando ' + cats.length + ' despesa(s). Os detalhes estão na tabela.';
    alvo.innerHTML = '<svg viewBox="0 0 ' + L + ' ' + H + '" role="img" aria-label="' + esc(resumo) +
      '" style="width:100%;height:auto;display:block" font-family="Figtree,system-ui,sans-serif">' + ligacoes + nosConta + nosCat + '</svg>' + legenda();
  };
})();
