import requests
from fastapi import HTTPException
from pydantic import BaseModel
from typing import Dict, Tuple, Optional, Union, Any
from fastapi import FastAPI, Request, HTTPException
from urllib.parse import urlparse

import json
import logging



INEA_BASE_URL = "http://mtr.inea.rj.gov.br/api"

# =========================
# Schema de entrada INEA
# =========================
class ConsultaIneaManifestoRequest(BaseModel):
    cpf: str
    senha: str
    cnpj: str
    unidadeGerador: str
    codigoBarras: str

# =========================
# Consulta LISTA INEA
# =========================
# Endpoints de consulta permitidos pelo proxy.
INEA_LIST_ENDPOINTS = {
    "retornaListaClasse",
    "retornaListaUnidade",
    "retornaListaTecnologia",
    "retornaListaEstadoFisico",
    "retornaListaResiduo",
    "retornaListaAcondicionamento",
}


class ConsultaListaIneaRequest(BaseModel):
    url: str


def validar_url_lista_inea(url: str) -> tuple[str, str]:
    """
    Valida a URL recebida do client.

    Estrutura esperada:
    https://mtr.inea.rj.gov.br/api/{endpoint}/{cpf}/{senha}/{cnpj}/{unidade}
    """

    try:
        parsed_url = urlparse(url)
    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail=f"URL do INEA inválida: {str(error)}",
        )

    if parsed_url.scheme != "https":
        raise HTTPException(
            status_code=400,
            detail="A URL do INEA deve utilizar HTTPS.",
        )

    if parsed_url.hostname != "mtr.inea.rj.gov.br":
        raise HTTPException(
            status_code=403,
            detail="Host da API INEA não autorizado.",
        )

    if parsed_url.port not in (None, 443):
        raise HTTPException(
            status_code=403,
            detail="Porta da API INEA não autorizada.",
        )

    if parsed_url.query or parsed_url.fragment:
        raise HTTPException(
            status_code=400,
            detail="A URL do INEA não pode conter query string ou fragmento.",
        )

    partes = [
        parte
        for parte in parsed_url.path.split("/")
        if parte
    ]

    # Estrutura:
    # 0: api
    # 1: endpoint
    # 2: cpf
    # 3: senha
    # 4: cnpj
    # 5: unidade
    if len(partes) != 6:
        raise HTTPException(
            status_code=400,
            detail=(
                "Estrutura da URL INEA inválida. "
                "Esperado: /api/{endpoint}/{cpf}/{senha}/{cnpj}/{unidade}"
            ),
        )

    if partes[0] != "api":
        raise HTTPException(
            status_code=400,
            detail="Prefixo da API INEA inválido.",
        )

    endpoint = partes[1]

    if endpoint not in INEA_LIST_ENDPOINTS:
        raise HTTPException(
            status_code=403,
            detail=f"Endpoint INEA não autorizado: {endpoint}",
        )

    # URL mascarada para os logs.
    partes_mascaradas = partes.copy()
    partes_mascaradas[2] = "***CPF***"
    partes_mascaradas[3] = "***SENHA***"

    url_mascarada = (
        f"{parsed_url.scheme}://"
        f"{parsed_url.hostname}/"
        f"{'/'.join(partes_mascaradas)}"
    )

    return endpoint, url_mascarada


def retorna_lista_inea(url: str) -> requests.Response:
    """
    Consulta uma das listas auxiliares da API do INEA
    e devolve a resposta HTTP original.
    """

    endpoint, url_mascarada = validar_url_lista_inea(url)

    logger.info(
        "[API INEA] Consulta de lista iniciada | "
        "endpoint=%s | url=%s",
        endpoint,
        url_mascarada,
    )

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Tree-ESG-API/1.0",
        "Connection": "close",
    }

    try:
        response_inea = requests.post(
            url=url,
            headers=headers,
            timeout=(15, 30),
            allow_redirects=True,
        )

    except requests.ConnectTimeout as error:
        logger.error(
            "[API INEA] Timeout de conexão | endpoint=%s | erro=%s",
            endpoint,
            str(error),
        )

        raise HTTPException(
            status_code=504,
            detail=(
                "Timeout ao estabelecer conexão com a API do INEA. "
                "O servidor não conseguiu acessar mtr.inea.rj.gov.br:443."
            ),
        )

    except requests.ReadTimeout as error:
        logger.error(
            "[API INEA] Timeout de resposta | endpoint=%s | erro=%s",
            endpoint,
            str(error),
        )

        raise HTTPException(
            status_code=504,
            detail="A API do INEA demorou demais para responder.",
        )

    except requests.SSLError as error:
        logger.error(
            "[API INEA] Erro SSL | endpoint=%s | erro=%s",
            endpoint,
            str(error),
        )

        raise HTTPException(
            status_code=502,
            detail=f"Erro SSL ao consultar a API do INEA: {str(error)}",
        )

    except requests.RequestException as error:
        logger.error(
            "[API INEA] Erro de comunicação | endpoint=%s | erro=%s",
            endpoint,
            str(error),
        )

        raise HTTPException(
            status_code=502,
            detail=f"Erro de comunicação com a API do INEA: {str(error)}",
        )

    logger.info(
        "[API INEA] Consulta de lista finalizada | "
        "endpoint=%s | status=%s | tamanho=%s",
        endpoint,
        response_inea.status_code,
        len(response_inea.content or b""),
    )

    return response_inea


