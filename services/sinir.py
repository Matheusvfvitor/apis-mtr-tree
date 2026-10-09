import json
import logging
import re
import time

import requests
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict

SINIR_LEGACY_BASE_URL = "https://admin.sinir.gov.br/apiws/rest"
SINIR_TOKEN_BASE_URL = "https://admin.sinir.gov.br/api"
SINIR_MANIFESTO_BASE_URL = "https://admin.sinir.gov.br/api"
logger = logging.getLogger("sinir")

print("[SINIR DEBUG] MODULE LOADED")
print(f"[SINIR DEBUG] SINIR_TOKEN_BASE_URL={SINIR_TOKEN_BASE_URL}")
print(f"[SINIR DEBUG] SINIR_MANIFESTO_BASE_URL={SINIR_MANIFESTO_BASE_URL}")


def debug_token(label: str, token: str | None) -> None:
    token = str(token or "").strip()
    if not token:
        print(f"[SINIR DEBUG] {label}: EMPTY")
        return

    has_bearer = token.lower().startswith("bearer ")
    clean = token[7:] if has_bearer else token
    masked = f"{clean[:4]}...{clean[-4:]}" if len(clean) > 8 else "***"
    print(
        f"[SINIR DEBUG] {label}: "
        f"present=True has_bearer={has_bearer} "
        f"length={len(token)} value={masked}"
    )


def _repr_erro_seguro(error: Exception, *secrets: str) -> str:
    return _texto_seguro(repr(error), *secrets)


def _texto_seguro(text: str, *secrets: str) -> str:
    safe_text = str(text)
    for secret in sorted((str(value or "").strip() for value in secrets), key=len, reverse=True):
        if secret:
            safe_text = safe_text.replace(secret, "<REDACTED>")
            without_bearer = re.sub(r"(?i)^bearer\s+", "", secret)
            if without_bearer:
                safe_text = safe_text.replace(without_bearer, "<REDACTED>")
    return re.sub(r"(?i)(Bearer\s+)[^'\"\s,}]+", r"\1<REDACTED>", safe_text)


def _content_length(response) -> int:
    content = getattr(response, "content", b"")
    return len(content) if isinstance(content, (bytes, bytearray, str)) else 0


def _mascarar_manifesto_sinir(manifesto_numero: str) -> str:
    numero = str(manifesto_numero or "")
    return f"***{numero[-4:]}" if numero else "***"

# =========================
# Schema de entrada SINIR Busca Modelo
# =========================
class ConsultaSinirModeloRequest(BaseModel):
    cpfCnpj: str
    senha: str
    parCodigo: int

# =========================
# Schema de entrada SINIR
# =========================
class ConsultaSinirManifestoRequest(BaseModel):
    token: str
    manifestoNumero: str
    model_config = ConfigDict(extra="forbid")


# =========================
# Passo 1 - Get Token SINIR
# =========================
def gerar_token_sinir(cpf_cnpj: str, senha: str, unidade: str) -> str:
    url = f"{SINIR_LEGACY_BASE_URL}/gettoken"

    payload = {
        "cpfCnpj": cpf_cnpj,
        "senha": senha,
        "unidade": unidade
    }

    headers = {
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Erro de comunicação com o SINIR (token): {str(e)}"
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="Erro ao gerar token no SINIR"
        )

    data = response.json()

    if data.get("erro") is True or "objetoResposta" not in data:
        raise HTTPException(
            status_code=401,
            detail=f"Falha na autenticação SINIR: {data}"
        )

    # objetoResposta já vem como: "Bearer xxxxx"
    return data["objetoResposta"]

# ==================================================
# LOGIN NÃO OFICIAL
# ==================================================

def login_nao_oficial_sinir(login: str = "04304532642", senha: str = "Sinir@2601", parCodigo: int = 490976):
    
    print('login sinir api não oficial...')

    try:
        url = "https://mtr.sinir.gov.br/api/mtr/login"
        
        payload = json.dumps({
            "parCodigo": parCodigo,
            "login": login,
            "senha": senha
        })
        
        headers = {'Content-Type': 'application/json'}

        response = requests.request("POST", url, headers=headers, data=payload)
        
        response = response.json()
        objetoResposta = response.get('objetoResposta')
        token = objetoResposta.get('token')
        
        return token
    
    except requests.RequestException as e:
        
        raise HTTPException(
            status_code=502,
            detail=f"Erro de comunicação com o SIGOR (manifesto): {str(e)}"
        )
    
