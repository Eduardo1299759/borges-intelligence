"""Estado real de cada integração. Nada aqui é marcado como conectado sem ter sido testado."""

INTEGRATIONS = [
    {"key": "demo", "name": "Dados demonstrativos", "kind": "leitura + escrita simulada", "status": "available",
     "note": "Gerador determinístico interno. Sempre sinalizado como demonstração."},
    {"key": "windsor", "name": "Windsor.ai", "kind": "leitura", "status": "available",
     "note": "Meta Ads e Google Ads em leitura, configurado por cliente. Não concede escrita. "
             "Testado com respostas simuladas no formato real; a chamada real depende da sua chave."},
    {"key": "meta_ads", "name": "Meta Ads (direto)", "kind": "escrita", "status": "planned", "phase": 5,
     "note": "A leitura vem pelo Windsor.ai. Conector direto, com escrita autorizada, na Fase 5."},
    {"key": "google_ads", "name": "Google Ads (direto)", "kind": "escrita", "status": "planned", "phase": 5,
     "note": "A leitura vem pelo Windsor.ai. Conector direto, com escrita autorizada, na Fase 5."},
    {"key": "ga4", "name": "Google Analytics 4", "kind": "leitura", "status": "planned", "phase": 5, "note": ""},
    {"key": "gsc", "name": "Google Search Console", "kind": "leitura", "status": "planned", "phase": 5, "note": ""},
    {"key": "gtm", "name": "Google Tag Manager", "kind": "leitura", "status": "planned", "phase": 5, "note": ""},
    {"key": "crm", "name": "CRM / vendas", "kind": "leitura", "status": "planned", "phase": 5, "note": ""},
    {"key": "whatsapp", "name": "WhatsApp", "kind": "leitura", "status": "planned", "phase": 5,
     "note": "Somente com integração autorizada e base legal LGPD."},
]
