// Cadastro (cadastro.html)
Auth.redirecionarSeLogado();

const form = document.getElementById('form-cadastro');
const erro = document.getElementById('cadastro-erro');
const btn  = form.querySelector('button[type=submit]');

function mostrarErro(msg, campo) {
  erro.textContent = msg; erro.hidden = false;
  form.querySelectorAll('.erro-campo').forEach(c => c.classList.remove('erro-campo'));
  if (campo) { campo.classList.add('erro-campo'); campo.focus(); }
}

form.addEventListener('submit', async e => {
  e.preventDefault();
  erro.hidden = true;

  const nome = form.nome.value.trim();
  const email = form.email.value.trim();
  const senha = form.senha.value;
  const renda = parseFloat(form.renda_mensal.value) || 0;

  if (nome.length < 2)                 return mostrarErro('Informe seu nome completo.', form.nome);
  if (!form.email.checkValidity())     return mostrarErro('E-mail inválido.', form.email);
  if (senha.length < 6)                return mostrarErro('A senha precisa ter no mínimo 6 caracteres.', form.senha);
  if (senha !== form.senha2.value)     return mostrarErro('As senhas não coincidem.', form.senha2);
  if (renda < 0)                       return mostrarErro('A renda não pode ser negativa.', form.renda_mensal);
  if (!form.lgpd.checked)              return mostrarErro('É necessário autorizar o tratamento de dados (LGPD) para continuar.', form.lgpd);

  btn.disabled = true; btn.textContent = 'Criando conta...';
  try {
    const { token, usuario } = await api('/auth/cadastro', {
      method: 'POST', auth: false,
      // lgpd_aceito: o backend deve gravar data/hora do consentimento
      body: { nome, email, senha, renda_mensal: renda, lgpd_aceito: true }
    });
    Auth.salvarSessao(token, usuario);
    location.href = 'dashboard.html';
  } catch (err) {
    mostrarErro(err.message);
    btn.disabled = false; btn.textContent = 'Criar conta grátis →';
  }
});
