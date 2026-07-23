import requests
from fastapi import HTTPException
from pydantic import BaseModel
from typing import Dict, Tuple, Optional, Union, Any
from fastapi import FastAPI, Request, HTTPException, APIRouter, Response, Header
from urllib.parse import urlparse
import os
import re
import secrets
import threading
import time

import json
import logging
import firebase_admin
from firebase_admin import firestore


logger = logging.getLogger("inea")
logger.setLevel(logging.INFO)

router = APIRouter(
    prefix="/inea",
    tags=["INEA"],
)

# ==========================================================
# ConfiguraÃ§Ã£o do workaround da API INEA
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

INEA_RELAY_COLLECTION = "configuracoes"
INEA_RELAY_DOCUMENT = "ineaRelay"
INEA_RELAY_CACHE_SECONDS = 30

_INEA_RELAY_CACHE = {
    "url": "",
    "expires_at": 0.0,
}
_INEA_RELAY_CACHE_LOCK = threading.Lock()
_FIRESTORE_CLIENT = os.getenv("FIREBASE_KEY", "")


class RegistrarIneaRelayRequest(BaseModel):
    url: str


def obter_firestore_client():
    """ObtÃ©m uma instÃ¢ncia compartilhada do Firestore via ADC."""

    global _FIRESTORE_CLIENT

    if _FIRESTORE_CLIENT is not None:
        return _FIRESTORE_CLIENT

    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app()

    _FIRESTORE_CLIENT = firestore.client()
    return _FIRESTORE_CLIENT


def validar_url_publica_relay(url: str) -> str:
    """Valida e normaliza uma URL gerada por Cloudflare Quick Tunnel."""

    try:
        parsed_url = urlparse((url or "").strip())
        parsed_port = parsed_url.port
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=f"URL do relay invÃ¡lida: {str(error)}",
        )

    hostname = (parsed_url.hostname or "").strip().lower()

    if parsed_url.scheme.lower() != "https":
        raise HTTPException(
            status_code=400,
            detail="A URL pÃºblica do relay deve utilizar HTTPS.",
        )

    if not re.fullmatch(
        r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.trycloudflare\.com",
        hostname,
    ):
        raise HTTPException(
            status_code=403,
            detail="Host do relay nÃ£o autorizado.",
        )

    if parsed_port not in (None, 443):
        raise HTTPException(
            status_code=403,
            detail="Porta do relay nÃ£o autorizada.",
        )

    if parsed_url.username or parsed_url.password:
        raise HTTPException(
            status_code=400,
            detail="A URL do relay nÃ£o pode conter credenciais.",
        )

    if parsed_url.path not in ("", "/"):
        raise HTTPException(
            status_code=400,
            detail="A URL do relay nÃ£o pode conter um caminho.",
        )

    if parsed_url.query or parsed_url.fragment:
        raise HTTPException(
            status_code=400,
            detail="A URL do relay nÃ£o pode conter query string ou fragmento.",
        )

    return f"https://{hostname}"


def atualizar_cache_inea_relay(url: str) -> None:
    with _INEA_RELAY_CACHE_LOCK:
        _INEA_RELAY_CACHE["url"] = url
        _INEA_RELAY_CACHE["expires_at"] = (
            time.monotonic() + INEA_RELAY_CACHE_SECONDS
        )


