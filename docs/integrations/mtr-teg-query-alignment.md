# Alinhamento de consultas ambientais ao TEG — 2026-10-09

Fluxo preservado: scheduler → apis-mtr-tree → órgãos. Não foi adicionada autenticação Firebase/KMS no scheduler ou na API. O TEG é referência somente leitura.

Escopo: IMA, FEPAM e SEMAD. SIGOR, SINIR, FEAM e INEA preservados nesta rodada.

## IMA

O scheduler envia CPF/CNPJ/senha e a unidade da credencial em unidadeGerador, usada pela lista de autenticação. O código de barras continua composto com os dados do envio. A API valida a credencial por retornaListaClasse/{login}/{senha}/{cnpj}/{unidade}, tentando CPF primeiro e CNPJ como fallback, e consulta retornaManifesto/{barcode}/{loginSelecionado}/{senha}/{cnpj}. Não há gettoken IMA nem Bearer nesse fluxo. Timeout/rede não provocam tentativas de login alternativas.

## FEPAM

O scheduler acrescenta unidade da credencial ao payload. A API valida a credencial via retornaListaEstadoFisico/{cpf}/{senha}/{cnpj}, e envia login/senha/cnp/codUnidade/manifestoJSON ao retornaManifesto. Unidade numérica em string é enviada como int em codUnidade; outros valores permanecem string, como no TEG. Objeto vazio na autenticação é rejeitado. unidade é opcional no contrato público para preservar clientes anteriores; o scheduler sempre a exige e a envia. O caminho comprovado de CDF permanece dados.manifestoJSON.cdfCodigo.

## SEMAD

O usuário definiu pessoaCodigo = envio.unidadeGerador e dispensou validação numérica desse campo. Scheduler e schema da API usam sua representação em string, exigindo presença. A composição do código de barras ainda exige seus quatro identificadores válidos e 34 dígitos. CPF/CNPJ vêm da credencial; senha vem de pswSemad ou senha normalizada, sem fallback para pswFeam. API mantém POST /api/gettoken com pessoaCodigo/pessoaCnpj/usuarioCpf/senha e POST /api/retornaManifesto/{barcode} com Bearer único, sem chave_feam.

A ativação do job SEMAD permanece pendente da comprovação do caminho CDF: nenhum cron, registry ou parser de CDF SEMAD foi inventado ou ativado nesta alteração.

## Respostas e erros

IMA e SEMAD devolvem erro funcional de manifesto como HTTP 422, incluindo o corpo operacional sanitizado em detail e preservando retornoCodigo quando informado. FEPAM mantém os status documentados por retornoCodigo (900→401, 901→403, 902→404, 903→400) e trata flags explícitas de falha como 422. Contratos desconhecidos continuam erro 502; não viram manifesto sem CDF. HTTP 401/403 é classificado antes de JSON. As respostas de consulta dos três sistemas removem campos sensíveis recursivamente. Campos operacionais, incluindo CNPJ e CDF, permanecem disponíveis. Nenhum segredo é inserido em log.

## Validação local

API: suite completa com HTTP simulado. Scheduler: suites test_mtr_cdf_check e test_mtr_client, incluindo testes conjuntos de payload scheduler→API. Cobertura adicional de fallback IMA, codUnidade FEPAM, rejeição de credencial vazia, SEMAD sem validação numérica e sanitização aninhada. Ruff dos arquivos novos e verificações críticas nos arquivos legados; compileall dos arquivos afetados; git diff --check.

Não houve smoke autenticado real, commit, push ou deploy. Testes locais não comprovam disponibilidade atual dos portais ambientais.
