// Wrapper único de fetch: token, erros amigáveis, 401 e modo mock.
class ApiError extends Error {
  constructor(msg, status = 0) { super(msg); this.status = status; }
}

// ---------- MOCK (simula o backend; cresce a cada etapa) ----------
const Mock = {
  _users() { return JSON.parse(localStorage.getItem('sosv_mock_users') || '[]'); },
  _save(u) { localStorage.setItem('sosv_mock_users', JSON.stringify(u)); },
  _pub(u) { return { id: u.id, nome: u.nome, email: u.email, renda_mensal: u.renda_mensal }; },

  handle(method, path, body) {
    if (method === 'POST' && path === '/auth/cadastro') {
      const users = this._users();
      if (users.some(u => u.email === body.email)) throw new ApiError('esse email já está em uso', 409);
      const u = { id: Date.now(), nome: body.nome, email: body.email, senha: body.senha,
                  renda_mensal: body.renda_mensal || 0, lgpd_aceito_em: new Date().toISOString() };
      users.push(u); this._save(users);
      return { token: 'mock.' + u.id, usuario: this._pub(u) };
    }
    if (method === 'POST' && path === '/auth/login') {
      const u = this._users().find(x => x.email === body.email && x.senha === body.senha);
      if (!u) throw new ApiError('email ou senha incorretos', 401);
      return { token: 'mock.' + u.id, usuario: this._pub(u) };
    }
    throw new ApiError('Rota ainda não simulada: ' + method + ' ' + path, 404);
  }
};

// ---------- Requisição ----------
async function api(path, { method = 'GET', body = null, auth = true } = {}) {
  if (CONFIG.MOCK) {
    await new Promise(r => setTimeout(r, 250)); // simula latência
    try { return Mock.handle(method, path, body); }
    catch (e) { if (e.status === 401 && auth) Auth.sair(true); throw e; }
  }

  const headers = { 'Content-Type': 'application/json' };
  const token = Auth.token();
  if (auth && token) headers['Authorization'] = 'Bearer ' + token;

  let res;
  try {
    res = await fetch(CONFIG.API_URL + path, { method, headers, body: body ? JSON.stringify(body) : null });
  } catch {
    throw new ApiError('Servidor offline. Verifique se o backend está rodando em ' + CONFIG.API_URL);
  }

  let data = null;
  try { data = await res.json(); } catch { /* resposta sem JSON */ }

  if (res.status === 401 && auth) Auth.sair(true);
  if (!res.ok) throw new ApiError((data && (data.erro || data.msg)) || 'Erro ' + res.status, res.status);
  return data;
}
