// Botão "mostrar/ocultar senha". Basta incluir este script no fim do <body>:
// ele coloca o botão em todo <input type="password"> da página (login, cadastro, redefinir...).
// Para janelas criadas depois (ex.: "Minha conta"), chame window.aplicarOlhoSenha(elementoRaiz).
(function () {
  if (window.aplicarOlhoSenha) return;

  const estilo = document.createElement('style');
  estilo.textContent = `
    .senha-wrap{position:relative}
    .campo .senha-wrap input{padding-right:2.9rem}
    .senha-btn{position:absolute;top:50%;right:.45rem;transform:translateY(-50%);display:grid;place-items:center;
      padding:.4rem;border:0;border-radius:8px;background:none;color:var(--ink2,#52667E);cursor:pointer;line-height:0}
    .senha-btn:hover{background:var(--bg,#F2F5F8);color:var(--brand,#0E2A47)}`;
  document.head.appendChild(estilo);

  const svg = caminhos => `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${caminhos}</svg>`;
  const OLHO = svg('<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>');
  const OLHO_RISCADO = svg('<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/>');

  window.aplicarOlhoSenha = function (raiz) {
    (raiz || document).querySelectorAll('input[type="password"]').forEach(campo => {
      if (campo.parentNode.classList.contains('senha-wrap')) return;      // já tem o botão
      const caixa = document.createElement('div');
      caixa.className = 'senha-wrap';
      campo.parentNode.insertBefore(caixa, campo);
      caixa.appendChild(campo);

      // com a senha visível o navegador não deve corrigir nem capitalizar o texto
      campo.spellcheck = false;
      campo.setAttribute('autocapitalize', 'off');
      campo.setAttribute('autocorrect', 'off');

      const botao = document.createElement('button');
      botao.type = 'button'; // não envia o formulário
      botao.className = 'senha-btn';

      const mostrar = visivel => {
        campo.type = visivel ? 'text' : 'password';
        botao.innerHTML = visivel ? OLHO_RISCADO : OLHO;
        botao.setAttribute('aria-pressed', String(visivel));
        botao.setAttribute('aria-label', visivel ? 'Ocultar senha' : 'Mostrar senha');
        botao.title = visivel ? 'Ocultar senha' : 'Mostrar senha';
      };
      botao.addEventListener('click', () => { mostrar(campo.type === 'password'); campo.focus(); });
      mostrar(false);
      caixa.appendChild(botao);

      // ao enviar o formulário a senha volta a ficar oculta
      if (campo.form) campo.form.addEventListener('submit', () => mostrar(false));
    });
  };

  window.aplicarOlhoSenha(document);
})();