# =========================
# Passo 2 - Retorna Manifesto
# =========================
def normalizar_bearer(token: str) -> str:
    token = str(token or "").strip()
    if not token:
        raise HTTPException(
            status_code=400,
            detail="Token SINIR não informado.",
        )
    if token.lower().startswith("bearer "):
        return token
    return f"Bearer {token}"


def gerar_token_dinamico_sinir(token_ws: str) -> str:
    print('log-manal [token_ws]', token_ws)
    url = f"{SINIR_TOKEN_BASE_URL}/token"
    started_at = time.perf_counter()
    print("\n[SINIR DEBUG] ===== TOKEN EXCHANGE START =====")
    print(f"[SINIR DEBUG] token_url={url}")
    debug_token("token_ws_raw", token_ws)
    authorization = normalizar_bearer(token_ws)
    print('log-manual [authorization]', authorization)
    debug_token("authorization_after_normalize", authorization)
    headers = {"Authorization": authorization}

    logger.info("step=token_exchange.start system=SINIR token_present=True")
    print("[SINIR DEBUG] executing POST token")
    print("[SINIR DEBUG] body=''")
    print("[SINIR DEBUG] timeout=30")
    print("[SINIR DEBUG] headers={}", headers)
    print("[SINIR DEBUG] url={}", url)

    try:
        response = requests.request("POST", url, headers=headers, data='')
        print("[SINIR DEBUG] token POST returned")
        print('log-manual [response]', response)
    except Exception as error:
        print("[SINIR DEBUG] TOKEN POST EXCEPTION")
        print(f"[SINIR DEBUG] type={type(error).__name__}")
        print(
            f"[SINIR DEBUG] repr={_repr_erro_seguro(error, token_ws, authorization)}"
        )
        if isinstance(error, requests.Timeout):
            logger.error(
                "step=token_exchange.timeout system=SINIR elapsed_ms=%.0f",
                (time.perf_counter() - started_at) * 1000,
            )
            raise HTTPException(
                status_code=504,
                detail="Timeout na troca do token SINIR.",
            )
        if isinstance(error, requests.RequestException):
            logger.error(
                "step=token_exchange.transport_error system=SINIR error_type=%s elapsed_ms=%.0f",
                type(error).__name__,
                (time.perf_counter() - started_at) * 1000,
            )
            raise HTTPException(
                status_code=502,
                detail="Erro de comunicação na troca do token SINIR.",
            )
        raise

    print("[SINIR DEBUG] token POST returned")
    print(f"[SINIR DEBUG] status={response.status_code}")
    content_type = _texto_seguro(
        str(response.headers.get("Content-Type")), token_ws, authorization
    )
    print(f"[SINIR DEBUG] content_type={content_type}")
    print(f"[SINIR DEBUG] content_length={_content_length(response)}")

    elapsed_ms = (time.perf_counter() - started_at) * 1000
    if response.status_code != 200:
        logger.error(
            "step=token_exchange.response system=SINIR status=%s elapsed_ms=%.0f",
            response.status_code,
            elapsed_ms,
        )
        raise HTTPException(
            status_code=response.status_code,
            detail="Erro ao trocar o token SINIR.",
        )

    try:
        data = response.json()
    except ValueError as error:
        print("[SINIR DEBUG] token response JSON EXCEPTION")
        print(f"[SINIR DEBUG] type={type(error).__name__}")
        logger.error(
            "step=token_exchange.response system=SINIR status=%s json_type=invalid keys=[] elapsed_ms=%.0f",
            response.status_code,
            elapsed_ms,
        )
        raise HTTPException(
            status_code=502,
            detail="Resposta inválida na troca do token SINIR.",
        )

    print("[SINIR DEBUG] token response parsed")
    json_type = type(data).__name__
    keys = sorted(str(key) for key in data) if isinstance(data, dict) else []
    print(f"[SINIR DEBUG] response_keys={keys if isinstance(data, dict) else 'not-dict'}")
    print(f"[SINIR DEBUG] erro={data.get('erro') if isinstance(data, dict) else None}")
    mensagem = data.get("mensagem") if isinstance(data, dict) else None
    token_dinamico = data.get("objetoResposta") if isinstance(data, dict) else None
    print(
        f"[SINIR DEBUG] mensagem={_texto_seguro(str(mensagem), token_ws, authorization, token_dinamico)[:200]}"
    )
    logger.info(
        "step=token_exchange.response system=SINIR status=%s json_type=%s keys=%s elapsed_ms=%.0f",
        response.status_code,
        json_type,
        keys,
        elapsed_ms,
    )

    debug_token("token_dinamico_from_objetoResposta", token_dinamico)
    if (
        isinstance(data, dict)
        and data.get("erro") is not True
        and isinstance(token_dinamico, str)
        and token_dinamico.strip()
    ):
        token_dinamico = token_dinamico.strip()
        print("[SINIR DEBUG] token exchange success")
        debug_token("token_dinamico_return", token_dinamico)
        print("[SINIR DEBUG] ===== TOKEN EXCHANGE END =====\n")
        return token_dinamico

    raise HTTPException(
        status_code=502,
        detail="Token dinâmico SINIR não retornado.",
    )


