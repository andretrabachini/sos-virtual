// Janela "Minha conta" (seções à esquerda, conteúdo à direita), aberta pelo perfil do menu lateral.
// Carregada sob demanda pelo app.js. Usa as funções globais de lá: api, esc, usuarioAtual, msgErro,
// atualizarNomeNoMenu, inicialDe, sair.
(function () {
  const icone = caminhos => '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + caminhos + '</svg>';
  const SECOES = [
    ['perfil', 'Perfil', icone('<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/>')],
    ['seguranca', 'Segurança', icone('<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>')],
    ['preferencias', 'Preferências', icone('<line x1="4" y1="7" x2="20" y2="7"/><circle cx="9" cy="7" r="2" fill="#fff"/><line x1="4" y1="17" x2="20" y2="17"/><circle cx="15" cy="17" r="2" fill="#fff"/>')],
    ['privacidade', 'Privacidade e dados', icone('<path d="M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6z"/>')],
  ];
  const FOCAVEIS = 'a[href],button:not([disabled]),input:not([disabled]):not([type=hidden]),select,textarea,[tabindex]:not([tabindex="-1"])';
  const PREF_POPUP = 'sosv_pref_alertas_popup';

  let fundo = null, voltarPara = null, secaoAtual = 'perfil';

  function estilo() {
    if (document.getElementById('estilo-conta')) return;
    const st = document.createElement('style');
    st.id = 'estilo-conta';
    st.textContent = `
      .conta-fundo{position:fixed;inset:0;z-index:1100;display:grid;place-items:center;padding:1rem;background:rgba(14,42,71,.55)}
      .conta-caixa{display:grid;grid-template-rows:auto minmax(0,1fr);width:min(920px,100%);height:min(640px,92vh);border-radius:14px;background:#fff;box-shadow:0 20px 60px rgba(14,42,71,.35);overflow:hidden}
      .conta-topo{display:flex;align-items:center;justify-content:space-between;padding:1rem 1.4rem;border-bottom:1px solid var(--line,#DDE5ED)}
      .conta-topo h2{font-size:1.2rem}
      .conta-x{display:grid;place-items:center;width:2.2rem;height:2.2rem;border:0;border-radius:8px;background:none;color:var(--ink2,#52667E);font-size:1.5rem;line-height:1;cursor:pointer}
      .conta-x:hover{background:var(--bg,#F2F5F8);color:var(--ink,#0E2A47)}
      .conta-corpo{display:grid;grid-template-columns:15rem minmax(0,1fr);min-height:0}
      .conta-nav{display:flex;flex-direction:column;gap:.2rem;padding:1rem;border-right:1px solid var(--line,#DDE5ED);background:var(--bg,#F2F5F8);overflow-y:auto}
      .conta-nav button{display:flex;align-items:center;gap:.7rem;padding:.65rem .8rem;border:0;border-radius:var(--r,10px);background:none;color:var(--ink2,#52667E);font:500 .95rem var(--fb,sans-serif);text-align:left;cursor:pointer}
      .conta-nav button:hover{background:rgba(14,42,71,.06);color:var(--ink,#0E2A47)}
      .conta-nav button[aria-selected=true]{background:#fff;color:var(--ink,#0E2A47);font-weight:700;box-shadow:0 1px 3px rgba(14,42,71,.12)}
      .conta-painel{padding:1.5rem 1.8rem;overflow-y:auto}
      .conta-painel:focus{outline:none}
      .conta-painel h3{font-size:1.1rem;margin-bottom:.4rem}
      .conta-painel>.rot,.conta-painel form{max-width:34rem}
      .conta-id{display:flex;align-items:center;gap:1rem;margin:1rem 0 1.4rem}
      .conta-linha{display:flex;align-items:center;justify-content:space-between;gap:1.5rem;padding:1rem 0;border-top:1px solid var(--line,#DDE5ED)}
      .conta-linha>div:first-child{max-width:30rem}
      .conta-botoes{display:flex;flex-wrap:wrap;gap:.6rem;margin-top:.8rem}
      .conta-perigo{margin-top:1.6rem;padding:1.1rem 1.2rem;border:1px solid #F2B8C2;border-radius:var(--r,10px);background:#FFF8F9}
      .conta-perigo>b{color:var(--neg,#D2415A)}
      .conta-caixa .aviso{margin:.2rem 0 1rem}
      .conta-caixa .aviso.ok{background:#E8F6F0;border-color:#9ED8C0;color:#0B5A41}
      .cf-switch{position:relative;flex:none;display:inline-block;width:2.9rem;height:1.6rem}
      .cf-switch input{position:absolute;inset:0;width:100%;height:100%;margin:0;opacity:0;cursor:pointer}
      .cf-switch span{position:absolute;inset:0;border-radius:99px;background:#B9C8DA;transition:background .15s;pointer-events:none}
      .cf-switch span::after{content:"";position:absolute;top:.2rem;left:.2rem;width:1.2rem;height:1.2rem;border-radius:50%;background:#fff;transition:transform .15s}
      .cf-switch input:checked+span{background:var(--pos,#12805C)}
      .cf-switch input:checked+span::after{transform:translateX(1.3rem)}
      .cf-switch input:focus-visible+span{outline:3px solid var(--gold,#E8A317);outline-offset:2px}
      @media(max-width:720px){
        .conta-caixa{height:94vh}
        .conta-corpo{grid-template-columns:1fr;grid-template-rows:auto minmax(0,1fr)}
        .conta-nav{flex-direction:row;overflow-x:auto;border-right:0;border-bottom:1px solid var(--line,#DDE5ED);padding:.6rem}
        .conta-nav button{flex:none;white-space:nowrap}
        .conta-painel{padding:1.2rem}
        .conta-linha{flex-direction:column;align-items:flex-start;gap:.8rem}
      }
      @media(prefers-reduced-motion:reduce){.cf-switch span,.cf-switch span::after{transition:none}}`;
    document.head.appendChild(st);
  }

  // ---------------------------------------------------------------- utilidades
  const hojeISO = () => { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };
  const salvarUsuario = dados => localStorage.setItem('sosv_usuario', JSON.stringify(Object.assign({}, usuarioAtual(), dados)));
  function mensagem(painel, texto, tipo) {
    const el = painel.querySelector('#cf-msg');
    if (!el) return;
    el.className = 'aviso' + (tipo === 'erro' ? ' erro' : tipo === 'ok' ? ' ok' : '');
    el.textContent = texto;
    el.hidden = !texto;
  }
  function comOlho(painel) {                               // botão "mostrar senha" nos campos de senha desta seção
    if (window.aplicarOlhoSenha) return window.aplicarOlhoSenha(painel);
    const s = document.createElement('script');
    s.src = 'js/senha-visivel.js';
    s.onload = () => window.aplicarOlhoSenha && window.aplicarOlhoSenha(painel);
    document.head.appendChild(s);
  }

  // ---------------------------------------------------------------- seções
  const render = {};

  render.perfil = painel => {
    const u = usuarioAtual();
    painel.innerHTML =
      '<h3>Perfil</h3><p class="rot">Seus dados no SOS Virtual.</p>' +
      '<div class="conta-id"><span class="perfil-avatar grande" data-avatar aria-hidden="true">' + esc(inicialDe(u.nome)) + '</span>' +
      '<div><b data-nome-usuario>' + esc(u.nome || '') + '</b><div class="rot">' + esc(u.email || '') + '</div></div></div>' +
      '<form id="cf-perfil" novalidate>' +
      '<div class="campo"><label for="cf-nome">Nome</label><input id="cf-nome" maxlength="120" autocomplete="name"></div>' +
      '<div class="campo"><label for="cf-email">E-mail</label><input id="cf-email" type="email" disabled><div class="rot" style="margin-top:.3rem">O e-mail é o seu login e não pode ser alterado aqui.</div></div>' +
      '<div class="campo"><label for="cf-renda">Renda mensal (R$)</label><input id="cf-renda" type="number" min="0" step="0.01" placeholder="0,00"><div class="rot" style="margin-top:.3rem">Usada no painel para calcular quanto sobra livre depois das parcelas. Deixe em branco se preferir não informar.</div></div>' +
      '<div id="cf-msg" class="aviso" hidden role="status"></div>' +
      '<button class="btn" type="submit">Salvar alterações</button></form>';
    const nome = painel.querySelector('#cf-nome'), email = painel.querySelector('#cf-email'), renda = painel.querySelector('#cf-renda');
    let alterado = false;
    nome.value = u.nome || ''; email.value = u.email || ''; renda.value = u.renda_mensal || '';
    [nome, renda].forEach(c => c.addEventListener('input', () => { alterado = true; }));
    api('/auth/perfil').then(d => {                           // confere com o servidor, sem atropelar quem já começou a digitar
      salvarUsuario(d);
      if (!alterado) { nome.value = d.nome || ''; renda.value = d.renda_mensal || ''; }
      email.value = d.email || '';
    }).catch(() => {});
    painel.querySelector('#cf-perfil').addEventListener('submit', async e => {
      e.preventDefault();
      const novoNome = nome.value.trim(), valor = renda.value === '' ? 0 : parseFloat(renda.value);
      if (novoNome.length < 2) return mensagem(painel, 'Informe seu nome (no mínimo 2 caracteres).', 'erro');
      if (!(valor >= 0)) return mensagem(painel, 'A renda não pode ser negativa.', 'erro');
      try {
        const d = await api('/auth/perfil', { method: 'PUT', body: JSON.stringify({ nome: novoNome, renda_mensal: valor }) });
        salvarUsuario(d); atualizarNomeNoMenu(); alterado = false;
        mensagem(painel, 'Dados salvos.', 'ok');
      } catch (err) { mensagem(painel, msgErro(err), 'erro'); }
    });
  };

  render.seguranca = painel => {
    painel.innerHTML =
      '<h3>Segurança</h3><p class="rot">Troque a senha da sua conta. Por segurança, pedimos a senha atual.</p>' +
      '<form id="cf-senha" novalidate>' +
      '<div class="campo"><label for="cf-atual">Senha atual</label><input type="password" id="cf-atual" autocomplete="current-password"></div>' +
      '<div class="campo"><label for="cf-nova">Nova senha</label><input type="password" id="cf-nova" autocomplete="new-password"><div class="rot" style="margin-top:.3rem">No mínimo 8 caracteres.</div></div>' +
      '<div class="campo"><label for="cf-nova2">Confirmar nova senha</label><input type="password" id="cf-nova2" autocomplete="new-password"></div>' +
      '<div id="cf-msg" class="aviso" hidden role="status"></div>' +
      '<button class="btn" type="submit">Alterar senha</button></form>' +
      '<p class="rot" style="margin-top:1.2rem">Não lembra a senha atual? <a href="recuperar.html">Recupere o acesso por e-mail</a>.</p>';
    comOlho(painel);
    const campo = id => painel.querySelector(id);
    campo('#cf-senha').addEventListener('submit', async e => {
      e.preventDefault();
      const atual = campo('#cf-atual').value, nova = campo('#cf-nova').value, nova2 = campo('#cf-nova2').value;
      if (!atual) return mensagem(painel, 'Informe a senha atual.', 'erro');
      if (nova.length < 8) return mensagem(painel, 'A nova senha precisa ter pelo menos 8 caracteres.', 'erro');
      if (nova !== nova2) return mensagem(painel, 'A confirmação não é igual à nova senha.', 'erro');
      if (nova === atual) return mensagem(painel, 'A nova senha precisa ser diferente da atual.', 'erro');
      try {
        await api('/auth/senha', { method: 'PUT', body: JSON.stringify({ senha_atual: atual, nova_senha: nova }) });
        painel.querySelector('#cf-senha').reset();
        mensagem(painel, 'Senha alterada com sucesso. Use a nova senha no próximo login.', 'ok');
      } catch (err) { mensagem(painel, msgErro(err), 'erro'); }
    });
  };

  async function limparCache(painel) {
    // o sistema guarda no navegador só o login e as preferências; apaga o resto (inclusive restos de versões antigas)
    const manter = k => k === 'sosv_token' || k === 'sosv_usuario' || k.startsWith('sosv_pref_');
    let removidos = 0;
    Object.keys(localStorage).forEach(k => { if (k.startsWith('sosv_') && !manter(k)) { localStorage.removeItem(k); removidos++; } });
    removidos += sessionStorage.length; sessionStorage.clear();
    const tarefas = [];
    if (window.caches && caches.keys) tarefas.push(caches.keys().then(ks => Promise.all(ks.map(k => caches.delete(k))).then(() => { removidos += ks.length; })));
    if (navigator.serviceWorker && navigator.serviceWorker.getRegistrations) tarefas.push(navigator.serviceWorker.getRegistrations().then(rs => Promise.all(rs.map(r => r.unregister())).then(() => { removidos += rs.length; })));
    await Promise.all(tarefas).catch(() => {});
    try { salvarUsuario(await api('/auth/perfil')); } catch (e) { /* sem rede: mantém o que já estava salvo */ }
    mensagem(painel, (removidos ? 'Cache limpo: ' + removidos + (removidos === 1 ? ' item removido' : ' itens removidos') + '.' : 'Nada para limpar: o navegador já estava em ordem.') + ' Atualizando a página…', 'ok');
    setTimeout(() => location.reload(), 900);
  }

  render.preferencias = painel => {
    const ligado = localStorage.getItem(PREF_POPUP) !== '0';
    painel.innerHTML =
      '<h3>Preferências</h3>' +
      '<div class="conta-linha"><div><b>Pop-up de alerta de gastos</b><div class="rot">Mostra um aviso na tela quando um gasto passa do limite de uma categoria. Desligado, os alertas continuam funcionando na página Alertas.</div></div>' +
      '<label class="cf-switch"><input type="checkbox" role="switch" id="cf-popup" aria-label="Mostrar pop-up de alerta de gastos"' + (ligado ? ' checked' : '') + '><span aria-hidden="true"></span></label></div>' +
      '<h3 style="margin-top:1.6rem">Armazenamento do navegador</h3>' +
      '<p class="rot">O SOS Virtual guarda neste navegador apenas o seu login e as suas preferências. Seus dados financeiros ficam na sua conta e <b>não são apagados</b> por aqui.</p>' +
      '<div id="cf-msg" class="aviso" hidden role="status" style="margin-top:.8rem"></div>' +
      '<div class="conta-botoes"><button type="button" class="btn sec" id="cf-cache">Limpar cache e atualizar</button>' +
      '<button type="button" class="btn perigo" id="cf-sair-tudo">Sair e apagar os dados deste navegador</button></div>';
    painel.querySelector('#cf-popup').addEventListener('change', e => {
      localStorage.setItem(PREF_POPUP, e.target.checked ? '1' : '0');
      mensagem(painel, e.target.checked ? 'Pop-up de alerta ligado.' : 'Pop-up de alerta desligado.', 'ok');
    });
    painel.querySelector('#cf-cache').addEventListener('click', () => limparCache(painel));
    painel.querySelector('#cf-sair-tudo').addEventListener('click', () => {
      if (!confirm('Sair e apagar tudo o que este navegador guardou do SOS Virtual (login e preferências)? Seus dados na conta não são afetados.')) return;
      localStorage.clear(); sessionStorage.clear();
      location.href = 'login.html';
    });
  };

  async function exportar(painel) {
    try {
      const dados = await api('/auth/meus-dados');
      const blob = new Blob([JSON.stringify(dados, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'sos-virtual-meus-dados-' + hojeISO() + '.json';
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      mensagem(painel, 'Arquivo gerado. Verifique a pasta de downloads.', 'ok');
    } catch (err) { mensagem(painel, msgErro(err), 'erro'); }
  }

  render.privacidade = painel => {
    painel.innerHTML =
      '<h3>Privacidade e dados</h3><p class="rot">Conforme a LGPD, você pode baixar uma cópia dos seus dados ou excluir a conta. <a href="privacidade.html" target="_blank" rel="noopener">Política de Privacidade</a></p>' +
      '<div class="conta-linha"><div><b>Exportar meus dados</b><div class="rot">Baixa um arquivo com seu perfil, transações, metas, alertas, contas e compras parceladas. A senha não faz parte do arquivo.</div></div>' +
      '<button type="button" class="btn sec" id="cf-export">Baixar meus dados</button></div>' +
      '<div id="cf-msg" class="aviso" hidden role="status"></div>' +
      '<div class="conta-perigo"><b>Excluir minha conta</b>' +
      '<p class="rot" style="margin:.4rem 0 1rem">Apaga a conta e <b>todos</b> os seus dados (transações, metas, alertas, contas e parcelas). Não é possível desfazer. Se quiser guardar uma cópia, exporte antes.</p>' +
      '<form id="cf-excluir" novalidate>' +
      '<div class="campo"><label for="cf-exc-senha">Sua senha</label><input type="password" id="cf-exc-senha" autocomplete="current-password"></div>' +
      '<div class="campo"><label for="cf-exc-conf">Digite EXCLUIR para confirmar</label><input id="cf-exc-conf" autocomplete="off" placeholder="EXCLUIR"></div>' +
      '<button type="submit" class="btn perigo" id="cf-exc-btn" disabled>Excluir minha conta</button></form></div>';
    comOlho(painel);
    painel.querySelector('#cf-export').addEventListener('click', () => exportar(painel));
    const senha = painel.querySelector('#cf-exc-senha'), conf = painel.querySelector('#cf-exc-conf'), botao = painel.querySelector('#cf-exc-btn');
    const liberar = () => { botao.disabled = !(senha.value && conf.value.trim() === 'EXCLUIR'); };
    senha.addEventListener('input', liberar); conf.addEventListener('input', liberar);
    painel.querySelector('#cf-excluir').addEventListener('submit', async e => {
      e.preventDefault();
      if (botao.disabled) return;
      botao.disabled = true;
      try {
        await api('/auth/conta', { method: 'DELETE', body: JSON.stringify({ senha: senha.value }) });
        localStorage.clear(); sessionStorage.clear();
        location.href = 'index.html';
      } catch (err) { mensagem(painel, msgErro(err), 'erro'); liberar(); }
    });
  };

  // ---------------------------------------------------------------- janela
  function mostrarSecao(id, focarAba) {
    secaoAtual = id;
    fundo.querySelectorAll('[role=tab]').forEach(b => {
      const ativa = b.dataset.secao === id;
      b.setAttribute('aria-selected', String(ativa));
      b.tabIndex = ativa ? 0 : -1;
      if (ativa && focarAba) b.focus();
    });
    const painel = fundo.querySelector('[role=tabpanel]');
    painel.setAttribute('aria-labelledby', 'cf-aba-' + id);
    painel.scrollTop = 0;
    render[id](painel);
  }

  function fechar() {
    if (!fundo) return;
    document.removeEventListener('keydown', teclado);
    fundo.remove(); fundo = null;
    if (voltarPara && voltarPara.focus) voltarPara.focus();
  }

  function teclado(e) {
    if (e.key === 'Escape') return fechar();
    if (e.key !== 'Tab' || !fundo) return;
    const itens = [...fundo.querySelectorAll(FOCAVEIS)].filter(x => !x.closest('[hidden]'));
    if (!itens.length) return;
    const primeiro = itens[0], ultimo = itens[itens.length - 1];
    if (e.shiftKey && document.activeElement === primeiro) { e.preventDefault(); ultimo.focus(); }
    else if (!e.shiftKey && document.activeElement === ultimo) { e.preventDefault(); primeiro.focus(); }
  }

  window.abrirPainelConta = function (secao) {
    if (fundo) return;                                          // já está aberta
    estilo();
    voltarPara = document.activeElement;
    fundo = document.createElement('div');
    fundo.className = 'conta-fundo';
    fundo.innerHTML =
      '<div class="conta-caixa" role="dialog" aria-modal="true" aria-labelledby="conta-titulo">' +
      '<div class="conta-topo"><h2 id="conta-titulo">Minha conta</h2><button type="button" class="conta-x" aria-label="Fechar">×</button></div>' +
      '<div class="conta-corpo"><div class="conta-nav" role="tablist" aria-orientation="vertical" aria-label="Seções da conta">' +
      SECOES.map(([id, nome, ic]) => '<button type="button" role="tab" id="cf-aba-' + id + '" data-secao="' + id + '" aria-controls="cf-painel" aria-selected="false" tabIndex="-1">' + ic + nome + '</button>').join('') +
      '</div><div class="conta-painel" id="cf-painel" role="tabpanel" tabindex="-1"></div></div></div>';
    document.body.appendChild(fundo);

    fundo.addEventListener('click', e => { if (e.target === fundo) fechar(); });
    fundo.querySelector('.conta-x').addEventListener('click', fechar);
    const nav = fundo.querySelector('.conta-nav');
    nav.addEventListener('click', e => { const b = e.target.closest('[role=tab]'); if (b) mostrarSecao(b.dataset.secao, false); });
    nav.addEventListener('keydown', e => {                      // setas, Home e End trocam de seção (padrão de abas)
      const ids = SECOES.map(s => s[0]), i = ids.indexOf(secaoAtual);
      const proximo = { ArrowDown: i + 1, ArrowRight: i + 1, ArrowUp: i - 1, ArrowLeft: i - 1, Home: 0, End: ids.length - 1 }[e.key];
      if (proximo === undefined) return;
      e.preventDefault();
      mostrarSecao(ids[(proximo + ids.length) % ids.length], true);
    });
    document.addEventListener('keydown', teclado);
    mostrarSecao(SECOES.some(s => s[0] === secao) ? secao : 'perfil', true);
  };
})();
