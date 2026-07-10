import requests
from fastapi import HTTPException
from pydantic import BaseModel
from typing import Dict, Tuple, Optional, Union, Any
from fastapi import FastAPI, Request, HTTPException, APIRouter, Response
from urllib.parse import urlparse
import os

import json
import logging

router = APIRouter(
    prefix="/inea",
    tags=["INEA"],
)

# ==========================================================
# Configuração do workaround da API INEA
# ==========================================================

INEA_WORKAROUND_ENABLED = (
    os.getenv("INEA_WORKAROUND_ENABLED", "false")
    .strip()
    .lower()
    in {"true", "1", "yes", "on"}
)

INEA_RELAY_KEY = os.getenv(
    "INEA_RELAY_KEY",
    "",
).strip()

INEA_ALLOWED_HOSTS = {
    "mtr.inea.rj.gov.br",
}

INEA_RELAY_URL = (
    os.getenv("INEA_RELAY_URL", "")
    .strip()
    .rstrip("/")
)



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


class DownloadManifestoIneaRequest(BaseModel):
    url: str

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

def validar_url_download_manifesto_inea(
    url: str,
) -> tuple[str, str]:
    """
    Valida exclusivamente a URL original do INEA.

    Estrutura esperada:
    /api/buscaPdfManifestoPorCodigoBarras/
    {cpf}/{senha}/{cnpj}/{unidade}/{codigoDeBarras}
    """

    try:
        parsed_url = urlparse(url)
        parsed_port = parsed_url.port

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=f"URL ou porta inválida: {str(error)}",
        )

    if parsed_url.scheme.lower() != "https":
        raise HTTPException(
            status_code=400,
            detail="A URL do INEA deve utilizar HTTPS.",
        )

    hostname = (parsed_url.hostname or "").strip().lower()

    if hostname not in INEA_ALLOWED_HOSTS:
        logger.warning(
            "[API INEA] Host recusado na validação | "
            "host_recebido=%s | hosts_permitidos=%s",
            hostname,
            sorted(INEA_ALLOWED_HOSTS),
        )

        raise HTTPException(
            status_code=403,
            detail="Host da API INEA não autorizado.",
        )

    if parsed_port not in (None, 443):
        raise HTTPException(
            status_code=403,
            detail="Porta da API INEA não autorizada.",
        )

    if parsed_url.username or parsed_url.password:
        raise HTTPException(
            status_code=400,
            detail="A URL não pode conter credenciais no host.",
        )

    if parsed_url.query or parsed_url.fragment:
        raise HTTPException(
            status_code=400,
            detail="A URL não pode conter query string ou fragmento.",
        )

    partes = [
        parte
        for parte in parsed_url.path.split("/")
        if parte
    ]

    if len(partes) != 7:
        raise HTTPException(
            status_code=400,
            detail=(
                "Estrutura inválida. Esperado: "
                "/api/buscaPdfManifestoPorCodigoBarras/"
                "{cpf}/{senha}/{cnpj}/{unidade}/{codigoDeBarras}"
            ),
        )

    if partes[0] != "api":
        raise HTTPException(
            status_code=400,
            detail="Prefixo da API INEA inválido.",
        )

    if partes[1] != "buscaPdfManifestoPorCodigoBarras":
        raise HTTPException(
            status_code=403,
            detail=f"Endpoint não autorizado: {partes[1]}",
        )

    cpf = partes[2]
    cnpj = partes[4]
    unidade = partes[5]
    codigo_barras = partes[6]

    if not cpf.isdigit() or len(cpf) != 11:
        raise HTTPException(
            status_code=400,
            detail="CPF de acesso inválido.",
        )

    if not cnpj.isdigit() or len(cnpj) not in (11, 14):
        raise HTTPException(
            status_code=400,
            detail="CNPJ ou CPF da unidade inválido.",
        )

    if not unidade.isdigit():
        raise HTTPException(
            status_code=400,
            detail="Código da unidade inválido.",
        )

    if not codigo_barras.isdigit():
        raise HTTPException(
            status_code=400,
            detail="Código de barras inválido.",
        )

    partes_mascaradas = partes.copy()
    partes_mascaradas[2] = "***CPF***"
    partes_mascaradas[3] = "***SENHA***"

    url_mascarada = (
        f"https://{hostname}/"
        f"{'/'.join(partes_mascaradas)}"
    )

    return codigo_barras, url_mascarada

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