# =========================
# Consulta Manifesto INEA
# =========================
def retorna_manifesto_inea(
    cpf: str,
    senha: str,
    cnpj: str,
    unidade_gerador: str,
    codigo_barras: str
):
    url = (
        f"{INEA_BASE_URL}/retornaManifesto/"
        f"{cpf}/{senha}/{cnpj}/{unidade_gerador}/{codigo_barras}"
    )

    try:
        response = requests.post(url, timeout=30)
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Erro de comunicação com o INEA: {str(e)}"
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="Erro ao consultar manifesto no INEA"
        )

    return response.json()

INEA_BASE = "https://mtr.inea.rj.gov.br"
LOGIN_URL = f"{INEA_BASE}/ControllerServlet"


# ----------------------------
# Utils de logging (SSE)
# ----------------------------
def sse_event(event: str, data: Any) -> str:
    """
    Envia evento SSE.
    - event: nome do evento
    - data: dict/string/list
    """
    if not isinstance(data, str):
        data = json.dumps(data, ensure_ascii=False)
    # SSE format: event: <name>\ndata: <payload>\n\n
    return f"event: {event}\ndata: {data}\n\n"


# ----------------------------
# Login (requests/session)
# ----------------------------
def login_inea_session(cnpj: str, cpf: str, senha: str, unidade_codigo: str = "", tipo: str = "J") -> requests.Session:
    """
    Faz login e devolve requests.Session autenticada (com cookies).
    """
    s = requests.Session()

    headers = {
        "Accept": "*/*",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": INEA_BASE,
        "Referer": f"{INEA_BASE}/",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/142.0.0.0 Safari/537.36"
        ),
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    # GET inicial (seta JSESSIONID muitas vezes)
    s.get(f"{INEA_BASE}/", headers=headers, timeout=30)

    payload = {
        "acao": "autenticaUsuario",
        "txtCnpj": cnpj,
        "txtSenha": senha,
        "txtUnidadeCodigo": unidade_codigo or "",
        "txtCpfUsuario": cpf,
        "tipoPessoaSociedade": tipo,
    }

    r = s.post(LOGIN_URL, data=payload, headers=headers, timeout=30)

    # tenta interpretar retorno (às vezes vem JSON)
    try:
        body = r.json()
    except Exception:
        body = r.text[:500]

    # valida cookie básico
    js = s.cookies.get("JSESSIONID") or r.cookies.get("JSESSIONID")
    if not js:
        raise RuntimeError(f"Login sem JSESSIONID. status={r.status_code} body={body}")

    # se a API do INEA voltar algo que sinalize erro: você pode reforçar aqui
    # Ex.: {"sucesso":"N"} etc. Como você não colou o payload de retorno do login, mantive leve.

    return s

logger = logging.getLogger("inea")
logger.setLevel(logging.INFO)


def salvar_manifesto_inea(url, manifesto):
    logger.info("Iniciando função salvar_manifesto_inea")

    payload = json.dumps(manifesto, ensure_ascii=False)
    logger.info(f"Payload serializado enviado ao INEA: {payload}")

    headers = {
        "Content-Type": "application/json"
    }

    logger.info(f"Headers enviados ao INEA: {headers}")
    logger.info(f"URL de destino: {url}")

    response_inea = requests.post(
        url,
        headers=headers,
        data=payload,
        timeout=60
    )

    logger.info(f"Resposta status code INEA: {response_inea.status_code}")
    logger.info(f"Resposta body INEA: {response_inea.text}")

    return response_inea


# =============
# HELPERS
# =============