def obter_inea_relay_url(force_refresh: bool = False) -> str:
    """LÃª a URL atual do relay em configuracoes/ineaRelay."""

    with _INEA_RELAY_CACHE_LOCK:
        cached_url = _INEA_RELAY_CACHE["url"]
        cache_is_valid = (
            cached_url
            and time.monotonic() < _INEA_RELAY_CACHE["expires_at"]
        )

    if cache_is_valid and not force_refresh:
        return cached_url

    try:
        snapshot = (
            obter_firestore_client()
            .collection(INEA_RELAY_COLLECTION)
            .document(INEA_RELAY_DOCUMENT)
            .get()
        )
    except Exception as error:
        if cached_url:
            logger.warning(
                "[API INEA] Falha ao atualizar URL do relay; "
                "utilizando cache anterior | erro=%s",
                str(error),
            )
            return cached_url

        logger.exception(
            "[API INEA] NÃ£o foi possÃ­vel consultar a configuraÃ§Ã£o do relay"
        )
        raise HTTPException(
            status_code=503,
            detail="NÃ£o foi possÃ­vel consultar a configuraÃ§Ã£o do relay INEA.",
        )

    if not snapshot.exists:
        raise HTTPException(
            status_code=503,
            detail=(
                "Relay INEA ainda nÃ£o registrado em "
                "configuracoes/ineaRelay."
            ),
        )

    dados_relay = snapshot.to_dict() or {}

    if dados_relay.get("status") != "online":
        raise HTTPException(
            status_code=503,
            detail="Relay INEA indisponÃ­vel.",
        )

    try:
        relay_url = validar_url_publica_relay(dados_relay.get("url", ""))
    except HTTPException as error:
        logger.error(
            "[API INEA] URL invÃ¡lida armazenada no Firestore | detalhe=%s",
            error.detail,
        )
        raise HTTPException(
            status_code=503,
            detail="ConfiguraÃ§Ã£o invÃ¡lida do relay INEA.",
        )

    atualizar_cache_inea_relay(relay_url)
    return relay_url


def executar_post_inea_relay(
    endpoint_path: str,
    *,
    safe_to_retry: bool,
    **request_kwargs,
) -> tuple[requests.Response, str]:
    """Envia uma chamada ao relay e atualiza a URL apÃ³s falha de conexÃ£o."""

    if not INEA_RELAY_KEY:
        raise HTTPException(
            status_code=500,
            detail="INEA_RELAY_KEY nÃ£o configurada.",
        )

    headers = dict(request_kwargs.pop("headers", {}))
    headers["X-Tree-Relay-Key"] = INEA_RELAY_KEY
    request_kwargs["headers"] = headers

    relay_url = obter_inea_relay_url()
    destino_url = f"{relay_url}{endpoint_path}"

    try:
        return (
            requests.post(url=destino_url, **request_kwargs),
            destino_url,
        )
    except (requests.ConnectTimeout, requests.ConnectionError):
        refreshed_url = relay_url

        try:
            refreshed_url = obter_inea_relay_url(force_refresh=True)
        except HTTPException:
            pass

        if safe_to_retry and refreshed_url != relay_url:
            refreshed_destino = f"{refreshed_url}{endpoint_path}"
            logger.warning(
                "[API INEA] URL do relay alterada; repetindo operaÃ§Ã£o segura | "
                "endpoint=%s",
                endpoint_path,
            )
            return (
                requests.post(url=refreshed_destino, **request_kwargs),
                refreshed_destino,
            )

        raise


