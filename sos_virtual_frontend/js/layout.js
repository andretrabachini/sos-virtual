// Sidebar única, menu mobile e dados do usuário. Use <div id="app-sidebar"></div> dentro de .layout
// e <body data-page="dashboard|transacoes|metas|assistente">.
(function () {
  const ic = p => `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">${p}</svg>`;
  const NAV = [
    { id: 'dashboard',  href: 'dashboard.html',  label: 'Dashboard',    icon: '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>' },
    { id: 'transacoes', href: 'transacoes.html', label: 'Transações',   icon: '<line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>' },
    { id: 'metas',      href: 'metas.html',      label: 'Metas',        icon: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>' },
    { id: 'assistente', href: 'assistente.html', label: 'Assistente IA', icon: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>' },
  ];
  const atual = document.body.dataset.page;
  const u = Auth.usuario() || {};
  const nome = u.nome || 'Usuário';
  const primeiro = nome.split(' ')[0];

  const html = `
  <aside class="sidebar" id="sidebar" aria-label="Menu principal">
    <div class="logo">SOS <span>Virtual</span></div>
    <nav>${NAV.map(n => `<a href="${n.href}" class="nav-item${n.id === atual ? ' active' : ''}"${n.id === atual ? ' aria-current="page"' : ''}>${ic(n.icon)}${n.label}</a>`).join('')}</nav>
    <div class="sidebar-footer">
      <div class="user-info">
        <div class="avatar" aria-hidden="true">${nome.charAt(0).toUpperCase()}</div>
        <div><div class="user-name"></div><div class="user-role">Conta pessoal</div></div>
      </div>
      <button type="button" class="nav-item nav-sair" id="btn-sair">${ic('<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>')}Sair</button>
    </div>
  </aside>`;

  const slot = document.getElementById('app-sidebar');
  slot.outerHTML = html;
  document.querySelector('.user-name').textContent = nome; // textContent: sem risco de XSS
  document.querySelectorAll('[data-user-name]').forEach(el => el.textContent = primeiro);

  // menu mobile
  const btn = document.createElement('button');
  btn.className = 'menu-btn'; btn.type = 'button';
  btn.setAttribute('aria-label', 'Abrir menu'); btn.setAttribute('aria-controls', 'sidebar');
  btn.innerHTML = ic('<line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>');
  const overlay = document.createElement('div'); overlay.className = 'menu-overlay';
  document.body.append(btn, overlay);
  const alternar = abrir => { document.body.classList.toggle('menu-aberto', abrir); btn.setAttribute('aria-expanded', abrir); };
  btn.addEventListener('click', () => alternar(!document.body.classList.contains('menu-aberto')));
  overlay.addEventListener('click', () => alternar(false));
  document.addEventListener('keydown', e => { if (e.key === 'Escape') alternar(false); });

  document.getElementById('btn-sair').addEventListener('click', () => Auth.sair());
})();
