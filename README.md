# Borges Intelligence — AI Traffic Operating System

Plataforma de inteligência para gestão, análise e otimização de tráfego pago, operada por agentes
especializados coordenados pelo **Borges Core**.

**Estado atual: Fase 1 concluída (fundação funcional + MVP).** Veja [docs/PHASES.md](docs/PHASES.md)
para o que existe, o que é simulado e o que vem a seguir, e [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
para as decisões técnicas.

> Esta versão opera apenas com **dados demonstrativos**, sempre sinalizados. Não há integração com
> plataformas de anúncios, não há chamadas a LLM e nenhuma campanha real é lida ou alterada.

## Executar localmente (sem Docker)

Requisitos: Python 3.11+, Node 20+.

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env
.venv/bin/python -m app.cli init-db
.venv/bin/python -m app.cli seed          # cria o administrador (a senha gerada aparece uma única vez)
.venv/bin/uvicorn app.main:app --port 8000
```

Em outro terminal:

```bash
cd frontend
npm install
npm run dev                                # http://localhost:3000
```

O padrão local é SQLite. Para PostgreSQL, ajuste `BORGES_DATABASE_URL` em `backend/.env`.

## Executar com Docker

```bash
cp .env.example .env                       # preencha as três variáveis vazias
docker compose up --build                  # http://localhost:3000
```

## Testes

```bash
cd backend
.venv/bin/pytest                           # SQLite em memória
BORGES_TEST_DATABASE_URL=postgresql+psycopg://usuario:senha@localhost:5432/borges_test .venv/bin/pytest
.venv/bin/ruff check .
```

```bash
cd frontend
npm run lint && npm run build
E2E_EMAIL=admin@borges.local E2E_PASSWORD=... node e2e/mvp.cjs   # exige API + frontend no ar e Playwright
```

O teste E2E percorre no navegador os dez critérios de aceitação do MVP.

## Usuários e papéis

```bash
.venv/bin/python -m app.cli create-user ana@empresa.com "Ana" manager
```

| Papel | Pode |
|---|---|
| `admin` | Tudo, em todos os clientes; verificar a integridade da auditoria |
| `manager` | Criar/editar seus clientes, analisar, aprovar e rejeitar |
| `analyst` | Ler e solicitar análises |
| `viewer` | Somente leitura |

Usuários não administradores só enxergam clientes aos quais foram vinculados (hoje: os que criaram).

## Estrutura

```
backend/app/
  core/         configuração, banco, segurança, logs
  models.py     modelo de dados
  api/          rotas HTTP (camada fina)
  services/     métricas, auditoria, isolamento por cliente, ingestão
  connectors/   contrato de conectores + conector de demonstração
  agents/       Borges Core, Data Intelligence, Performance Auditor, Financial Intelligence
  decision/     motor de decisão (funções puras)
  execution/    aprovação, validação pré-execução, execução verificada
frontend/       Next.js (App Router) + TypeScript + Tailwind
docs/           arquitetura e fases
```
