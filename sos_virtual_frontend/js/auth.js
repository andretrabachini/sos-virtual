// Sessão, proteção de rotas e logout.
const Auth = {
  token()   { return localStorage.getItem('sosv_token') || ''; },
  usuario() { try { return JSON.parse(localStorage.getItem('sosv_usuario')); } catch { return null; } },

  salvarSessao(token, usuario) {
    localStorage.setItem('sosv_token', token);
    localStorage.setItem('sosv_usuario', JSON.stringify(usuario));
  },

  // Chame no topo de toda página interna.
  exigirLogin() {
    if (!this.token()) location.replace('index.html#login');
  },

  // Chame em index/cadastro: quem já está logado vai direto ao painel.
  redirecionarSeLogado() {
    if (this.token()) location.replace('dashboard.html');
  },

  sair(expirou = false) {
    localStorage.removeItem('sosv_token');
    localStorage.removeItem('sosv_usuario');
    location.replace('index.html' + (expirou ? '?sessao=expirada' : '') + '#login');
  },
};