def retorna_manifesto_sinir(
    token_dinamico: str,
    manifesto_numero: str
):
    url = f"{SINIR_MANIFESTO_BASE_URL}/retornaManifesto/{manifesto_numero}"
    manifesto_log = _mascarar_manifesto_sinir(manifesto_numero)
    started_at = time.perf_counter()
    print("\n[SINIR DEBUG] ===== MANIFEST REQUEST START =====")
    print(f"[SINIR DEBUG] manifesto_url={url}")
    print(f"[SINIR DEBUG] manifesto_numero={manifesto_numero}")
    debug_token("token_dinamico_received", token_dinamico)
    authorization = normalizar_bearer(token_dinamico)
    debug_token("manifest_authorization", authorization)

    headers = {
        "Authorization": authorization
    }
    
    print(authorization)

    logger.info(
        "step=manifesto_request.start system=SINIR manifesto=%s token_present=%s",
        manifesto_log,
        bool(authorization),
    )
    print("[SINIR DEBUG] executing GET manifesto")

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=30
        )
    except Exception as error:
        print("[SINIR DEBUG] MANIFEST GET EXCEPTION")
        print(f"[SINIR DEBUG] type={type(error).__name__}")
        print(
            f"[SINIR DEBUG] repr={_repr_erro_seguro(error, token_dinamico, authorization)}"
        )
        if isinstance(error, requests.Timeout):
            logger.error(
                "step=manifesto_request.timeout system=SINIR manifesto=%s elapsed_ms=%.0f",
                manifesto_log,
                (time.perf_counter() - started_at) * 1000,
            )
            raise HTTPException(
                status_code=504,
                detail="Timeout na comunicação com o SINIR (manifesto).",
            )
        if isinstance(error, requests.RequestException):
            logger.error(
                "step=manifesto_request.transport_error system=SINIR manifesto=%s error_type=%s elapsed_ms=%.0f",
                manifesto_log,
                type(error).__name__,
                (time.perf_counter() - started_at) * 1000,
            )
            raise HTTPException(
                status_code=502,
                detail="Erro de comunicação com o SINIR (manifesto).",
            )
        raise

    print("[SINIR DEBUG] manifesto GET returned")
    print(f"[SINIR DEBUG] status={response.status_code}")
    content_type = _texto_seguro(
        str(response.headers.get("Content-Type")), token_dinamico, authorization
    )
    print(f"[SINIR DEBUG] content_type={content_type}")
    print(f"[SINIR DEBUG] content_length={_content_length(response)}")

    elapsed_ms = (time.perf_counter() - started_at) * 1000
    logger.info(
        "step=manifesto_request.upstream_response system=SINIR manifesto=%s status_code=%s elapsed_ms=%.0f",
        manifesto_log,
        response.status_code,
        elapsed_ms,
    )

    if response.status_code != 200:
        logger.error(
            "step=manifesto_request.upstream_error system=SINIR manifesto=%s status_code=%s elapsed_ms=%.0f",
            manifesto_log,
            response.status_code,
            elapsed_ms,
        )
        raise HTTPException(
            status_code=response.status_code,
            detail="Erro ao consultar manifesto no SINIR"
        )

    try:
        manifesto = response.json()
    except Exception as error:
        print("[SINIR DEBUG] manifesto JSON EXCEPTION")
        print(f"[SINIR DEBUG] type={type(error).__name__}")
        raise

    print("[SINIR DEBUG] manifesto JSON parsed")
    if isinstance(manifesto, dict):
        objeto = manifesto.get("objetoResposta")
        print(f"[SINIR DEBUG] root_keys={list(manifesto.keys())}")
        safe_erro = _texto_seguro(
            str(manifesto.get("erro")), token_dinamico, authorization
        )
        print(f"[SINIR DEBUG] erro={safe_erro}")
        if isinstance(objeto, dict):
            man_numero = _texto_seguro(
                str(objeto.get("manNumero")), token_dinamico, authorization
            )
            cdf_numero = _texto_seguro(
                str(objeto.get("cdfNumero")), token_dinamico, authorization
            )
            print(f"[SINIR DEBUG] manNumero={man_numero}")
            print(f"[SINIR DEBUG] cdfNumero={cdf_numero}")
            situacao = objeto.get("situacaoManifesto")
            descricao = situacao.get("simDescricao") if isinstance(situacao, dict) else None
            safe_descricao = _texto_seguro(
                str(descricao), token_dinamico, authorization
            )
            print(f"[SINIR DEBUG] situacao={safe_descricao}")

    logger.info(
        "step=manifesto_request.success system=SINIR manifesto=%s elapsed_ms=%.0f",
        manifesto_log,
        elapsed_ms,
    )
    print("[SINIR DEBUG] ===== MANIFEST REQUEST END =====\n")
    return manifesto

