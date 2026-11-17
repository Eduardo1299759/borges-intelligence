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
- Uma sincronização contra a API real do Windsor.ai, com uma chave real. Até lá, o formato da requisição
  REST é uma suposição isolada em um único método.
- Dimensões (dispositivo, posicionamento, região, horário), GA4 e Search Console.
- Vendas confirmadas para clientes reais (CRM, Fase 5): sem elas, CAC real e ROAS confirmado ficam
  indisponíveis e as regras de eficiência não rodam.

## Fase 3 — Agentes e diagnóstico
Provedor de LLM atrás de interface (com controle de custo), interpretação da pergunta, especialistas
Meta e Google, diagnóstico por conjunto/anúncio/termo de pesquisa.

## Fase 4 — Competitiva e criativa
Meta Ad Library, análise de criativos, briefings, geração de imagens, motor de experimentos.

## Fase 5 — Comercial e execução
CRM e vendas reais, tracking/CRO, conectores de escrita autorizados, reversão, nível 3 com limites.

## Fase 6 — Automações e aprendizado
Agendador por cliente (aqui entram Redis e fila), relatórios e PDF, alertas, medição do efeito das
decisões, memória de aprendizados com origem, data e confiabilidade.
