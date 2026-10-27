// Desenha o grafo "contas → despesas" em SVG puro (sem bibliotecas externas).
// Usa as funções esc() e brl() do app.js. `dados` é a resposta de /api/grafo ou /api/grafo/otimizar
// (campos nos e arestas). A espessura de cada ligação mostra quanto dinheiro passa por ela;
// a cor mostra o benefício da conta: verde = cashback, azul = neutro, vermelho = juros/taxa.
(function () {
  const COR = { pos: '#12805C', neutro: '#1C4A7A', neg: '#D2415A', tinta: '#0E2A47', suave: '#52667E', linha: '#DDE5ED', ouro: '#E8A317' };
  const cortar = (s, n) => (s.length > n ? s.slice(0, n - 1) + '…' : s);
  const corDaConta = c => (c.custo < 0 ? COR.pos : c.custo > 0 ? COR.neg : COR.neutro);
  const pct = v => Math.abs(v).toLocaleString('pt-BR', { maximumFractionDigits: 2 }) + '%';

  function legenda(temRestrita, temFalta) {
    const item = (estilo, texto) =>
      '<span style="display:inline-flex;align-items:center;gap:.4rem;margin-right:1rem"><i style="width:.8rem;height:.8rem;border-radius:3px;display:inline-block;' +
      estilo + '"></i>' + texto + '</span>';
    return '<div class="rot" style="margin-top:.6rem">' + item('background:' + COR.pos, 'conta com cashback') + item('background:' + COR.neutro, 'conta sem benefício') +
      item('background:' + COR.neg, 'conta com juros/taxa') +
      (temRestrita ? item('background:' + COR.tinta + ';border:2px dashed ' + COR.ouro, 'conta restrita (vale)') : '') +
      (temFalta ? item('background:#fff;border:2px solid ' + COR.neg, 'despesa sem conta suficiente') : '') +
      '<span>· quanto mais grossa a linha, mais dinheiro passa por ela</span></div>';
  }

  window.desenharGrafo = function (alvo, dados) {
    const contas = dados.nos.filter(n => n.tipo === 'conta');
    const cats = dados.nos.filter(n => n.tipo === 'categoria');
    const porId = Object.fromEntries(dados.nos.map(n => [n.id, n]));

    const L = 600, X_CONTA = 8, X_CAT = 424, LARG = 168, ALT = 42, PASSO = 52, MARGEM = 10;
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
      const so = c.restrita && c.categorias && c.categorias.length ? ' — só paga: ' + c.categorias.join(', ') : '';
      return '<g><title>' + esc(c.nome) + ' — ' + esc(info) + esc(so) + ' — ' + esc(sub) + '</title>' +
        '<rect x="' + X_CONTA + '" y="' + y + '" width="' + LARG + '" height="' + ALT + '" rx="10" fill="' + COR.tinta + '" opacity="' + (c.usado > 0 ? 1 : 0.55) + '"' +
        (c.restrita ? ' stroke="' + COR.ouro + '" stroke-width="2" stroke-dasharray="5 3"' : '') + '/>' +
        '<rect x="' + X_CONTA + '" y="' + y + '" width="6" height="' + ALT + '" rx="3" fill="' + corDaConta(c) + '"/>' +
        '<text x="' + (X_CONTA + 16) + '" y="' + (y + 19) + '" fill="#fff" font-size="13" font-weight="600">' + esc(cortar(c.nome, 18)) + '</text>' +
        '<text x="' + (X_CONTA + 16) + '" y="' + (y + 35) + '" fill="#B9C8DA" font-size="11">' + esc(sub) + '</text></g>';
    }).join('');

    const nosCat = cats.map(c => {
      const y = yCat[c.id] - ALT / 2;
      const falta = c.faltam > 0;
      return '<g><title>' + esc(c.nome) + ': ' + brl(c.valor) + (falta ? ' — faltam ' + brl(c.faltam) + ' (nenhuma conta cobre)' : '') + '</title>' +
        '<rect x="' + X_CAT + '" y="' + y + '" width="' + LARG + '" height="' + ALT + '" rx="23" fill="#fff" stroke="' + (falta ? COR.neg : COR.linha) + '" stroke-width="2"/>' +
        '<text x="' + (X_CAT + LARG / 2) + '" y="' + (y + 20) + '" text-anchor="middle" fill="' + COR.tinta + '" font-size="13" font-weight="600">' + esc(cortar(c.nome, 18)) + '</text>' +
        '<text x="' + (X_CAT + LARG / 2) + '" y="' + (y + 36) + '" text-anchor="middle" fill="' + (falta ? COR.neg : COR.suave) + '" font-size="11">' + esc(falta ? 'faltam ' + brl(c.faltam) : brl(c.valor)) + '</text></g>';
    }).join('');

    const resumo = 'Mapa de pagamentos: ' + contas.length + ' conta(s) pagando ' + cats.length + ' despesa(s). Os detalhes estão na tabela.';
    alvo.innerHTML = '<svg viewBox="0 0 ' + L + ' ' + H + '" role="img" aria-label="' + esc(resumo) +
      '" style="display:block;width:100%;height:auto;max-height:56vh;margin:0 auto" font-family="Figtree,system-ui,sans-serif">' + ligacoes + nosConta + nosCat + '</svg>' + legenda(contas.some(c => c.restrita), cats.some(c => c.faltam > 0));
  };
})();