# ==================================================
# Retorna Dados Transportador
# ==================================================

def retorna_dados_transportador_sinir(cnpj):
    print('\nretornando dados do transportador')

    token = login_nao_oficial_sinir()
    url = f"https://mtr.sinir.gov.br/api/mtr/pesquisaParceiro/5/{cnpj}"

    payload = {}
    headers = {
    'Authorization': f'Bearer {token}'
    }

    response = requests.request("GET", url, headers=headers, data=payload)
    print(response.text)
    return response.text

# ==================================================
# Retorna Dados Destino
# ==================================================

def retorna_dados_destino_sinir(cnpj):
    print('\nretornando dados do destino')

    token = login_nao_oficial_sinir()

    url = f"https://mtr.sinir.gov.br/api/mtr/pesquisaParceiro/9/{cnpj}"

    payload = {}
    headers = {
    'Authorization': f'Bearer {token}'
    }

    response = requests.request("GET", url, headers=headers, data=payload)
    print(response.text)
    return response.text

# ==================================================
# Retorna Dados Armazenador
# ==================================================

def retorna_dados_armazenador_sinir(cnpj):
    
    print('\n... retornando dados do armazenador')
    token = login_nao_oficial_sinir()

    url = f"https://mtr.sinir.gov.br/api/mtr/pesquisaParceiro/10/{cnpj}"

    payload = {}
    headers = {
    'Authorization': f'Bearer {token}'
    }

    response = requests.request("GET", url, headers=headers, data=payload)
    print(response.text)
    return response.text

#retorna_dados_armazenador('50891995000104')
#retorna_dados_transportador('39228967000160')
#retorna_dados_destino('50891995000104')



# ==================================================
# BUSCA MODELOS 
# ==================================================  
def busca_modelos_sinir(login: str = "04304532642", senha: str = "Sinir@2601", parCodigo: int = 490976):
    print('\n... buscando modelos')

    token = login_nao_oficial_sinir()
    
    print('token:', token)

    url = f"https://mtr.sinir.gov.br/api/mtr/manifestoModelo/{parCodigo}"

    payload = {}
    headers = {
    'Authorization': f'Bearer {token}'
    }

    response = requests.request("GET", url, headers=headers, data=payload)
    print(response.text)
    return response.text
