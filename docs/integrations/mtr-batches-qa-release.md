# Execução sequencial MTR — IMA/FEPAM/SEMAD — 2026-10-09

BATCH: QA-7
STATUS: BLOCKED (release/smoke); verificações locais IMPLEMENTED
REPOSITORIO/BRANCH: apis-mtr-tree/main e tree-automation/main, conforme preferência persistente da conversa. Commits pequenos por batch; sem push/deploy.
ARQUIVOS ALTERADOS QA: API main.py, services/ima.py, services/fepam.py, tests/test_mtr_query_security.py, tests/test_scheduler_query_contracts.py, este relatório; scheduler validação FEPAM, testes e relatório QA.
CONTRATOS PRESERVADOS: métodos, paths, schemas públicos de entrada e envelopes de sucesso; alterações de validação local não incluem credenciais nos erros 422. Manifestos mantêm dados operacionais; campos de autenticação ecoados são suprimidos. SINIR/FEAM/SIGOR/INEA, demais endpoints SEMAD/IMA/FEPAM e gateway não foram alterados. Mail, tracking, cron, lookback e limites de breakers mantidos.
EVIDENCIAS: payloads reais dos helpers scheduler IMA/FEPAM aceitos pelas rotas API via TestClient; fixtures sintéticas; assert CDF do caminho documentado. Consulta somente leitura de metadados de checkStatus para identificar campos; nenhum valor/ID sensível persistido.
RISCO RESIDUAL: nenhum CDF positivo real validado no ambiente atual. SEMAD-2 bloqueada por ausência de pessoaCodigo na amostra e caminho CDF não comprovado. A regra conservadora de manifesto SEMAD precisa de confirmação real. Suite global scheduler não é integralmente executável neste ambiente.
DEPLOY: NAO EXECUTADO
PROXIMA BATCH: obter evidência SEMAD, concluir integração desabilitada, autorizar smoke em staging; depois aprovar rollout por órgão.

## Situação por batch

| Batch | Status | Evidência / testes na etapa |
|---|---|---|
| IMA-1 | IMPLEMENTED | Legado confirma CPF no login; pytest API 103 passed; URL codificada, erros sanitizados. |
| IMA-2 | IMPLEMENTED | Um documento IMA da amostra contém cpf/cnpj/psw/unidade; testes scheduler MTR+client 114 passed; sem arredondamento de identificadores; seleção exclusiva não ambígua. |
| FEPAM-1 | IMPLEMENTED | Manual oficial Consulta Manifesto, página 4; fixture de request e estrutura, 2 passed. SAFE_TO_IMPLEMENT. |
| FEPAM-2 | IMPLEMENTED | dados.manifestoJSON.cdfCodigo comprovado; API 123 passed; scheduler MTR+client 128 passed; erros documentados 900/901/902/903 nunca viram semCdf. |
| SEMAD-1 | IMPLEMENTED (local) | API 171 passed; campos gettoken, Bearer único, status/JSON e validação seguros; CDF upstream PENDENTE. |
| SEMAD-2 | BLOCKED | Cinco documentos amostrados sem pessoaCodigo; pswSemad presente em quatro, sem psw genérico; CDF não comprovado. Job não criado nem agendado. |
| QA-7 | BLOCKED (release) | Testes locais concluídos, mas smoke real não autorizado e SEMAD-2 não concluída. |

## Matriz de cenários

| Cenário | IMA | FEPAM | SEMAD |
|---|---|---|---|
| Payload scheduler → API real/schema | PASS (helper real) | PASS (helper real) | BLOCKED no scheduler; schema API PASS |
| Credencial ausente/inválida → zero HTTP | PASS | PASS | PASS API; scheduler ausente |
| Código de barras inválido / identificador divergente | PASS | PASS para identidade MTR | PASS API conservador |
| HTTP401/403 isolado da empresa | PASS | PASS | PASS API; scheduler bloqueado |
| Timeout504, rede/SSL502, 5xx controlado | PASS | PASS | PASS ambas etapas |
| HTTP200 funcional/contrato inválido não vira semCdf | PASS | PASS | PASS API; sem parser CDF habilitado |
| CDF presente / ausência válida em mock | PASS | PASS fixture oficial | CDF NÃO COMPROVADO |
| Reprocessamento sem duplicar efeitos | PASS IMA com snapshots renovados | Motor compartilhado preservado e testes de efeitos | BLOCKED |
| Senha/CPF/token/URL autenticada em logs/erros HTTP | NO_EXPOSURE nos cenários testados, incluindo registros estruturados e validação422 | NO_EXPOSURE | NO_EXPOSURE |
| Jobs/crons anteriores | Snapshot dos seis jobs mantido; SEMAD ausente | Mantido | Ausente |
| Smoke real / release | NÃO EXECUTADO | NÃO EXECUTADO | BLOCKED |