def validar_url_salvar_manifesto_inea(
    url: str,
) -> tuple[str, str]:
    """
    Valida a URL do endpoint de salvamento de manifesto do INEA.

    Estrutura esperada:
    /api/salvarManifesto/{cpf}/{senha}/{cnpj}/{unidade}
    """

    try:
        parsed_url = urlparse(url)
        parsed_port = parsed_url.port

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=f"URL ou porta inválida: {str(error)}",
        )

    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail=f"URL inválida: {str(error)}",
        )

    if parsed_url.scheme.lower() != "https":
        raise HTTPException(
            status_code=400,
            detail="A URL do INEA deve utilizar HTTPS.",
        )

    hostname = (parsed_url.hostname or "").strip().lower()

    if hostname != "mtr.inea.rj.gov.br":
        raise HTTPException(
            status_code=403,
            detail="Host da API INEA não autorizado.",
        )

    if parsed_port not in (None, 443):
        raise HTTPException(
            status_code=403,
            detail="Porta da API INEA não autorizada.",
        )

    if parsed_url.username or parsed_url.password:
        raise HTTPException(
            status_code=400,
            detail="A URL não pode conter credenciais no host.",
        )

    if parsed_url.query or parsed_url.fragment:
        raise HTTPException(
            status_code=400,
            detail="A URL não pode conter query string ou fragmento.",
        )

    partes = [
        parte
        for parte in parsed_url.path.split("/")
        if parte
    ]

    # 0: api
    # 1: salvarManifesto
    # 2: cpf
    # 3: senha
    # 4: cnpj
    # 5: unidade
    if len(partes) != 6:
        raise HTTPException(
            status_code=400,
            detail=(
                "Estrutura da URL inválida. Esperado: "
                "/api/salvarManifesto/"
                "{cpf}/{senha}/{cnpj}/{unidade}"
            ),
        )

    if partes[0] != "api":
        raise HTTPException(
            status_code=400,
            detail="Prefixo da API INEA inválido.",
        )

    endpoint = partes[1]

    if endpoint != "salvarManifesto":
        raise HTTPException(
            status_code=403,
            detail=f"Endpoint não autorizado: {endpoint}",
        )

    cpf = partes[2]
    cnpj = partes[4]
    unidade = partes[5]

    if not cpf.isdigit() or len(cpf) != 11:
        raise HTTPException(
            status_code=400,
            detail="CPF de acesso inválido.",
        )

    if not cnpj.isdigit() or len(cnpj) not in (11, 14):
        raise HTTPException(
            status_code=400,
            detail="CNPJ ou CPF da unidade inválido.",
        )

    if not unidade.isdigit():
        raise HTTPException(
            status_code=400,
            detail="Código da unidade inválido.",
        )

    partes_mascaradas = partes.copy()
    partes_mascaradas[2] = "***CPF***"
    partes_mascaradas[3] = "***SENHA***"

    url_mascarada = (
        f"https://{hostname}/"
        f"{'/'.join(partes_mascaradas)}"
    )

    return endpoint, url_mascarada

