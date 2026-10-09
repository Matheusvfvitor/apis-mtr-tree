BATCH: IMA-1
STATUS: IMPLEMENTED
REPOSITORIO/BRANCH: apis-mtr-tree/main
ARQUIVOS ALTERADOS: services/ima.py, main.py, tests/test_ima_manifesto.py, este relatório
CONTRATOS PRESERVADOS: POST /ima/retorna-manifesto-codigo-de-barras; cpf/cnpj/senha/unidadeGerador/codigoBarras; {sucesso, dados}; demais endpoints intactos.
TESTES: PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider: 103 passed. Compileall dos arquivos alterados, ruff no teste e git diff --check: OK. Compileall global: FAILED nos arquivos ._*.py preexistentes (metadados macOS com bytes nulos).
EVIDENCIAS: checStatusCDF/services/ima.py e checksStatusMTR/services/ima.py usam CPF como login, identificam manifesto por manifestoCodigo e extraem cdfCodigo. Apenas mocks sintéticos foram usados nos testes.
RISCO RESIDUAL: resposta positiva com CDF no ambiente atual não foi consultada. retornoCodigo desconhecido é contrato inválido, sem inferir autenticação a partir de código numérico; não se aceita código de retorno sozinho como prova de manifesto.
DEPLOY: NAO EXECUTADO
PROXIMA BATCH: IMA-2
