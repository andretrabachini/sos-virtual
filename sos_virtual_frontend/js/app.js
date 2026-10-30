// SOS Virtual — código compartilhado pelas páginas logadas
const API = 'http://127.0.0.1:5000/api';

const brl = v => Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// protege as páginas logadas: sem token, volta para o login
if (document.body.dataset.pagina && !localStorage.getItem('sosv_token')) location.replace('login.html');

function usuarioAtual() {
  try { return JSON.parse(localStorage.getItem('sosv_usuario')) || {}; } catch { return {}; }
}

// fetch com token; lança erro com mensagem amigável quando a API falha
async function api(rota, opcoes = {}) {
  const headers = {
    'Authorization': 'Bearer ' + (localStorage.getItem('sosv_token') || ''),
    ...(opcoes.headers || {})
  };
  // upload de arquivo (FormData): o navegador define o Content-Type sozinho, com o boundary.
  // nos demais casos o corpo é JSON
  if (!(opcoes.body instanceof FormData)) headers['Content-Type'] = headers['Content-Type'] || 'application/json';

  const res = await fetch(API + rota, { ...opcoes, headers });
  const dados = await res.json().catch(() => ({}));
  // sessão expirada em página logada: limpa o token e volta ao login
  if (res.status === 401 && document.body.dataset.pagina) { sair(); throw new Error('Sessão expirada.'); }
  if (!res.ok) throw new Error(dados.erro || dados.msg || 'Erro ' + res.status);
  return dados;
}

function sair() {
  localStorage.removeItem('sosv_token');
  localStorage.removeItem('sosv_usuario');
  location.href = 'login.html';
}

// monta o menu lateral em <aside id="menu"> e marca a página atual (body data-pagina="...")
(function montarMenu() {
  const alvo = document.getElementById('menu');
  if (!alvo) return;
  const links = [
    ['dashboard', 'Painel', 'dashboard.html'],
    ['transacoes', 'Transações', 'transacoes.html'],
    ['metas', 'Metas', 'metas.html'],
    ['alertas', 'Alertas', 'alertas.html'],
    ['otimizador', 'Otimizador', 'grafo.html'],
    ['assistente', 'Assistente', 'assistente.html']
  ];
  const atual = document.body.dataset.pagina;
  const u = usuarioAtual();
  alvo.className = 'side';
  alvo.innerHTML =
    '<a class="logo" href="dashboard.html">SOS<i>Virtual</i></a>' +
    links.map(([id, nome, url]) =>
      `<a class="nav${id === atual ? ' ativo' : ''}" href="${url}">${nome}</a>`).join('') +
    '<button type="button" class="nav nav-conta" data-abrir-conta>Conta</button>' +
    `<div class="rodape"><button type="button" class="perfil-btn" data-abrir-conta aria-haspopup="dialog" title="Abrir minha conta">` +
    `<span class="perfil-avatar" data-avatar aria-hidden="true">${esc(inicialDe(u.nome))}</span>` +
    `<span class="perfil-txt"><b data-nome-usuario>${esc(u.nome || 'Visitante')}</b>Minha conta</span></button>` +
    `<button type="button" class="sair-btn" onclick="sair()">Sair</button></div>`;

  if (!document.getElementById('estilo-perfil-menu')) {
    const st = document.createElement('style');
    st.id = 'estilo-perfil-menu';
    st.textContent = `
      .side .rodape .perfil-btn{display:flex;align-items:center;gap:.7rem;width:100%;margin:0 0 .4rem;padding:.5rem;border-radius:var(--r);text-align:left;text-decoration:none;color:#B9C8DA;line-height:1.3}
      .side .rodape .perfil-btn:hover{background:rgba(255,255,255,.08)}
      .perfil-btn b{display:block;color:#fff;overflow-wrap:anywhere}
      .perfil-avatar{display:grid;place-items:center;flex:none;width:2.3rem;height:2.3rem;border-radius:50%;background:var(--brand2,#1C4A7A);color:#fff;font:700 1rem var(--fh,sans-serif)}
      .perfil-avatar.grande{width:3.4rem;height:3.4rem;font-size:1.4rem}
      .side .nav-conta{display:none}
      @media(max-width:820px){.side .nav-conta{display:flex;flex:1;justify-content:center;align-items:center;padding:.65rem .2rem;border:0;border-radius:var(--r);background:none;color:#B9C8DA;font:500 .74rem var(--fb,sans-serif);cursor:pointer}}`;
    document.head.appendChild(st);
  }
})();

// letra do círculo do perfil
function inicialDe(nome) { return (String(nome || 'V').trim().charAt(0) || 'V').toUpperCase(); }

// atualiza o nome no menu (e em qualquer lugar marcado com data-nome-usuario) depois de editar o perfil
function atualizarNomeNoMenu() {
  const nome = usuarioAtual().nome || 'Visitante';
  document.querySelectorAll('[data-nome-usuario]').forEach(el => { el.textContent = nome; });
  document.querySelectorAll('[data-avatar]').forEach(el => { el.textContent = inicialDe(nome); });
}

// abre a janela "Minha conta" (js/perfil.js é carregado só quando o usuário clica)
function abrirMinhaConta(secao) {
  const abrir = () => window.abrirPainelConta(secao);
  if (window.abrirPainelConta) return abrir();
  const s = document.createElement('script');
  s.src = 'js/perfil.js';
  s.onload = abrir;
  s.onerror = () => alert('Não foi possível abrir a tela da conta. Recarregue a página e tente de novo.');
  document.head.appendChild(s);
}
document.addEventListener('click', e => {
  const gatilho = e.target.closest && e.target.closest('[data-abrir-conta]');
  if (gatilho) abrirMinhaConta();
});

