// Login (index.html)
Auth.redirecionarSeLogado();

const form = document.getElementById('form-login');
const erro = document.getElementById('login-erro');
const btn  = form.querySelector('button[type=submit]');

if (new URLSearchParams(location.search).get('sessao') === 'expirada') {
  erro.textContent = 'Sessão expirada. Faça login novamente.';
  erro.hidden = false;
}

form.addEventListener('submit', async e => {
  e.preventDefault();
  erro.hidden = true;
  btn.disabled = true; btn.textContent = 'Entrando...';
  try {
    const { token, usuario } = await api('/auth/login', {
      method: 'POST', auth: false,
      body: { email: form.email.value.trim(), senha: form.senha.value }
    });
    Auth.salvarSessao(token, usuario);
    location.href = 'dashboard.html';
  } catch (err) {
    erro.textContent = err.message; erro.hidden = false;
    btn.disabled = false; btn.textContent = 'Entrar na conta →';
  }
});
