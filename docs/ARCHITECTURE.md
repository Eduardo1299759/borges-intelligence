# Arquitetura

## Visão geral

Monólito modular: um backend FastAPI, um frontend Next.js e um PostgreSQL. As fronteiras entre
módulos são as que o produto vai precisar ao crescer (conectores, agentes, decisão, execução,
auditoria), mas tudo roda em um processo — sem microsserviços enquanto não houver motivo.

```
Navegador ──> Next.js ──(/api, proxy same-origin)──> FastAPI ──> PostgreSQL
                                                       │
              api/ ─> services/ ─> agents/ ─> decision/ ─> execution/
                          │                                    │
                     connectors/ (leitura)            connectors/ (escrita, Fase 5)
```

## Decisões e motivos

| Decisão | Motivo |
|---|---|
| FastAPI + SQLAlchemy 2 + Alembic | Contratos tipados (Pydantic), ecossistema de dados/IA em Python, migrações versionadas. |
| Proxy `/api` no Next.js | Sessão em cookie `httpOnly` + `SameSite=Lax` same-origin: sem token em `localStorage`, sem CORS. |
| SQLite como padrão local, PostgreSQL em Docker/produção | Rodar sem dependências; a suíte passa nos dois bancos. |
| **Sem Redis/filas na Fase 1** | Ainda não há trabalho assíncrono. Entram com o agendador (Fase 6). |
| **Borges Core determinístico, sem LLM** | Regras auditáveis e testáveis, custo zero. O LLM entra na Fase 3 atrás de uma interface, para redigir e interpretar — não para substituir os cálculos. |
| Motor de decisão em funções puras | Cada regra é testada com números controlados, sem banco. |
| Leitura e escrita como contratos separados | Ter leitura (ex.: Windsor.ai) nunca implica poder alterar campanhas. |

## Modelo de dados

- `users`, `user_client_access` — autenticação, papéis e vínculo usuário↔cliente.
- `clients` — metas (CAC, ROAS), margem, nível de operação, limite de variação de orçamento, modo de dados.
- `ad_accounts`, `campaigns` — estrutura publicitária.
- `metric_daily` — fatos diários da **plataforma** (investimento, cliques, leads, receita *atribuída*).
- `sales_daily` — vendas **confirmadas** (CRM/pedidos). Separadas de propósito da receita atribuída.
- `analysis_runs`, `recommendations` — análises do Borges Core e recomendações estruturadas.
- `approval_decisions`, `executions` — decisão humana e execução (com verificações e estado antes/depois).
- `audit_log` — trilha somente-inserção encadeada por hash.

Toda tabela de negócio tem `client_id`. O acesso passa por `services/access.py`; um cliente de
terceiros responde 404, igual a um inexistente.

## Princípios aplicados no código

- **Indisponível ≠ zero.** Colunas e indicadores usam `NULL`/`None`; divisões impossíveis retornam
  `None` e a interface mostra “—”.
- **Receita ≠ lucro.** Lucro de contribuição, ROAS de equilíbrio e CAC máximo só existem se a margem
  foi informada.
- **Atribuído ≠ confirmado.** CAC real e ROAS confirmado usam apenas vendas confirmadas.
- **Demonstração sempre sinalizada.** `is_demo` acompanha métricas, análises e recomendações; fontes
  aparecem como `demo_ads`/`demo_crm`.
- **Não decidir sobre ruído.** Abaixo de 7 dias, ou de 30 leads e 10 vendas, a recomendação é não alterar.

## Motor de decisão

Uma recomendação por campanha, pela primeira regra aplicável (`decision/engine.py`):

1. Amostra insuficiente → não alterar.
2. Receita atribuída ≥ 1,5x (ou ≤ 1/1,5) da confirmada → auditar rastreamento antes de mexer em verba.
3. CTR da 2ª metade ≤ 80% da 1ª **e** frequência ≥ 120% → renovar criativos.
4. CAC real > 120% da meta → se o custo por lead é normal e a taxa lead→venda é baixa, investigar
   qualidade do lead; senão, reduzir orçamento.
5. ROAS confirmado ≥ 120% da meta e CAC dentro da meta → escalar gradualmente.
6. Caso contrário → manter.

Os limiares são pontos de partida conservadores, não verdades universais; devem ser calibrados com
dados reais. Prioridade = participação no investimento × severidade da regra.

## Execução e segurança

Aprovar uma recomendação de orçamento dispara, nesta ordem: conector de escrita disponível, nível de
operação, conta correta, estado atual igual ao da recomendação, limite financeiro do cliente, valor
válido. Qualquer falha registra a execução como **falhou** e nada é alterado. Em caso de sucesso, o
valor é relido antes de marcar **concluída**. Uma chave de idempotência única impede dupla execução.

Para clientes reais não há conector de escrita: a execução é bloqueada e registrada, nunca fingida.

Auditoria: cada registro guarda o hash do anterior; `GET /api/audit/verify` recalcula a cadeia. No
PostgreSQL um gatilho bloqueia `UPDATE`/`DELETE`. Isso torna adulteração evidente; não protege contra
um superusuário do banco que remova o gatilho e reescreva a cadeia inteira.

## Limitações de segurança conhecidas

- Sem limite de tentativas de login (as recusas são auditadas).
- Sem proteção CSRF dedicada: depende de `SameSite=Lax` e de a API só aceitar JSON.
- Sem tela de gestão de usuários/vínculos (apenas CLI) e sem troca de senha pela interface.
- Dados pessoais (LGPD): hoje só e-mail e nome de usuários. Leads e conversas entram na Fase 5 e
  exigirão base legal, minimização e política de retenção.
