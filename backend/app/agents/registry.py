"""Registro dos agentes e do que cada um REALMENTE faz hoje. Agentes planejados não são simulados."""

AGENTS = [
    {"code": "00", "name": "Borges Core", "role": "Diretor estratégico", "status": "active", "phase": 1,
     "capability": "Orquestra validação, auditoria, especialistas e finanças, resolve conflitos e prioriza por "
                   "impacto. Regras determinísticas, sem LLM."},
    {"code": "01", "name": "Data Intelligence", "role": "Coleta e validação de dados", "status": "active", "phase": 2,
     "capability": "Sincroniza Meta e Google via Windsor.ai (leitura), normaliza, detecta lacunas, dados "
                   "desatualizados e divergências entre campanha e anúncios. Sem GA4/CRM ainda."},
    {"code": "02", "name": "Performance Auditor", "role": "Auditoria de contas", "status": "partial", "phase": 3,
     "capability": "Audita campanhas (amostra, rastreamento, fadiga, CAC, escala) e entrega o retrato "
                   "aos especialistas."},
    {"code": "03", "name": "Meta Ads Specialist", "role": "Estrutura e otimização Meta", "status": "partial",
     "phase": 3,
     "capability": "Diagnóstico por anúncio: gasto sem resultado, custo por lead fora da curva e verba "
                   "pulverizada. Pausa anúncio (simulado em demonstração)."},
    {"code": "04", "name": "Google Ads Specialist", "role": "Estrutura e otimização Google", "status": "partial",
     "phase": 3, "capability": "Diagnóstico por grupo de anúncios e conversões sem valor configurado. "
                               "Sem termos de pesquisa nem palavras-chave ainda."},
    {"code": "05", "name": "Creative Intelligence", "role": "Análise e criação de criativos", "status": "partial",
     "phase": 4, "capability": "Biblioteca de criativos com classificação e desgaste; briefings com variações "
                               "(IA ou modelo). Sem geração de imagem."},
    {"code": "06", "name": "Competitive Intelligence", "role": "Inteligência competitiva", "status": "partial",
     "phase": 4, "capability": "Concorrentes e anúncios públicos capturados manualmente; ângulos e "
                               "oportunidades com IA. Biblioteca de Anúncios da Meta aguarda token."},
    {"code": "07", "name": "Sales Intelligence", "role": "Conversão comercial e CRM", "status": "partial", "phase": 5,
     "capability": "Importa pedidos e leads do CRM sem dados pessoais; funil, custo por venda, tempo de "
                   "resposta e motivos de perda por campanha."},
    {"code": "08", "name": "Tracking & CRO", "role": "Mensuração e conversão", "status": "partial", "phase": 5,
     "capability": "Verifica páginas (pixel, GTM, GA4, celular, velocidade), cruza plataforma e CRM e "
                   "sugere UTMs padronizadas."},
    {"code": "09", "name": "Financial Intelligence", "role": "Rentabilidade", "status": "partial", "phase": 2,
     "capability": "CAC real, ROAS de equilíbrio, CAC máximo, lucro de contribuição e ritmo de verba. Sem LTV."},
    {"code": "10", "name": "Experimentation Engine", "role": "Experimentos", "status": "active", "phase": 4,
     "capability": "Testes entre anúncios com tamanho de amostra, teste estatístico, critérios e "
                   "registro do aprendizado."},
    {"code": "11", "name": "Reporting Intelligence", "role": "Relatórios", "status": "planned", "phase": 6,
     "capability": ""},
    {"code": "12", "name": "Operations & Safety", "role": "Execução controlada", "status": "partial", "phase": 5,
     "capability": "Aprovação, validação pré-execução, idempotência, verificação por releitura e auditoria. "
                   "Simulada em demonstração; real pelo Windsor.ai quando ligada pelo administrador."},
]
