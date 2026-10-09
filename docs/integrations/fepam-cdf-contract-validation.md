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
