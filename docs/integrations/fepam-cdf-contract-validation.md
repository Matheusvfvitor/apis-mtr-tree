BATCH: FEPAM-1
STATUS: IMPLEMENTED
REPOSITORIO/BRANCH: apis-mtr-tree/main
ARQUIVOS ALTERADOS: tests/test_fepam_manifesto.py; este relatório. Nenhuma alteração funcional.
CONTRATOS PRESERVADOS: endpoint, request e envelope atuais.
EVIDÊNCIA: documento oficial FEPAM, Manual de Integração Web Service — Consulta Manifesto, página 4:
https://fepam.rs.gov.br/upload/arquivos/202607/22144248-retornamanifesto.pdf

Endpoint testado: retornaManifesto
Execução: mock + inspeção documental oficial; sem chamadas com credenciais reais
Caso com CDF: HTTP200 simulado; root keys [manifestoJSON]; manifesto identificado por manifestoJSON.manifestoCodigo; CDF path manifestoJSON.cdfCodigo.
Caso sem CDF: fixture sintética cdfCodigo=null em manifesto identificado, a validar no patch; não representa execução real positiva/negativa.
Caso erro funcional: retornoCodigo=900, sem manifesto válido.
Semântica retornoCodigo: COMPROVADA no documento: 0 sucesso, 900 credenciais inválidas; 901/902/903 são falhas de consulta. Não atribuir outros códigos por inferência.
Conclusão para FEPAM-2: SAFE_TO_IMPLEMENT (Caso B, fonte oficial confiável).

DIAGNÓSTICO: API atual envia request compatível (codUnidade é opcional); retorna JSON sem validar sucesso. Scheduler procura CDF apenas na raiz e não alcança manifestoJSON.cdfCodigo. Legado verificaSituacaoManifesto trata STATUS e não substitui esta consulta. Gateway atual usa retornaManifesto, sem comprovar outro caminho de CDF. A documentação mostra eco de login/senha na raiz: suprimir esses campos sensíveis preservando o manifesto e envelope.
TESTES: teste de request exato e fixture negativa; validar com suite antes do commit.
RISCO RESIDUAL: contrato documentado, não foi realizado smoke positivo no ambiente atual.
DEPLOY: NAO EXECUTADO
PROXIMA BATCH: FEPAM-2

BATCH: FEPAM-2
STATUS: IMPLEMENTED
REPOSITORIO/BRANCH: apis-mtr-tree/main + tree-automation/main
ARQUIVOS ALTERADOS: API services/fepam.py e tests/test_fepam_manifesto.py; scheduler mtr_cdf_check.py e seus testes; relatórios nos dois repos.
CONTRATOS PRESERVADOS: endpoint retornaManifesto, request e envelope {sucesso, orgao, dados}; manifestoJSON mantido. Apenas campos de autenticação ecoados na raiz foram suprimidos por segurança.
TESTES: API pytest completo 123 passed; scheduler test_mtr_cdf_check.py + test_mtr_client.py 128 passed. Compilação dos fontes alterados e git diff --check OK. Ruff dos testes e fontes scheduler OK. Limitações globais de compileall/pytest já descritas em IMA-1/2.
EVIDENCIAS: Caso B comprovado pela página 4 do manual oficial acima. Scheduler passa a extrair apenas dados.manifestoJSON.cdfCodigo; valida identidade do MTR e retornoCodigo=0. Erros funcionais conhecidos não viram semCdf. API mapeia códigos documentados 900/901/902/903 a 401/403/404/400, respectivamente; códigos desconhecidos e contratos malformados a 502.
RISCO RESIDUAL: manual oficial e mocks, sem smoke positivo real. Testes nulos não substituem confirmação operacional de ausência de CDF.
DEPLOY: NAO EXECUTADO
PROXIMA BATCH: SEMAD-1
