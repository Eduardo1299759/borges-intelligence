"""Registro dos agentes e do que cada um REALMENTE faz hoje. Agentes planejados não são simulados."""

AGENTS = [
    {"code": "00", "name": "Borges Core", "role": "Diretor estratégico", "status": "active", "phase": 1,
     "capability": "Orquestra validação, auditoria, finanças e motor de decisão por regras determinísticas. "
                   "Sem LLM nesta fase."},
    {"code": "01", "name": "Data Intelligence", "role": "Coleta e validação de dados", "status": "partial", "phase": 2,
     "capability": "Valida cobertura, lacunas e atualização dos dados armazenados. Conectores reais na Fase 2."},
    {"code": "02", "name": "Performance Auditor", "role": "Auditoria de contas", "status": "partial", "phase": 3,
     "capability": "Audita campanhas (amostra, rastreamento, fadiga, CAC, escala). Sem nível de conjunto/anúncio."},
    {"code": "03", "name": "Meta Ads Specialist", "role": "Estrutura e otimização Meta", "status": "planned",
     "phase": 3,
     "capability": ""},
    {"code": "04", "name": "Google Ads Specialist", "role": "Estrutura e otimização Google", "status": "planned",
     "phase": 3, "capability": ""},
    {"code": "05", "name": "Creative Intelligence", "role": "Análise e criação de criativos", "status": "planned",
     "phase": 4, "capability": ""},
    {"code": "06", "name": "Competitive Intelligence", "role": "Inteligência competitiva", "status": "planned",
     "phase": 4, "capability": ""},
    {"code": "07", "name": "Sales Intelligence", "role": "Conversão comercial e CRM", "status": "planned", "phase": 5,
     "capability": ""},
    {"code": "08", "name": "Tracking & CRO", "role": "Mensuração e conversão", "status": "planned", "phase": 5,
     "capability": ""},
    {"code": "09", "name": "Financial Intelligence", "role": "Rentabilidade", "status": "partial", "phase": 2,
     "capability": "CAC real, ROAS de equilíbrio, CAC máximo e lucro de contribuição. Sem LTV nem projeções."},
    {"code": "10", "name": "Experimentation Engine", "role": "Experimentos", "status": "planned", "phase": 4,
     "capability": ""},
    {"code": "11", "name": "Reporting Intelligence", "role": "Relatórios", "status": "planned", "phase": 6,
     "capability": ""},
    {"code": "12", "name": "Operations & Safety", "role": "Execução controlada", "status": "partial", "phase": 5,
     "capability": "Aprovação, validação pré-execução, idempotência, verificação por releitura e auditoria. "
                   "Execução apenas simulada (modo demonstração)."},
]
