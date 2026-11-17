# Fases

## Fase 1 — Fundação funcional ✅

**Entregue**
- Autenticação (bcrypt + JWT em cookie httpOnly), quatro papéis, isolamento por cliente.
- Cadastro e edição de clientes com metas, margem, nível de operação e limite de orçamento.
- Modo demonstração: 90 dias de dados determinísticos para 6 campanhas (Meta e Google).
- Visão geral, Gestor de campanhas, Central de inteligência, Central de aprovação, Auditoria, Configurações.
- Fatia mínima das Fases 3 e 5 exigida pelo MVP: Borges Core por regras, recomendações estruturadas,
  aprovação/rejeição/ajuste, execução simulada verificada, trilha de auditoria.

**Critérios de aceitação do MVP**

| # | Critério | Como é verificado |
|---|---|---|
| 1 | Executar localmente | README; API e frontend sobem com SQLite ou PostgreSQL |
| 2 | Autenticar um usuário | `test_auth_required_and_login_flow`, E2E |
| 3 | Cadastrar e selecionar cliente | `test_client_*`, E2E |
| 4 | Dados demonstrativos sinalizados | `test_demo_dashboard_is_flagged_and_consistent`, E2E |
| 5 | Indicadores corretos | `test_metrics.py` (cálculo à mão), E2E confere CAC e ROAS na tela |
| 6 | Solicitar análise ao Borges Core | `test_analysis_*`, E2E |
| 7 | Recomendação estruturada com evidências | `test_decision_engine.py`, E2E |
| 8 | Aprovar ou rejeitar ação simulada | `test_approve_*`, `test_reject_*`, E2E |
| 9 | Resultado no histórico | idem + histórico da campanha e auditoria |
| 10 | Testes essenciais passando | `pytest`, `ruff`, `eslint`, `next build`, `e2e/mvp.cjs` |

**Simulado nesta fase**
- Todos os dados de campanha e de vendas (gerador interno).
- A execução: altera apenas o orçamento da campanha demonstrativa no banco do Borges.

**Não existe ainda** (aparece na interface como “Fase N”, nunca como tela vazia)
- (na Fase 1) Qualquer integração real, LLM, conjuntos/anúncios, agentes 03–08, 10 e 11, agendador, relatórios,
  Creative Studio, Radar competitivo, Inteligência comercial, nível 3 de operação, etapa “mensurar/aprender”.

## Fase 2 — Inteligência de dados ✅ (validação com a API real pendente)

**Entregue**
- Conector Windsor.ai de leitura para Meta Ads e Google Ads, por cliente.
- Credenciais cifradas em repouso; conexão testada ao salvar; seleção explícita de contas por cliente.
- Hierarquia campanha → conjunto/grupo → anúncio, com detalhamento no Gestor de campanhas.
- Sincronização idempotente com histórico, estado (executando/concluída/falhou) e auditoria.
- Validação: lacunas, dados desatualizados, falhas, moeda divergente, campanhas renomeadas e
  reconciliação entre o nível da campanha e o dos anúncios.
- Ritmo de investimento do mês frente ao orçamento mensal.

**Como é verificado**
- `tests/test_windsor.py`: transporte HTTP (tentativas, erros, sigilo da chave), normalização, reconciliação.
- `tests/test_sync_flow.py`: conectar → escolher contas → sincronizar → consultar, isolamento e papéis.
- `frontend/e2e/phase2.cjs`: o mesmo fluxo no navegador.
- Todos usam um Windsor.ai falso cujas linhas reproduzem o formato real observado.

**Pendente**
- Uma sincronização completa contra a API real do Windsor.ai, com uma chave real. O formato da requisição
  já foi conferido na documentação oficial e a resposta de erro de autenticação, na API real.
- Dimensões (dispositivo, posicionamento, região, horário), GA4 e Search Console.
- Vendas confirmadas para clientes reais (CRM, Fase 5): sem elas, CAC real e ROAS confirmado ficam
  indisponíveis e as regras de eficiência não rodam.