def retorna_lista_inea(url: str) -> requests.Response:
    """
    Consulta uma das listas auxiliares da API do INEA.

    Com INEA_WORKAROUND_ENABLED=false:
        API Tree -> API INEA

    Com INEA_WORKAROUND_ENABLED=true:
        API Tree -> Cloudflare Tunnel -> Relay local -> API INEA

    A resposta HTTP recebida é devolvida integralmente para a rota.
    """

    endpoint, url_mascarada = validar_url_lista_inea(url)

    headers_inea = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Tree-ESG-API/1.0",
        "Connection": "close",
    }

    try:
        # ======================================================
        # WORKAROUND: encaminha pelo relay local
        # ======================================================
        if INEA_WORKAROUND_ENABLED:
            if not INEA_RELAY_URL:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Workaround INEA habilitado, mas a variável "
                        "INEA_RELAY_URL não está configurada."
                    ),
                )

            if not INEA_RELAY_KEY:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Workaround INEA habilitado, mas a variável "
                        "INEA_RELAY_KEY não está configurada."
                    ),
                )

            relay_endpoint = (
                f"{INEA_RELAY_URL}/inea/retornaListaInea"
            )

            logger.warning(
                "[API INEA] Workaround habilitado | "
                "endpoint=%s | url=%s | relay=%s",
                endpoint,
                url_mascarada,
                INEA_RELAY_URL,
            )

            response_inea = requests.post(
                url=relay_endpoint,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-Tree-Relay-Key": INEA_RELAY_KEY,
                    "User-Agent": "Tree-ESG-API/1.0",
                },
                json={
                    "url": url,
                },
                timeout=(15, 60),
                allow_redirects=True,
            )

        # ======================================================
        # FLUXO NORMAL: consulta diretamente o INEA
        # ======================================================
        else:
            logger.info(
                "[API INEA] Consulta direta iniciada | "
                "endpoint=%s | url=%s",
                endpoint,
                url_mascarada,
            )

            response_inea = requests.post(
                url=url,
                headers=headers_inea,
                timeout=(15, 30),
                allow_redirects=True,
            )

    except HTTPException:
        raise

    except requests.ConnectTimeout as error:
        destino = (
            "relay local"
            if INEA_WORKAROUND_ENABLED
            else "API do INEA"
        )

        logger.error(
            "[API INEA] Timeout de conexão | "
            "destino=%s | endpoint=%s | erro=%s",
            destino,
            endpoint,
            str(error),
        )

        raise HTTPException(
            status_code=504,
            detail=f"Timeout ao estabelecer conexão com o {destino}.",
        )

    except requests.ReadTimeout as error:
        destino = (
            "relay local"
            if INEA_WORKAROUND_ENABLED
            else "API do INEA"
        )

        logger.error(
            "[API INEA] Timeout de resposta | "
            "destino=%s | endpoint=%s | erro=%s",
            destino,
            endpoint,
            str(error),
        )

        raise HTTPException(
            status_code=504,
            detail=f"O {destino} demorou demais para responder.",
        )

    except requests.SSLError as error:
        destino = (
            "relay local"
            if INEA_WORKAROUND_ENABLED
            else "API do INEA"
        )

        logger.error(
            "[API INEA] Erro SSL | "
            "destino=%s | endpoint=%s | erro=%s",
            destino,
            endpoint,
            str(error),
        )

        raise HTTPException(
            status_code=502,
            detail=f"Erro SSL ao consultar o {destino}: {str(error)}",
        )

    except requests.RequestException as error:
        destino = (
            "relay local"
            if INEA_WORKAROUND_ENABLED
            else "API do INEA"
        )

        logger.error(
            "[API INEA] Erro de comunicação | "
            "destino=%s | endpoint=%s | erro=%s",
            destino,
            endpoint,
            str(error),
        )

        raise HTTPException(
            status_code=502,
            detail=f"Erro de comunicação com o {destino}: {str(error)}",
        )

    modo = (
        "relay-local"
        if INEA_WORKAROUND_ENABLED
        else "direto"
    )

    logger.info(
        "[API INEA] Consulta finalizada | "
        "modo=%s | endpoint=%s | status=%s | tamanho=%s",
        modo,
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

def salvar_manifesto_inea(
    url: str,
    manifesto: dict,
) -> requests.Response:
    """
    Salva um manifesto no INEA.

    Com INEA_WORKAROUND_ENABLED=true:
        API Tree -> Cloudflare Tunnel -> Relay local -> INEA

    Com INEA_WORKAROUND_ENABLED=false:
        API Tree -> INEA diretamente
    """

    endpoint, url_mascarada = validar_url_salvar_manifesto_inea(url)

    modo = (
        "relay-local"
        if INEA_WORKAROUND_ENABLED
        else "direto"
    )

    destino_url = ""

    try:
        payload_inea = json.dumps(
            manifesto,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

    except (TypeError, ValueError) as error:
        logger.error(
            "[API INEA] Manifesto inválido para serialização | erro=%s",
            str(error),
        )

        raise HTTPException(
            status_code=400,
            detail=f"Manifesto inválido para serialização JSON: {str(error)}",
        )

    logger.info(
        "[API INEA] Salvamento de manifesto iniciado | "
        "modo=%s | endpoint=%s | url=%s | tamanho_payload=%s",
        modo,
        endpoint,
        url_mascarada,
        len(payload_inea),
    )

    # Evita registrar todo o manifesto, pois o objeto pode conter
    # informações pessoais ou operacionais sensíveis.
    logger.info(
        "[API INEA] Campos do manifesto | campos=%s",
        sorted(manifesto.keys()),
    )

    try:
        # ======================================================
        # WORKAROUND: API Tree -> relay local -> INEA
        # ======================================================
        if INEA_WORKAROUND_ENABLED:
            if not INEA_RELAY_URL:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Workaround INEA habilitado, mas "
                        "INEA_RELAY_URL não está configurada."
                    ),
                )

            if not INEA_RELAY_KEY:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Workaround INEA habilitado, mas "
                        "INEA_RELAY_KEY não está configurada."
                    ),
                )

            destino_url = (
                f"{INEA_RELAY_URL.rstrip('/')}"
                "/inea/salvarManifesto"
            )

            payload_relay = json.dumps(
                {
                    "url": url,
                    "manifesto": manifesto,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")

            logger.warning(
                "[API INEA] Salvamento utilizando workaround | "
                "endpoint=%s | destino=%s | tamanho_payload=%s",
                endpoint,
                destino_url,
                len(payload_relay),
            )

            response_inea = requests.post(
                url=destino_url,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Accept": "application/json, text/plain, */*",
                    "X-Tree-Relay-Key": INEA_RELAY_KEY,
                    "User-Agent": "Tree-ESG-API/1.0",
                    "Connection": "close",
                },
                data=payload_relay,
                timeout=(20, 120),
                allow_redirects=False,
            )

        # ======================================================
        # FLUXO NORMAL: API Tree -> INEA
        # ======================================================
        else:
            destino_url = url

            logger.info(
                "[API INEA] Salvamento direto no INEA | "
                "endpoint=%s | url=%s",
                endpoint,
                url_mascarada,
            )

            response_inea = requests.post(
                url=destino_url,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Accept": "application/json, text/plain, */*",
                    "User-Agent": "Tree-ESG-API/1.0",
                    "Connection": "close",
                },
                data=payload_inea,
                timeout=(15, 90),
                allow_redirects=False,
            )

    except HTTPException:
        raise

    except requests.ConnectTimeout as error:
        logger.error(
            "[API INEA] Timeout de conexão ao salvar manifesto | "
            "modo=%s | destino=%s | endpoint=%s | erro=%s",
            modo,
            destino_url,
            endpoint,
            str(error),
        )

        raise HTTPException(
            status_code=504,
            detail=(
                "Timeout ao estabelecer conexão com o relay local."
                if INEA_WORKAROUND_ENABLED
                else "Timeout ao estabelecer conexão com a API do INEA."
            ),
        )

    except requests.ReadTimeout as error:
        logger.error(
            "[API INEA] Timeout de resposta ao salvar manifesto | "
            "modo=%s | destino=%s | endpoint=%s | erro=%s",
            modo,
            destino_url,
            endpoint,
            str(error),
        )

        raise HTTPException(
            status_code=504,
            detail=(
                "O relay demorou demais para processar o manifesto."
                if INEA_WORKAROUND_ENABLED
                else "A API do INEA demorou demais para processar o manifesto."
            ),
        )

    except requests.SSLError as error:
        logger.error(
            "[API INEA] Erro SSL ao salvar manifesto | "
            "modo=%s | destino=%s | endpoint=%s | erro=%s",
            modo,
            destino_url,
            endpoint,
            str(error),
        )

        raise HTTPException(
            status_code=502,
            detail=f"Erro SSL ao salvar manifesto no INEA: {str(error)}",
        )

    except requests.RequestException as error:
        logger.error(
            "[API INEA] Erro de comunicação ao salvar manifesto | "
            "modo=%s | destino=%s | endpoint=%s | erro=%s",
            modo,
            destino_url,
            endpoint,
            str(error),
        )

        raise HTTPException(
            status_code=502,
            detail=f"Erro de comunicação ao salvar manifesto: {str(error)}",
        )

    conteudo = response_inea.content or b""

    content_type = response_inea.headers.get(
        "Content-Type",
        "application/json; charset=utf-8",
    )

    logger.info(
        "[API INEA] Salvamento de manifesto finalizado | "
        "modo=%s | destino=%s | endpoint=%s | "
        "status=%s | content_type=%s | tamanho=%s",
        modo,
        destino_url,
        endpoint,
        response_inea.status_code,
        content_type,
        len(conteudo),
    )

    if response_inea.status_code >= 400:
        logger.warning(
            "[API INEA] Manifesto recusado | "
            "modo=%s | endpoint=%s | status=%s | resposta=%s",
            modo,
            endpoint,
            response_inea.status_code,
            response_inea.text[:1000],
        )

    return response_inea

def download_manifesto_inea(url: str) -> requests.Response:
    """
    Faz o download de um manifesto do INEA.

    Workaround habilitado:
        API Tree -> relay -> INEA

    Workaround desabilitado:
        API Tree -> INEA diretamente
    """

    codigo_barras, url_mascarada = (
        validar_url_download_manifesto_inea(url)
    )

    modo = (
        "relay-local"
        if INEA_WORKAROUND_ENABLED
        else "direto"
    )

    destino_url = ""

    logger.info(
        "[API INEA] Download de manifesto iniciado | "
        "modo=%s | codigo_barras=%s | url=%s",
        modo,
        codigo_barras,
        url_mascarada,
    )

    try:
        # ======================================================
        # WORKAROUND: API Tree -> relay local -> INEA
        # ======================================================
        if INEA_WORKAROUND_ENABLED:
            if not INEA_RELAY_URL:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Workaround INEA habilitado, mas "
                        "INEA_RELAY_URL não está configurada."
                    ),
                )

            if not INEA_RELAY_KEY:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Workaround INEA habilitado, mas "
                        "INEA_RELAY_KEY não está configurada."
                    ),
                )

            destino_url = (
                f"{INEA_RELAY_URL.rstrip('/')}"
                "/inea/downloadManifesto"
            )

            logger.warning(
                "[API INEA] Download utilizando workaround | "
                "codigo_barras=%s | destino=%s",
                codigo_barras,
                destino_url,
            )

            response_inea = requests.post(
                url=destino_url,
                headers={
                    "Accept": (
                        "application/pdf, "
                        "application/json, */*"
                    ),
                    "Content-Type": "application/json",
                    "X-Tree-Relay-Key": INEA_RELAY_KEY,
                    "User-Agent": "Tree-ESG-API/1.0",
                    "Connection": "close",
                },
                json={
                    "url": url,
                },
                timeout=(20, 120),
                allow_redirects=True,
            )

        # ======================================================
        # FLUXO DIRETO: API Tree -> INEA
        # ======================================================
        else:
            destino_url = url

            logger.info(
                "[API INEA] Download direto no INEA | "
                "codigo_barras=%s | url=%s",
                codigo_barras,
                url_mascarada,
            )

            response_inea = requests.post(
                url=destino_url,
                headers={
                    "Accept": (
                        "application/pdf, "
                        "application/octet-stream, */*"
                    ),
                    "User-Agent": "Tree-ESG-API/1.0",
                    "Connection": "close",
                },
                timeout=(15, 60),
                allow_redirects=True,
            )

    except HTTPException:
        raise

    except requests.ConnectTimeout as error:
        logger.error(
            "[API INEA] Timeout de conexão no download | "
            "modo=%s | destino=%s | codigo_barras=%s | erro=%s",
            modo,
            destino_url,
            codigo_barras,
            str(error),
        )

        raise HTTPException(
            status_code=504,
            detail=(
                "Timeout ao estabelecer conexão com o relay local."
                if INEA_WORKAROUND_ENABLED
                else "Timeout ao estabelecer conexão com a API do INEA."
            ),
        )

    except requests.ReadTimeout as error:
        logger.error(
            "[API INEA] Timeout de resposta no download | "
            "modo=%s | destino=%s | codigo_barras=%s | erro=%s",
            modo,
            destino_url,
            codigo_barras,
            str(error),
        )

        raise HTTPException(
            status_code=504,
            detail=(
                "O relay demorou demais para responder."
                if INEA_WORKAROUND_ENABLED
                else "A API do INEA demorou demais para responder."
            ),
        )

    except requests.SSLError as error:
        logger.error(
            "[API INEA] Erro SSL no download | "
            "modo=%s | destino=%s | codigo_barras=%s | erro=%s",
            modo,
            destino_url,
            codigo_barras,
            str(error),
        )

        raise HTTPException(
            status_code=502,
            detail=f"Erro SSL durante o download: {str(error)}",
        )

    except requests.RequestException as error:
        logger.error(
            "[API INEA] Erro de comunicação no download | "
            "modo=%s | destino=%s | codigo_barras=%s | erro=%s",
            modo,
            destino_url,
            codigo_barras,
            str(error),
        )

        raise HTTPException(
            status_code=502,
            detail=f"Erro de comunicação durante o download: {str(error)}",
        )

    conteudo = response_inea.content or b""

    content_type = response_inea.headers.get(
        "Content-Type",
        "application/octet-stream",
    )

    is_pdf = (
        "application/pdf" in content_type.lower()
        or conteudo.startswith(b"%PDF")
    )

    logger.info(
        "[API INEA] Download finalizado | "
        "modo=%s | destino=%s | codigo_barras=%s | "
        "status=%s | content_type=%s | is_pdf=%s | tamanho=%s",
        modo,
        destino_url,
        codigo_barras,
        response_inea.status_code,
        content_type,
        is_pdf,
        len(conteudo),
    )

    return response_inea

# =============
# HELPERS
# =============
