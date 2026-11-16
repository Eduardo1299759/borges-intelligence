"""Estado real de cada integração. Nada aqui é marcado como conectado sem ter sido testado."""

INTEGRATIONS = [
    {"key": "demo", "name": "Dados demonstrativos", "kind": "leitura + escrita simulada", "status": "available",
     "note": "Gerador determinístico interno. Sempre sinalizado como demonstração."},
    {"key": "windsor", "name": "Windsor.ai", "kind": "leitura", "status": "planned", "phase": 2,
     "note": "Fonte principal de leitura de dados publicitários. Não concede escrita."},
    {"key": "meta_ads", "name": "Meta Ads", "kind": "leitura + escrita", "status": "planned", "phase": 2,
     "note": "Leitura na Fase 2; escrita autorizada na Fase 5."},
    {"key": "google_ads", "name": "Google Ads", "kind": "leitura + escrita", "status": "planned", "phase": 2,
     "note": "Leitura na Fase 2; escrita autorizada na Fase 5."},
    {"key": "ga4", "name": "Google Analytics 4", "kind": "leitura", "status": "planned", "phase": 2, "note": ""},
    {"key": "gsc", "name": "Google Search Console", "kind": "leitura", "status": "planned", "phase": 2, "note": ""},
    {"key": "gtm", "name": "Google Tag Manager", "kind": "leitura", "status": "planned", "phase": 5, "note": ""},
    {"key": "crm", "name": "CRM / vendas", "kind": "leitura", "status": "planned", "phase": 5, "note": ""},
    {"key": "whatsapp", "name": "WhatsApp", "kind": "leitura", "status": "planned", "phase": 5,
     "note": "Somente com integração autorizada e base legal LGPD."},
]