def registrar_inea_relay(
    dados: RegistrarIneaRelayRequest,
    x_tree_relay_key: Optional[str] = Header(
        default=None,
        alias="X-Tree-Relay-Key",
    ),
):
    """Registra uma nova URL somente apÃ³s validar o health check pÃºblico."""

    if not INEA_RELAY_KEY:
        raise HTTPException(
            status_code=500,
            detail="INEA_RELAY_KEY nÃ£o configurada.",
        )

    if not x_tree_relay_key or not secrets.compare_digest(
        x_tree_relay_key,
        INEA_RELAY_KEY,
    ):
        raise HTTPException(
            status_code=403,
            detail="Chave de registro do relay invÃ¡lida.",
        )

    relay_url = validar_url_publica_relay(dados.url)

    try:
        health_response = requests.get(
            f"{relay_url}/health",
            timeout=(5, 15),
            allow_redirects=False,
        )
        health_response.raise_for_status()
        health_data = health_response.json()
    except (requests.RequestException, ValueError) as error:
        logger.warning(
            "[API INEA] Registro recusado: health check falhou | erro=%s",
            str(error),
        )
        raise HTTPException(
            status_code=503,
            detail="O health check pÃºblico do relay falhou.",
        )

    if (
        health_data.get("status") != "ok"
        or health_data.get("service") != "tree-inea-local-relay"
        or health_data.get("relay_key_configured") is not True
    ):
        raise HTTPException(
            status_code=503,
            detail="O endereÃ§o informado nÃ£o corresponde ao relay INEA esperado.",
        )

    try:
        doc_ref = (
            obter_firestore_client()
            .collection(INEA_RELAY_COLLECTION)
            .document(INEA_RELAY_DOCUMENT)
        )
        snapshot = doc_ref.get()
        previous_data = snapshot.to_dict() if snapshot.exists else {}
        changed = previous_data.get("url") != relay_url

        relay_data = {
            "url": relay_url,
            "status": "online",
            "lastHealthCheck": firestore.SERVER_TIMESTAMP,
            "source": "cloudflare-quick-tunnel",
        }

        if changed:
            relay_data["updatedAt"] = firestore.SERVER_TIMESTAMP

        doc_ref.set(relay_data, merge=True)
    except Exception as error:
        logger.exception(
            "[API INEA] Falha ao registrar URL do relay no Firestore"
        )
        raise HTTPException(
            status_code=503,
            detail="NÃ£o foi possÃ­vel registrar a URL do relay INEA.",
        )

    atualizar_cache_inea_relay(relay_url)

    logger.info(
        "[API INEA] Relay registrado | alterado=%s | url=%s",
        changed,
        relay_url,
    )

    return {
        "status": "ok",
        "changed": changed,
        "url": relay_url,
    }

INEA_BASE_URL = "http://mtr.inea.rj.gov.br/api"
INEA_HOST = "mtr.inea.rj.gov.br"

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

class CancelarManifestoIneaRequest(BaseModel):
    url: str
    cancelamento: dict[str, Any]

def validar_body_cancelamento_inea(
    cancelamento: dict[str, Any],
) -> None:
    campos_obrigatorios = {
        "login",
        "senha",
        "cnp",
        "codUnidade",
        "manifestoCodigo",
        "justificativa",
    }

    campos_ausentes = [
        campo
        for campo in campos_obrigatorios
        if campo not in cancelamento
        or cancelamento[campo] is None
        or str(cancelamento[campo]).strip() == ""
    ]

    if campos_ausentes:
        raise HTTPException(
            status_code=400,
            detail=(
                "Campos obrigatÃ³rios nÃ£o informados: "
                f"{', '.join(sorted(campos_ausentes))}"
            ),
        )

    manifesto_codigo = str(
        cancelamento["manifestoCodigo"]
    ).strip()

    if not manifesto_codigo.isdigit():
        raise HTTPException(
            status_code=400,
            detail="manifestoCodigo deve conter somente nÃºmeros.",
        )

    cod_unidade = str(
        cancelamento["codUnidade"]
    ).strip()

    if not cod_unidade.isdigit():
        raise HTTPException(
            status_code=400,
            detail="codUnidade deve conter somente nÃºmeros.",
        )

    justificativa = str(
        cancelamento["justificativa"]
    ).strip()

    if len(justificativa) < 3:
        raise HTTPException(
            status_code=400,
            detail=(
                "A justificativa do cancelamento deve possuir "
                "pelo menos 3 caracteres."
            ),
        )

