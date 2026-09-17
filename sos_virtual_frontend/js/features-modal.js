// ══════════════════════════════════════════════
// MODAL DE FUNCIONALIDADES
// ══════════════════════════════════════════════
const FEAT_DATA = {
  dashboard: {
    title: 'Dashboard financeiro',
    desc: 'Tenha uma visão completa da sua vida financeira em tempo real, com dados organizados e fáceis de entender.',
    icon: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>`,
    items: [
      'Gráficos de receitas e despesas por período',
      'Categorização automática de gastos com IA',
      'Saldo atualizado em tempo real',
      'Histórico completo de transações',
    ]
  },
  chat: {
    title: 'Assistente por chat',
    desc: 'Converse de forma natural com nossa IA especializada em finanças pessoais, disponível 24 horas por dia.',
    icon: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`,
    items: [
      'Registre gastos digitando frases naturais',
      'Tire dúvidas sobre finanças pessoais',
      'Receba dicas personalizadas para o seu perfil',
      'Histórico de conversas salvo automaticamente',
    ]
  },
  metas: {
    title: 'Metas inteligentes',
    desc: 'Defina objetivos financeiros e deixe a IA traçar o melhor caminho para você chegar lá.',
    icon: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
    items: [
      'Criação de metas com prazo e valor-alvo',
      'Acompanhamento semanal de progresso',
      'Sugestões automáticas de ajustes',
      'Celebração ao atingir cada objetivo',
    ]
  },
  alertas: {
    title: 'Alertas de gastos',
    desc: 'Nunca mais estoure o orçamento sem perceber. Receba avisos inteligentes antes que seja tarde.',
    icon: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>`,
    items: [
      'Alertas ao atingir 80% do limite por categoria',
      'Notificações de gastos incomuns detectados pela IA',
      'Resumo diário de movimentações',
      'Configuração de limites por categoria',
    ]
  },
  tendencias: {
    title: 'Análise de tendências',
    desc: 'Entenda seus padrões de consumo e tome decisões mais inteligentes com base em dados reais.',
    icon: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>`,
    items: [
      'Comparação de gastos mês a mês',
      'Identificação das categorias que mais crescem',
      'Previsão de gastos para o próximo mês',
      'Relatório mensal gerado automaticamente',
    ]
  },
  seguro: {
    title: '100% seguro',
    desc: 'Seus dados financeiros são tratados com o mais alto nível de segurança e privacidade.',
    icon: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>`,
    items: [
      'Criptografia AES-256 em todos os dados',
      'Nunca compartilhamos informações com terceiros',
      'Acesso protegido por autenticação segura',
      'Conformidade com a LGPD',
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
