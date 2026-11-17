# Borges Intelligence — AI Traffic Operating System

Plataforma de inteligência para gestão, análise e otimização de tráfego pago, operada por agentes
especializados coordenados pelo **Borges Core**.

**Estado atual: Fases 1 e 2 implementadas.** A Fase 2 (Windsor.ai) está testada contra respostas simuladas
no formato real; a validação contra a API real do Windsor.ai ainda está pendente. Veja [docs/PHASES.md](docs/PHASES.md)
para o que existe, o que é simulado e o que vem a seguir, e [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
para as decisões técnicas.

> Clientes de **demonstração** usam dados gerados, sempre sinalizados. Clientes **reais** leem Meta Ads e
> Google Ads pelo Windsor.ai, somente leitura. Não há chamadas a LLM e nenhuma campanha real é alterada.

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

## Conectar um cliente real (Windsor.ai)

1. Defina `BORGES_ENCRYPTION_KEY` (veja `backend/.env.example`). Sem ela a API recusa guardar credenciais.
2. Crie o cliente com fonte de dados **Real**.
3. Em **Configurações**, informe a chave de API do Windsor.ai. Ela é cifrada, testada e nunca mais exibida.
4. Clique em **Escolher contas** e marque só as contas daquele cliente. Uma chave costuma enxergar contas
   de vários clientes; o Borges só lê as marcadas e descarta qualquer linha de outra conta.
5. **Sincronizar agora.** O histórico mostra o resultado e os problemas de qualidade encontrados.

Sem CRM (Fase 5) não há vendas confirmadas: CAC real e ROAS confirmado aparecem como indisponíveis.

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

O E2E da Fase 2 usa um Windsor.ai falso local (nunca a API real):

```bash
cd backend && .venv/bin/python -m tests.fake_windsor_server 8099
```

```bash
cd backend && BORGES_WINDSOR_BASE_URL=http://127.0.0.1:8099 .venv/bin/uvicorn app.main:app --port 8000
```

```bash
cd frontend && E2E_EMAIL=admin@borges.local E2E_PASSWORD=... node e2e/phase2.cjs
```

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
  services/     métricas, auditoria, isolamento por cliente, ingestão, sincronização
  connectors/   contrato de conectores, demonstração e Windsor.ai (leitura)
  agents/       Borges Core, Data Intelligence, Performance Auditor, Financial Intelligence
  decision/     motor de decisão (funções puras)
  execution/    aprovação, validação pré-execução, execução verificada
frontend/       Next.js (App Router) + TypeScript + Tailwind
docs/           arquitetura e fases
```
