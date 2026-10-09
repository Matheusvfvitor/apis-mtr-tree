BATCH: SEMAD-1
STATUS: IMPLEMENTED (guardas locais e contrato da rota); CDF upstream PENDENTE
REPOSITORIO/BRANCH: apis-mtr-tree/main
ARQUIVOS ALTERADOS: services/semad.py, main.py, services/mtr_query_validation.py, tests/test_semad_manifesto.py, este relatório
CONTRATOS PRESERVADOS: cinco campos e envelope {sucesso, orgao, dados}; gettoken e retornaManifesto nos endereços atuais; timeout 30; endpoints parceiros/download/escrita e gateway intactos.
CORREÇÃO: pessoaCodigo inteiro válido; campos obrigatórios e barcode validados antes do token; status/timeout/JSON controlados; token exige retornoCodigo int zero e string preenchida; Bearer único. Logs seguros por etapa e erros 422 da rota sem input sensível. Guardas de manifesto exigem objeto identificado e rejeitam contrato desconhecido, sem inferir ausência de CDF.
TESTES: pytest API completo: 171 passed. Ruff nos testes/helper, compileall dos fontes tocados e git diff --check: OK. Compileall global continua limitado pelos ._*.py preexistentes.
EVIDÊNCIA: contrato de token já implementado e gateway docs/SEMAD.md + adapter SEMAD; legado checksStatusMTR/services/semad.py confirma endpoint e leitura de manifesto para status. Fixtures de manifesto são sintéticas, não prova de retorno real. Caminho CDF: NAO COMPROVADO. Semântica de códigos funcionais de manifesto: PENDENTE; rejeitados de forma controlada, sem mapear códigos desconhecidos para autenticação.
RISCO RESIDUAL: guardas conservadoras de identidade requerem smoke autorizado com manifesto real antes de liberar automação. Nenhum teste sintético comprova CDF upstream.
DEPLOY: NAO EXECUTADO
PROXIMA BATCH: SEMAD-2 (gate de credenciais/CDF)