## Fase 3 — Agentes e diagnóstico ✅

**Entregue**
- Meta Ads Specialist: anúncio gastando sem resultado (≥ 3x o custo por lead da campanha, zero leads),
  custo por lead fora da curva (≥ 1,5x a campanha) e verba pulverizada em muitos anúncios.
- Google Ads Specialist: grupo de anúncios gastando sem converter e conversões sem valor configurado.
- Borges Core: combina campanha e anúncio, não deixa os especialistas opinarem quando a campanha tem
  amostra insuficiente ou rastreamento duvidoso, deduplica pendências por campanha/regra/anúncio e
  prioriza pela participação real da entidade no investimento.
- Nova ação executável: pausar anúncio (simulada em demonstração, bloqueada em cliente real), com as
  mesmas verificações, idempotência, releitura e auditoria do ajuste de orçamento.
- Recomendações mostram campanha → conjunto/grupo → anúncio; o Gestor de campanhas mostra anúncios pausados.

- IA da Anthropic no Borges Core (opcional, desligada por padrão): interpreta a pergunta e redige a
  resposta a partir dos fatos calculados, com limite de gasto mensal, chave cifrada, reserva automática
  quando o modelo recusa, e descarte da resposta se ela citar números que não estão nos dados.

**Como é verificado:** `tests/test_ai.py` (salvaguardas e formato real da chamada pelo SDK oficial),
`e2e/ai.cjs` (contra uma Anthropic falsa), `tests/test_specialists.py` (cada regra com números controlados),
`tests/test_api_flow.py` (análise, pausa simulada, bloqueio em cliente real) e `e2e/mvp.cjs` no navegador.

**Não feito nesta fase**
- Termos de pesquisa, palavras-chave e negativas do Google (o conector ainda não lê esses relatórios).
- Dimensões (posicionamento, região, horário, dispositivo).

## Fase 4 — Competitiva, criativa e experimentos ✅

**Entregue**
- Creative Studio: biblioteca de criativos (anúncios da Meta) classificados contra a própria campanha
  (vencedor, na média, pouco volume, abaixo da média, sem resultado) e tendência de desgaste pelo CTR.
- Briefings com 3 a 5 variações (título, texto, CTA, formato, orientação visual e hipótese de teste),
  escritos pela IA quando ativa ou por um modelo com ângulos clássicos. A IA não pode citar número que não
  esteja na oferta informada; se citar, o briefing cai para o modelo.
- Experimentation Engine: teste entre anúncios da mesma campanha com problema, hipótese, variável, métrica
  principal, métricas de proteção, variação mínima a detectar e duração. Calcula o volume necessário (5% de
  significância, 80% de poder), avalia com teste z de duas proporções na taxa clique → lead, só declara
  resultado ao atingir o volume ou a duração (antes, mostra tendência), permite análise retroativa, e
  registra resultado e aprendizado na conclusão.
- Radar competitivo: concorrentes e anúncios públicos capturados manualmente (só links http/https), tempo
  no ar e resumo de ângulos, ofertas e ideias de teste pela IA, ou resumo por regras sem IA.

**Como é verificado:** `tests/test_experiment_stats.py` (fórmulas conferidas à mão),
`tests/test_growth.py` (API, isolamento, papéis, IA com preço inventado), `e2e/phase4.cjs` no navegador.

**Não feito nesta fase**
- Geração de imagens (exige um provedor pago de imagem).
- Busca automática na Biblioteca de Anúncios da Meta (exige token com identidade confirmada pela Meta).
- Teste A/B nativo da Meta (exige escrita autorizada, Fase 5); o teste entre anúncios do mesmo conjunto
  indica, mas não prova, causalidade.

## Fase 5 — Comercial e execução
CRM e vendas reais, tracking/CRO, conectores de escrita autorizados, reversão, nível 3 com limites.

## Fase 6 — Automações e aprendizado
Agendador por cliente (aqui entram Redis e fila), relatórios e PDF, alertas, medição do efeito das
decisões, memória de aprendizados com origem, data e confiabilidade.