def validar_url_cancelar_manifesto_inea(
    url: str,
) -> tuple[str, str]:
    """
    Valida exclusivamente o endpoint de cancelamento do INEA.

    Endpoint permitido:
        POST /api/cancelarManifesto
    """

    try:
        parsed_url = urlparse(url)
        parsed_port = parsed_url.port

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=f"URL ou porta invÃ¡lida: {str(error)}",
        )

    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail=f"URL invÃ¡lida: {str(error)}",
        )

    if parsed_url.scheme.lower() != "https":
        raise HTTPException(
            status_code=400,
            detail="A URL do INEA deve utilizar HTTPS.",
        )

    hostname = (parsed_url.hostname or "").strip().lower()

    if hostname != INEA_HOST:
        raise HTTPException(
            status_code=403,
            detail="Host da API INEA nÃ£o autorizado.",
        )

    if parsed_port not in (None, 443):
        raise HTTPException(
            status_code=403,
            detail="Porta da API INEA nÃ£o autorizada.",
        )

    if parsed_url.username or parsed_url.password:
        raise HTTPException(
            status_code=400,
            detail="A URL nÃ£o pode conter credenciais no host.",
        )

    if parsed_url.query or parsed_url.fragment:
        raise HTTPException(
            status_code=400,
            detail="A URL nÃ£o pode conter query string ou fragmento.",
        )

    path = parsed_url.path.rstrip("/")

    if path != "/api/cancelarManifesto":
        raise HTTPException(
            status_code=403,
            detail=(
                "Endpoint INEA nÃ£o autorizado para cancelamento. "
                "Esperado: /api/cancelarManifesto"
            ),
        )

    url_validada = (
        f"https://{INEA_HOST}"
        "/api/cancelarManifesto"
    )

    return "cancelarManifesto", url_validada



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
            detail=f"URL ou porta invÃ¡lida: {str(error)}",
        )

    if parsed_url.scheme.lower() != "https":
        raise HTTPException(
            status_code=400,
            detail="A URL do INEA deve utilizar HTTPS.",
        )

    hostname = (parsed_url.hostname or "").strip().lower()

    if hostname not in INEA_ALLOWED_HOSTS:
        logger.warning(
            "[API INEA] Host recusado na validaÃ§Ã£o | "
            "host_recebido=%s | hosts_permitidos=%s",
            hostname,
            sorted(INEA_ALLOWED_HOSTS),
        )

        raise HTTPException(
            status_code=403,
            detail="Host da API INEA nÃ£o autorizado.",
        )

    if parsed_port not in (None, 443):
        raise HTTPException(
            status_code=403,
            detail="Porta da API INEA nÃ£o autorizada.",
        )

    if parsed_url.username or parsed_url.password:
        raise HTTPException(
            status_code=400,
            detail="A URL nÃ£o pode conter credenciais no host.",
        )

    if parsed_url.query or parsed_url.fragment:
        raise HTTPException(
            status_code=400,
            detail="A URL nÃ£o pode conter query string ou fragmento.",
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
                "Estrutura invÃ¡lida. Esperado: "
                "/api/buscaPdfManifestoPorCodigoBarras/"
                "{cpf}/{senha}/{cnpj}/{unidade}/{codigoDeBarras}"
            ),
        )

    if partes[0] != "api":
        raise HTTPException(
            status_code=400,
            detail="Prefixo da API INEA invÃ¡lido.",
        )

    if partes[1] != "buscaPdfManifestoPorCodigoBarras":
        raise HTTPException(
            status_code=403,
            detail=f"Endpoint nÃ£o autorizado: {partes[1]}",
        )

    cpf = partes[2]
    cnpj = partes[4]
    unidade = partes[5]
    codigo_barras = partes[6]

    if not cpf.isdigit() or len(cpf) != 11:
        raise HTTPException(
            status_code=400,
            detail="CPF de acesso invÃ¡lido.",
        )

    if not cnpj.isdigit() or len(cnpj) not in (11, 14):
        raise HTTPException(
            status_code=400,
            detail="CNPJ ou CPF da unidade invÃ¡lido.",
        )

    if not unidade.isdigit():
        raise HTTPException(
            status_code=400,
            detail="CÃ³digo da unidade invÃ¡lido.",
        )

    if not codigo_barras.isdigit():
        raise HTTPException(
            status_code=400,
            detail="CÃ³digo de barras invÃ¡lido.",
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
            detail=f"URL do INEA invÃ¡lida: {str(error)}",
        )

    if parsed_url.scheme != "https":
        raise HTTPException(
            status_code=400,
            detail="A URL do INEA deve utilizar HTTPS.",
        )

    if parsed_url.hostname != "mtr.inea.rj.gov.br":
        raise HTTPException(
            status_code=403,
            detail="Host da API INEA nÃ£o autorizado.",
        )

    if parsed_url.port not in (None, 443):
        raise HTTPException(
            status_code=403,
            detail="Porta da API INEA nÃ£o autorizada.",
        )

    if parsed_url.query or parsed_url.fragment:
        raise HTTPException(
            status_code=400,
            detail="A URL do INEA nÃ£o pode conter query string ou fragmento.",
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
                "Estrutura da URL INEA invÃ¡lida. "
                "Esperado: /api/{endpoint}/{cpf}/{senha}/{cnpj}/{unidade}"
            ),
        )

    if partes[0] != "api":
        raise HTTPException(
            status_code=400,
            detail="Prefixo da API INEA invÃ¡lido.",
        )

    endpoint = partes[1]

    if endpoint not in INEA_LIST_ENDPOINTS:
        raise HTTPException(
            status_code=403,
            detail=f"Endpoint INEA nÃ£o autorizado: {endpoint}",
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

def cancelar_manifesto_inea(
    url: str,
    cancelamento: dict,
) -> requests.Response:
    """
    Cancela um manifesto no INEA.

    Workaround ativo:
        API Tree -> relay local -> INEA

    Workaround desativado:
        API Tree -> INEA diretamente
    """

    endpoint, url_validada = (
        validar_url_cancelar_manifesto_inea(url)
    )

    validar_body_cancelamento_inea(
        cancelamento
    )

    modo = (
        "relay-local"
        if INEA_WORKAROUND_ENABLED
        else "direto"
    )

    destino_url = ""

    logger.info(
        "[API INEA] Cancelamento iniciado | "
        "modo=%s | endpoint=%s | manifesto_codigo=%s",
        modo,
        endpoint,
        cancelamento.get("manifestoCodigo"),
    )

    try:
        if INEA_WORKAROUND_ENABLED:
            logger.warning(
                "[API INEA] Cancelamento utilizando workaround | "
                "manifesto_codigo=%s",
                cancelamento.get("manifestoCodigo"),
            )

            response_inea, destino_url = executar_post_inea_relay(
                "/inea/cancelarManifesto",
                safe_to_retry=False,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/plain, */*",
                    "User-Agent": "Tree-ESG-API/1.0",
                    "Connection": "close",
                },
                json={
                    "url": url_validada,
                    "cancelamento": cancelamento,
                },
                timeout=(20, 120),
                allow_redirects=False,
            )

        else:
            destino_url = url_validada

            payload = json.dumps(
                cancelamento,
                ensure_ascii=False,
            )

            logger.info(
                "[API INEA] Cancelamento direto | "
                "destino=%s | manifesto_codigo=%s",
                destino_url,
                cancelamento.get("manifestoCodigo"),
            )

            response_inea = requests.post(
                url=destino_url,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/plain, */*",
                    "User-Agent": "Tree-ESG-API/1.0",
                    "Connection": "close",
                },
                data=payload,
                timeout=(15, 90),
                allow_redirects=False,
            )

    except HTTPException:
        raise

    except requests.ConnectTimeout as error:
        logger.error(
            "[API INEA] Timeout de conexÃ£o no cancelamento | "
            "modo=%s | destino=%s | erro=%s",
            modo,
            destino_url,
            str(error),
        )

        raise HTTPException(
            status_code=504,
            detail=(
                "Timeout ao conectar com o relay local."
                if INEA_WORKAROUND_ENABLED
                else "Timeout ao conectar com a API do INEA."
            ),
        )

    except requests.ReadTimeout as error:
        logger.error(
            "[API INEA] Timeout de resposta no cancelamento | "
            "modo=%s | destino=%s | erro=%s",
            modo,
            destino_url,
            str(error),
        )

        raise HTTPException(
            status_code=504,
            detail="Timeout ao processar o cancelamento do manifesto.",
        )

    except requests.SSLError as error:
        logger.error(
            "[API INEA] Erro SSL no cancelamento | "
            "modo=%s | destino=%s | erro=%s",
            modo,
            destino_url,
            str(error),
        )

        raise HTTPException(
            status_code=502,
            detail=f"Erro SSL ao cancelar manifesto: {str(error)}",
        )

    except requests.RequestException as error:
        logger.error(
            "[API INEA] Erro de comunicaÃ§Ã£o no cancelamento | "
            "modo=%s | destino=%s | erro=%s",
            modo,
            destino_url,
            str(error),
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "Erro de comunicaÃ§Ã£o ao cancelar manifesto: "
                f"{str(error)}"
            ),
        )

    logger.info(
        "[API INEA] Cancelamento finalizado | "
        "modo=%s | destino=%s | manifesto_codigo=%s | "
        "status=%s | tamanho=%s",
        modo,
        destino_url,
        cancelamento.get("manifestoCodigo"),
        response_inea.status_code,
        len(response_inea.content or b""),
    )

    return response_inea

