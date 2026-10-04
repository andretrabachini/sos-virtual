// SOS Virtual — código compartilhado pelas páginas logadas
const API = 'http://127.0.0.1:5000/api';

const brl = v => Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function usuarioAtual() {
  try { return JSON.parse(localStorage.getItem('sosv_usuario')) || {}; } catch { return {}; }
}

// fetch com token; lança erro com mensagem amigável quando a API falha
async function api(rota, opcoes = {}) {
  const res = await fetch(API + rota, {
    ...opcoes,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + (localStorage.getItem('sosv_token') || ''),
      ...(opcoes.headers || {})
    }
  });
  const dados = await res.json().catch(() => ({}));
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
    ['assistente', 'Assistente', 'assistente.html']
  ];
  const atual = document.body.dataset.pagina;
  const u = usuarioAtual();
  alvo.className = 'side';
  alvo.innerHTML =
    '<a class="logo" href="dashboard.html">SOS<i>Virtual</i></a>' +
    links.map(([id, nome, url]) =>
      `<a class="nav${id === atual ? ' ativo' : ''}" href="${url}">${nome}</a>`).join('') +
    `<div class="rodape"><b>${esc(u.nome || 'Visitante')}</b>Conta pessoal<br><button onclick="sair()">Sair</button></div>`;
})();

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