## Comandos e limitações

API:
- `PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider`: 178 passed, 3 avisos de depreciação existentes. QA conjunta exige checkout scheduler irmão ou `TREE_SCHEDULER_ROOT`; ambos presentes nesta execução.
- `PYTHONPYCACHEPREFIX=/tmp/mtr-batches-api-pycache python -m compileall -q .`: FAILED em nove arquivos ._*.py preexistentes (metadados macOS, bytes nulos).
- `PYTHONPYCACHEPREFIX=/tmp/mtr-batches-api-pycache python -m compileall -q -x '(^|/)\._' .`: PASS, excluindo somente esses metadados.
- Ruff dos testes novos/helper de validação: PASS. Não declarar lint global dos serviços legados.
- `git diff --check`: PASS; revisão cumulativa limitada aos órgãos autorizados.

Scheduler:
- `PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider`: FAILED na coleta de seis módulos preexistentes: pypdf/jinja2 ausentes; import _runtime do agentic_tai incompatível. Nenhuma dependência instalada ou módulo fora do escopo corrigido.
- Suite disponível: `PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider --ignore=tests/smartdocs_advanced/test_api.py --ignore=tests/smartdocs_advanced/test_document_pipeline.py --ignore=tests/test_agentic_tai_smartdocs.py --ignore=tests/test_envio_agendado_job.py --ignore=tests/test_smartdocs_relatorio.py --ignore=tests/test_smartdocs_worker.py`: 260 passed, 3 avisos existentes.
- `PYTHONPYCACHEPREFIX=/tmp/mtr-batches-scheduler-pycache python -m compileall -q .`: PASS. Cache em /tmp preserva checkout limpo.
- Ruff mtr_cdf_check.py/seus testes e `git diff --check`: PASS.

## Evidência FEPAM oficial

https://fepam.rs.gov.br/upload/arquivos/202607/22144248-retornamanifesto.pdf
O serviço retornaManifesto mantém o manifesto em manifestoJSON e o certificado em cdfCodigo nesse objeto. O manual diferencia consulta de situação e consulta de manifesto. Não foi substituído por verificaSituacaoManifesto. Relatórios detalhados por órgão estão em docs/integrations/*-cdf-contract-validation.md.

## Rollout e rollback propostos

1. Corrigir/validar cadastros SEMAD com pessoaCodigo e senha própria comprovados; obter resposta redigida com CDF e sem CDF ou fonte oficial. Nunca derivar pessoaCodigo de unidade sem prova.
2. Concluir SEMAD-2 com integração desabilitada por padrão, sem inventar horário de cron.
3. Após autorização explícita para credenciais reais, consultar em staging uma empresa/manifesto conhecido por órgão e conferir CDF, contadores e efeitos. Sem dry-run implementado, não usar job de produção como diagnóstico.
4. Aprovar API e scheduler do órgão individualmente; ativar agenda só após prova positiva. SEMAD permanece fora do registry até cumprir gates.
5. Rollback seletivo por commit da batch e configuração/agenda do órgão, preservando os demais jobs; snapshots existentes verificam limites e crons. Sem mudanças de dados de produção a reverter nesta execução.

MATRIZ FINAL:
IMA: API_VERIFIED(local) / SCHEDULER_VERIFIED(local) / POSITIVE_CDF_NOT_VERIFIED / NOT_RELEASED
FEPAM: CONTRACT_PROVEN(documento oficial) / API_VERIFIED(local) / SCHEDULER_VERIFIED(local) / POSITIVE_CDF_NOT_VERIFIED / NOT_RELEASED
SEMAD: API_VERIFIED(local) / SCHEDULER_BLOCKED / JOB_ABSENT / POSITIVE_CDF_NOT_VERIFIED / NOT_RELEASED
REGRESSION: TESTS_PASSED no conjunto disponível; pytest global scheduler BLOCKED por ambiente.
SECRETS: NO_EXPOSURE nos logs/respostas cobertos pelos testes.
DEPLOY: NAO EXECUTADO
