# Proxy SIGOR/CETESB

O frontend deve chamar a API Tree, sem acessar diretamente `mtrr.cetesb.sp.gov.br`.

## Rotas

- `POST /sigor/get-token`: valida o Firebase ID token, verifica acesso à empresa/filial, busca as credenciais SIGOR no Firestore e devolve o bearer em `objetoResposta` com `Cache-Control: no-store`.
- `POST /sigor/emitir-manifesto`: encaminha o corpo do manifesto para `salvarManifestoLote`.
- `POST /sigor/cancelar-manifesto`: encaminha o pedido para `cancelarManifesto`.
- `POST /sigor/download-manifesto/{numero}`: encaminha o download do manifesto.

As chamadas exigem `Authorization: Bearer <Firebase ID token>`. As operações posteriores ao login também enviam o bearer SIGOR em `X-Sigor-Token`. O backend encaminha o `User-Agent` do navegador ao SIGOR, limita timeouts e retorna conteúdo sem cache. Tokens são reutilizados no processo do backend por até 50 minutos; uma nova autenticação dentro do intervalo mínimo recebe `429` com `Retry-After`.

## Execução local

```powershell
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Configure `FIREBASE_KEY` com a conta de serviço autorizada antes de usar as rotas autenticadas. Não registre nem versiona essa chave, senhas SIGOR ou bearers.
