"""Estado real de cada integração. Nada aqui é marcado como conectado sem ter sido testado."""

INTEGRATIONS = [
    {"key": "demo", "name": "Dados demonstrativos", "kind": "leitura + escrita simulada", "status": "available",
     "note": "Gerador determinístico interno. Sempre sinalizado como demonstração."},
    {"key": "windsor", "name": "Windsor.ai", "kind": "leitura", "status": "available",
     "note": "Meta Ads e Google Ads em leitura, configurado por cliente. Não concede escrita. "
             "Testado com respostas simuladas no formato real; a chamada real depende da sua chave."},
    {"key": "windsor_write", "name": "Windsor.ai (escrita)", "kind": "escrita", "status": "available",
     "note": "Orçamento de campanha e pausa de anúncio (Meta) e pausa de grupo (Google). Desligada por cliente "
             "até um administrador ligar; exige escrita habilitada no time do Windsor.ai."},
    {"key": "meta_ad_library", "name": "Biblioteca de Anúncios da Meta", "kind": "leitura", "status": "planned",
     "phase": 4, "note": "Exige token de acesso com identidade confirmada pela Meta. Até lá, anúncios de "
                         "concorrentes são cadastrados manualmente no Radar."},
    {"key": "ga4", "name": "Google Analytics 4", "kind": "leitura", "status": "planned", "phase": 5, "note": ""},
    {"key": "gsc", "name": "Google Search Console", "kind": "leitura", "status": "planned", "phase": 5, "note": ""},
    {"key": "gtm", "name": "Google Tag Manager", "kind": "leitura", "status": "planned", "phase": 5, "note": ""},
    {"key": "crm", "name": "CRM / vendas (planilha)", "kind": "leitura", "status": "available",
     "note": "Importação de pedidos e leads em CSV, sem dados pessoais. Conexão direta com CRMs: próxima etapa."},
    {"key": "whatsapp", "name": "WhatsApp", "kind": "leitura", "status": "planned", "phase": 5,
     "note": "Somente com integração autorizada e base legal LGPD."},
]