def validar_url_salvar_manifesto_inea(
    url: str,
) -> tuple[str, str]:
    """
    Valida o endpoint real de salvamento em lote do INEA.

    Endpoint aceito:
        POST /api/salvarManifestoLote

    Login, senha, CNPJ e unidade ficam no body.
    """

    try:
        parsed_url = urlparse(url)
        parsed_port = parsed_url.port

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=f"URL ou porta invÃ¡lida: {str(error)}",
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
            detail="Host da API INEA nÃ£o autorizado.",
        )

    if parsed_port not in (None, 443):
        raise HTTPException(
            status_code=403,
            detail="Porta da API INEA nÃ£o autorizada.",
        )

    if parsed_url.username or parsed_url.password:
        raise HTTPException(
            status_code=400,
            detail="A URL nÃ£o pode conter credenciais no host.",
        )

    if parsed_url.query or parsed_url.fragment:
        raise HTTPException(
            status_code=400,
            detail="A URL nÃ£o pode conter query string ou fragmento.",
        )

    path = parsed_url.path.rstrip("/")

    if path != "/api/salvarManifestoLote":
        raise HTTPException(
            status_code=400,
            detail=(
                "Endpoint invÃ¡lido. Esperado: "
                "/api/salvarManifestoLote"
            ),
        )

    url_validada = (
        "https://mtr.inea.rj.gov.br"
        "/api/salvarManifestoLote"
    )

    return "salvarManifestoLote", url_validada

