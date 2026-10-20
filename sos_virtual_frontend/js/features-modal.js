// ══════════════════════════════════════════════
// MODAL DE FUNCIONALIDADES
// Os textos abaixo descrevem apenas o que o sistema faz hoje.
// Quando uma funcionalidade nova ficar pronta (ex.: assistente, comparação mês a mês),
// atualize o item correspondente.
// ══════════════════════════════════════════════
const FEAT_DATA = {
  dashboard: {
    title: 'Dashboard financeiro',
    desc: 'Veja receitas, despesas e saldo do mês em um só lugar, com os dados organizados e fáceis de entender.',
    icon: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>`,
    items: [
      'Receitas, despesas e saldo do mês',
      'Gastos separados por categoria',
      'Categoria sugerida automaticamente a partir da descrição do gasto',
      'Histórico de transações com filtro por mês',
    ]
  },
  chat: {
    title: 'Assistente por chat',
    desc: 'Converse sobre suas finanças e registre gastos escrevendo frases simples.',
    icon: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`,
    items: [
      'Registre gastos digitando frases como "gastei R$ 50 no mercado"',
      'Tire dúvidas sobre finanças pessoais',
      'Atalhos com perguntas frequentes',
    ]
  },
  metas: {
    title: 'Metas',
    desc: 'Defina um valor e, se quiser, um prazo, e acompanhe quanto já guardou.',
    icon: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
    items: [
      'Criação de metas com valor-alvo e prazo opcional',
      'Depósitos que atualizam o progresso na hora',
      'Barra de progresso e indicação de meta concluída',
    ]
  },
  alertas: {
    title: 'Alertas de gastos',
    desc: 'Defina um limite mensal por categoria e veja quando o gasto passar dele.',
    icon: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>`,
    items: [
      'Limite mensal configurável por categoria',
      'Aviso quando o gasto ultrapassa o limite',
      'Barra mostrando quanto do limite já foi usado',
      'Possibilidade de ativar e desativar cada alerta',
    ]
  },
  tendencias: {
    title: 'Análise de tendências',
    desc: 'Entenda seus padrões de consumo com base nos seus próprios lançamentos.',
    icon: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>`,
    items: [
      'Gastos do mês separados por categoria',
      'Em breve: comparação de gastos mês a mês',
      'Em breve: previsão de gastos para o próximo mês',
    ]
  },
  seguro: {
    title: 'Segurança e privacidade',
    desc: 'Medidas de proteção e controle sobre os seus dados financeiros.',
    icon: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>`,
    items: [
      'Senhas guardadas apenas como hash, nunca em texto puro',
      'Acesso por login, com sessão que expira automaticamente',
      'Cada usuário acessa somente os próprios dados',
      'Consentimento LGPD registrado no cadastro',
      'Não compartilhamos seus dados com terceiros',
    ]
  }
};

document.querySelectorAll('.feat-card[data-feat]').forEach(card => {
  card.addEventListener('click', () => {
    const key = card.dataset.feat;
    const data = FEAT_DATA[key];
    if (!data) return;

    document.getElementById('feat-modal-icon').innerHTML = data.icon;
    document.getElementById('feat-modal-title').textContent = data.title;
    document.getElementById('feat-modal-desc').textContent = data.desc;
    document.getElementById('feat-modal-list').innerHTML =
      data.items.map(i => `<li>${i}</li>`).join('');

    openModal('modal-feat');
  });
});

document.getElementById('feat-modal-close').addEventListener('click', () => closeModal('modal-feat'));