// mensagem amigável para qualquer erro de API (servidor fora do ar ou erro de validação)
const msgErro = e => e instanceof TypeError
  ? 'Não consegui falar com o servidor. Confira se o backend está rodando em http://127.0.0.1:5000.'
  : e.message;

// mostra/esconde o aviso de uma página: aviso('msg', 'texto', 'erro') ou aviso('msg') para limpar
function aviso(id, texto, tipo) {
  const el = document.getElementById(id);
  if (!texto) { el.hidden = true; return; }
  el.className = 'aviso' + (tipo === 'erro' ? ' erro' : '');
  el.textContent = texto;
  el.hidden = false;
}

// Pop-up de alerta de gastos. Chame com a lista "alertas" que a API devolve ao registrar uma despesa:
//   mostrarAlertas(resposta.alertas)   (não faz nada se a lista estiver vazia)
// Fecha com o botão, com Esc ou clicando fora; o foco volta para onde estava.
function mostrarAlertas(lista) {
  if (!Array.isArray(lista) || !lista.length) return;
  if (localStorage.getItem('sosv_pref_alertas_popup') === '0') return;   // desligado em Minha conta > Preferências
  if (!document.getElementById('estilo-alerta')) {
    const st = document.createElement('style');
    st.id = 'estilo-alerta';
    st.textContent = `
      .alerta-fundo{position:fixed;inset:0;z-index:1000;display:grid;place-items:center;padding:1rem;background:rgba(14,42,71,.55)}
      .alerta-caixa{width:100%;max-width:30rem;max-height:90vh;overflow:auto;padding:1.6rem;border-radius:14px;background:#fff;box-shadow:0 20px 60px rgba(14,42,71,.35)}
      .alerta-icone{display:grid;place-items:center;width:2.8rem;height:2.8rem;margin-bottom:.8rem;border-radius:50%;background:#FDECEF;color:var(--neg,#D2415A);font:800 1.5rem var(--fh,sans-serif)}
      .alerta-caixa h2{font-size:1.25rem;margin-bottom:1rem}
      .alerta-item{padding:.9rem 0;border-top:1px solid var(--line,#DDE5ED)}
      .alerta-item>b{font-size:1.05rem}.alerta-item>span{margin-left:.5rem;color:var(--ink2,#52667E);font-size:.88rem}
      .alerta-item .barra{margin:.5rem 0 .4rem}
      .alerta-acoes{display:flex;gap:.6rem;justify-content:flex-end;flex-wrap:wrap;margin-top:1.2rem}`;
    document.head.appendChild(st);
  }
  const antigo = document.querySelector('.alerta-fundo');
  if (antigo) antigo.remove();

  const voltarPara = document.activeElement;
  const fundo = document.createElement('div');
  fundo.className = 'alerta-fundo';
  const plural = lista.length > 1;
  fundo.innerHTML =
    '<div class="alerta-caixa" role="alertdialog" aria-modal="true" aria-labelledby="alerta-titulo" aria-describedby="alerta-corpo">' +
    '<div class="alerta-icone" aria-hidden="true">!</div>' +
    '<h2 id="alerta-titulo">' + (plural ? 'Você ultrapassou ' + lista.length + ' limites de gasto' : 'Você ultrapassou o limite de gasto') + '</h2>' +
    '<div id="alerta-corpo">' + lista.map(a =>
      '<div class="alerta-item"><b>' + esc(a.categoria) + '</b><span>' + (a.cruzou ? 'passou do limite deste mês' : 'continua acima do limite') + '</span>' +
      '<div class="barra perigo"><i style="width:100%"></i></div>' +
      '<div class="linha"><span>Gasto: <b>' + brl(a.gasto) + '</b></span><span>Limite: ' + brl(a.limite) + '</span></div>' +
      '<div class="neg">' + (a.excesso > 0 ? brl(a.excesso) + ' acima do limite' : 'Chegou exatamente ao limite') + '</div></div>').join('') + '</div>' +
    '<div class="alerta-acoes"><a class="btn sec" href="alertas.html">Ver alertas</a><button type="button" class="btn" id="alerta-ok">Entendi</button></div></div>';
  document.body.appendChild(fundo);

  const fechar = () => { document.removeEventListener('keydown', teclado); fundo.remove(); if (voltarPara && voltarPara.focus) voltarPara.focus(); };
  const teclado = e => {
    if (e.key === 'Escape') return fechar();
    if (e.key !== 'Tab') return;
    const itens = [...fundo.querySelectorAll('a,button')];            // mantém o Tab dentro do pop-up
    const primeiro = itens[0], ultimo = itens[itens.length - 1];
    if (e.shiftKey && document.activeElement === primeiro) { e.preventDefault(); ultimo.focus(); }
    else if (!e.shiftKey && document.activeElement === ultimo) { e.preventDefault(); primeiro.focus(); }
  };
  document.addEventListener('keydown', teclado);
  fundo.addEventListener('click', e => { if (e.target === fundo) fechar(); });
  document.getElementById('alerta-ok').addEventListener('click', fechar);
  document.getElementById('alerta-ok').focus();
}