def retorna_lista_inea(url: str) -> requests.Response:
    """
    Consulta uma das listas auxiliares da API do INEA.

    Com INEA_WORKAROUND_ENABLED=false:
        API Tree -> API INEA

    Com INEA_WORKAROUND_ENABLED=true:
        API Tree -> Cloudflare Tunnel -> Relay local -> API INEA

    A resposta HTTP recebida Ã© devolvida integralmente para a rota.
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
            logger.warning(
                "[API INEA] Workaround habilitado | "
                "endpoint=%s | url=%s",
                endpoint,
                url_mascarada,
            )

            response_inea, _ = executar_post_inea_relay(
                "/inea/retornaListaInea",
                safe_to_retry=True,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
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
            "[API INEA] Timeout de conexÃ£o | "
            "destino=%s | endpoint=%s | erro=%s",
            destino,
            endpoint,
            str(error),
        )

        raise HTTPException(
            status_code=504,
            detail=f"Timeout ao estabelecer conexÃ£o com o {destino}.",
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
            "[API INEA] Erro de comunicaÃ§Ã£o | "
            "destino=%s | endpoint=%s | erro=%s",
            destino,
            endpoint,
            str(error),
        )

        raise HTTPException(
            status_code=502,
            detail=f"Erro de comunicaÃ§Ã£o com o {destino}: {str(error)}",
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
            detail=f"Erro de comunicaÃ§Ã£o com o INEA: {str(e)}"
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

    # tenta interpretar retorno (Ã s vezes vem JSON)
    try:
        body = r.json()
    except Exception:
        body = r.text[:500]

    # valida cookie bÃ¡sico
    js = s.cookies.get("JSESSIONID") or r.cookies.get("JSESSIONID")
    if not js:
        raise RuntimeError(f"Login sem JSESSIONID. status={r.status_code} body={body}")

    # se a API do INEA voltar algo que sinalize erro: vocÃª pode reforÃ§ar aqui
    # Ex.: {"sucesso":"N"} etc. Como vocÃª nÃ£o colou o payload de retorno do login, mantive leve.

    return s

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
            "[API INEA] Manifesto invÃ¡lido para serializaÃ§Ã£o | erro=%s",
            str(error),
        )

        raise HTTPException(
            status_code=400,
            detail=f"Manifesto invÃ¡lido para serializaÃ§Ã£o JSON: {str(error)}",
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
    # informaÃ§Ãµes pessoais ou operacionais sensÃ­veis.
    logger.info(
        "[API INEA] Campos do manifesto | campos=%s",
        sorted(manifesto.keys()),
    )

    try:
        # ======================================================
        # WORKAROUND: API Tree -> relay local -> INEA
        # ======================================================
        if INEA_WORKAROUND_ENABLED:
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
                "endpoint=%s | tamanho_payload=%s",
                endpoint,
                len(payload_relay),
            )

            response_inea, destino_url = executar_post_inea_relay(
                "/inea/salvarManifesto",
                safe_to_retry=False,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Accept": "application/json, text/plain, */*",
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
            "[API INEA] Timeout de conexÃ£o ao salvar manifesto | "
            "modo=%s | destino=%s | endpoint=%s | erro=%s",
            modo,
            destino_url,
            endpoint,
            str(error),
        )

        raise HTTPException(
            status_code=504,
            detail=(
                "Timeout ao estabelecer conexÃ£o com o relay local."
                if INEA_WORKAROUND_ENABLED
                else "Timeout ao estabelecer conexÃ£o com a API do INEA."
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
            "[API INEA] Erro de comunicaÃ§Ã£o ao salvar manifesto | "
            "modo=%s | destino=%s | endpoint=%s | erro=%s",
            modo,
            destino_url,
            endpoint,
            str(error),
        )

        raise HTTPException(
            status_code=502,
            detail=f"Erro de comunicaÃ§Ã£o ao salvar manifesto: {str(error)}",
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
            logger.warning(
                "[API INEA] Download utilizando workaround | "
                "codigo_barras=%s",
                codigo_barras,
            )

            response_inea, destino_url = executar_post_inea_relay(
                "/inea/downloadManifesto",
                safe_to_retry=True,
                headers={
                    "Accept": (
                        "application/pdf, "
                        "application/json, */*"
                    ),
                    "Content-Type": "application/json",
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
            "[API INEA] Timeout de conexÃ£o no download | "
            "modo=%s | destino=%s | codigo_barras=%s | erro=%s",
            modo,
            destino_url,
            codigo_barras,
            str(error),
        )

        raise HTTPException(
            status_code=504,
            detail=(
                "Timeout ao estabelecer conexÃ£o com o relay local."
                if INEA_WORKAROUND_ENABLED
                else "Timeout ao estabelecer conexÃ£o com a API do INEA."
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
            "[API INEA] Erro de comunicaÃ§Ã£o no download | "
            "modo=%s | destino=%s | codigo_barras=%s | erro=%s",
            modo,
            destino_url,
            codigo_barras,
            str(error),
        )

        raise HTTPException(
            status_code=502,
            detail=f"Erro de comunicaÃ§Ã£o durante o download: {str(error)}",
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