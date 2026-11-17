# Arquitetura

## Visão geral

Monólito modular: um backend FastAPI, um frontend Next.js e um PostgreSQL. As fronteiras entre
módulos são as que o produto vai precisar ao crescer (conectores, agentes, decisão, execução,
auditoria), mas tudo roda em um processo — sem microsserviços enquanto não houver motivo.

```
Navegador ──> Next.js ──(/api, proxy same-origin)──> FastAPI ──> PostgreSQL <── worker (rotinas)
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
| **Fila no banco, sem Redis (Fase 6)** | As rotinas são poucas por cliente e por dia. A tabela `routines` guarda o próximo horário; o worker reserva as vencidas com `FOR UPDATE SKIP LOCKED` (PostgreSQL). Um serviço a menos para instalar no Windows e no Docker. |
| **Regras decidem; IA só redige** | Diagnóstico e recomendações vêm de regras auditáveis. A IA da Anthropic (opcional) interpreta a pergunta e redige a resposta a partir desses fatos, nunca calcula nem cria recomendações. |
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
- `ad_sets`, `ads`, `breakdown_daily` — conjuntos/grupos, anúncios e fatos diários no nível mais baixo que
  a fonte entrega. A verdade dos indicadores continua em `metric_daily`; o detalhe é reconciliado contra ela.
- `integrations` — credencial cifrada e contas selecionadas, por cliente. `sync_runs` — cada sincronização.
- `audit_log` — trilha somente-inserção encadeada por hash.
- `routines`, `routine_runs` — agenda por cliente (horário de parede no fuso do cliente, próximo horário em UTC)
  e cada execução com resumo ou erro.
- `alerts` — anomalias e avisos das rotinas (aberto, ciente, resolvido), sem repetição enquanto aberto.
- `reports` — relatórios gerados, com o conteúdo congelado no momento da geração.
- `learnings` — memória de aprendizados: origem, evidência, status (hipótese, validado, refutado) e confiabilidade.

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

## Conector Windsor.ai (somente leitura)

`connectors/windsor.py` tem duas partes: `WindsorClient` (HTTP: autenticação, 3 tentativas com espera
para 429/5xx/rede, erros que nunca contêm a chave) e `WindsorConnector` (normalização).

Regras de normalização, derivadas do formato real das linhas:

| Situação na fonte | Tratamento |
|---|---|
| Meta: orçamento diário em centavos | dividido por 100 |
| Meta: ação ausente (`null`) em linha com entrega | zero; sem entrega, permanece indisponível |
| Meta: leads | leads + conversas iniciadas por mensagem |
| Google: `conversions` | entram como leads; compras atribuídas ficam indisponíveis |
| Google: orçamento da campanha | indisponível nesta fonte (ações de orçamento viram revisão manual) |
| Campanha renomeada no período (duas linhas no mesmo dia) | somadas pelo ID; fato reportado |
| Alcance | lido no nível da campanha; não é somado entre anúncios |
| Conta em moeda diferente da do cliente | ignorada e reportada (não há conversão de câmbio) |
| Linha de conta não selecionada para o cliente | descartada e reportada |

A cada sincronização o investimento por anúncio/grupo é somado e comparado ao da campanha, dia a dia
(tolerância de 1%). Divergências, lacunas, dados com mais de 36 horas e falhas aparecem em
“Qualidade dos dados” no dashboard e nas análises.

**O que foi verificado e como**
- Formato da requisição (`/{conector}?api_key=…&date_from=…&date_to=…&fields=…&select_accounts=a,b`),
  resposta `{"data": [...]}` e limite de 600 requisições/minuto: documentação oficial da API do Windsor.ai.
  A autenticação só é aceita na query string.
- Chave ausente ou inválida: a API real responde **HTTP 400** com `{"error":"Not authorized","code":"unauthorized"}`
  (a documentação cita 401). O conector trata os dois.
- Nomes de campos: catálogo real do Windsor.ai.
- Normalização e reconciliação: conferidas com linhas reais de contas Meta (soma dos anúncios igual ao
  total da campanha em investimento e em conversas). Casos reais cobertos em teste: orçamento no conjunto
  (`campaign_daily_budget` nulo) e compra atribuída a campanha pausada sem entrega no dia.

**Pendências conhecidas do conector**
- Uma sincronização completa pela API REST com uma chave real ainda não foi executada.
- Linhas reais de Google Ads das contas em uso não foram conferidas (sem entrega no dia amostrado).
- Datas vêm no fuso da conta de anúncios; não há conversão para o fuso do cliente.
- A descoberta de contas só lista contas com dados nos últimos 30 dias.
- A sincronização é síncrona (dentro da requisição). Fila e agendamento entram na Fase 6.

`BORGES_WINDSOR_ALLOWED_ACCOUNTS` (opcional) limita, para a instalação inteira, quais contas podem ser
vistas, selecionadas e lidas — útil quando a chave enxerga contas fora do escopo de trabalho.

Credenciais: cifradas com Fernet (`core/crypto.py`), chave em `BORGES_ENCRYPTION_KEY`, fora do banco.
A API devolve apenas os 4 últimos caracteres. Trocar ou perder a chave exige recadastrar as credenciais.

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

## Especialistas (abaixo da campanha)

`decision/specialists.py` recebe o retrato da campanha e os totais de cada anúncio (Meta) ou grupo
(Google) e devolve recomendações, também como funções puras. Nenhuma regra desse nível fala em CAC,
porque vendas confirmadas só existem por campanha. Limiares e a justificativa estatística de cada regra
estão no topo do arquivo.

## IA (Anthropic)

`ai/narrator.py`, pelo SDK oficial (`anthropic`). Modelo padrão Claude Opus 5.5, esforço configurável,
saída estruturada (JSON validado) e reserva no servidor (`fallbacks: "default"`) para recusas. Salvaguardas:
o pior custo possível da chamada é conferido contra o limite mensal antes de chamar; cada número da
resposta precisa existir nos fatos enviados; qualquer falha devolve a resposta das regras. Uso e custo de
cada chamada ficam em `ai_usage`. Enviados à Anthropic: nome do cliente, nomes de campanhas/anúncios e
métricas agregadas; nenhum dado pessoal de leads.

## Execução e segurança

Ações executáveis: orçamento diário de campanha e pausa de anúncio (Meta), pausa de grupo (Google). Em
clientes de demonstração a execução é simulada; em clientes reais vai pelo Windsor.ai (`connectors/windsor_write.py`)
somente com a escrita ligada pelo administrador. Aprovar uma recomendação de orçamento dispara, nesta ordem: conector de escrita disponível, nível de
operação, conta correta, estado atual igual ao da recomendação, limite financeiro do cliente, valor
válido. Qualquer falha registra a execução como **falhou** e nada é alterado. Em caso de sucesso, o
valor é relido antes de marcar **concluída**. Uma chave de idempotência única impede dupla execução.

Em cliente real, a execução envia a ação ao Windsor.ai e relê o valor. Se a plataforma pedir confirmação
(aumento de gasto), a execução espera uma segunda confirmação humana; se o dado relido ainda não mostra a
mudança (cache), fica "aguardando verificação". Sem escrita ligada, a execução é bloqueada e registrada,
nunca fingida.

Auditoria: cada registro guarda o hash do anterior; `GET /api/audit/verify` recalcula a cadeia. No
PostgreSQL um gatilho bloqueia `UPDATE`/`DELETE`. Isso torna adulteração evidente; não protege contra
um superusuário do banco que remova o gatilho e reescreva a cadeia inteira.

## Automações (Fase 6)

`automation/schedule.py` calcula o próximo horário (funções puras, testadas com horário de verão).
`automation/routines.py` define as rotinas e o ciclo do worker (`app/worker.py`): marcar execuções presas como
falhas, criar as rotinas padrão de clientes novos, reservar as vencidas e rodar cada uma em transação própria.
As rotinas chamam os mesmos serviços da API (sincronização, Borges Core, biblioteca de criativos, Radar,
experimentos) e não têm caminho de escrita: nenhuma importa o executor. `reports/builder.py` monta os relatórios;
`learning/impact.py` mede antes x depois e `learning/service.py` aplica a regra de que só experimento valida.

## Limitações de segurança conhecidas

- Sem limite de tentativas de login (as recusas são auditadas).
- Sem proteção CSRF dedicada: depende de `SameSite=Lax` e de a API só aceitar JSON.
- Sem tela de gestão de usuários/vínculos (apenas CLI) e sem troca de senha pela interface.
- Dados pessoais (LGPD): hoje só e-mail e nome de usuários. Leads e conversas entram na Fase 5 e
  exigirão base legal, minimização e política de retenção.
