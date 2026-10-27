"""Authenticated server-side proxy for SIGOR manifest operations."""

import hashlib
import base64
import json
import logging
import re
import threading
import time
from typing import Any, Dict, Optional

import firebase_admin
import requests
from firebase_admin import auth as firebase_auth
from fastapi import APIRouter, HTTPException, Request, Response as FastAPIResponse
from fastapi.responses import Response
from pydantic import BaseModel

from services.inea import INEA_FIREBASE_APP_NAME, obter_firestore_client
from services.sigor import SIGOR_BASE_URL, gerar_token_sigor


logger = logging.getLogger("sigor_proxy")
router = APIRouter(prefix="/sigor", tags=["SIGOR"])

_TOKEN_CACHE: Dict[str, Dict[str, Any]] = {}
_LAST_AUTHENTICATED_AT: Dict[str, float] = {}
_TOKEN_LOCK = threading.RLock()
_TOKEN_TTL_SECONDS = 50 * 60
_MIN_AUTH_INTERVAL_SECONDS = 60
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_SAFE_USER_AGENT = "Tree ESG SIGOR relay"


class SigorRequest(BaseModel):
    empresaId: str
    filialId: str
    dados: Optional[Dict[str, Any]] = None


def _firebase_identity(request: Request) -> Dict[str, Any]:
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Autenticação Tree necessária.")

    try:
        obter_firestore_client()
        app = firebase_admin.get_app(INEA_FIREBASE_APP_NAME)
        return firebase_auth.verify_id_token(token, app=app)
    except firebase_admin.exceptions.FirebaseError:
        raise HTTPException(status_code=401, detail="Sessão Tree inválida ou expirada.")
    except ValueError:
        logger.exception("Firebase Admin não está inicializado para autenticação SIGOR.")
        raise HTTPException(status_code=503, detail="Autenticação Tree indisponível.")
    except Exception:
        logger.exception("Falha ao validar a sessão Tree na integração SIGOR.")
        raise HTTPException(status_code=503, detail="Não foi possível validar a sessão Tree.")


def _user_agent(request: Request) -> str:
    value = " ".join(request.headers.get("user-agent", "").split())
    return value[:512] or _SAFE_USER_AGENT


def _get_authorized_context(request: Request, dados: SigorRequest):
    if not _SAFE_ID.fullmatch(dados.empresaId) or not _SAFE_ID.fullmatch(dados.filialId):
        raise HTTPException(status_code=400, detail="Empresa ou filial inválida.")

    uid = _firebase_identity(request).get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Sessão Tree inválida ou expirada.")

    try:
        db = obter_firestore_client()
        user_ref = db.collection("usuarios").document(uid)
        user_snapshot = user_ref.get()
        if not user_snapshot.exists:
            raise HTTPException(status_code=403, detail="Usuário sem acesso ao SIGOR.")
        user_data = user_snapshot.to_dict() or {}

        managed_companies = user_data.get("empresas_geridas") or []
        if not isinstance(managed_companies, list):
            managed_companies = []
        authorized_company_ids = {str(user_data.get("cnpj", ""))}
        authorized_company_ids.update(str(value) for value in managed_companies)
        branch_values = user_data.get("filiais") or []
        if not isinstance(branch_values, list):
            branch_values = []
        authorized_branch_ids = {
            str(value.get("id")) if isinstance(value, dict) else str(value)
            for value in branch_values
        }

        if (user_data.get("categoria") != "sup"
                and dados.empresaId not in authorized_company_ids
                and dados.filialId not in authorized_branch_ids):
            raise HTTPException(status_code=403, detail="Sem acesso à empresa ou filial informada.")

        branch_ref = (
            db.collection("empresas").document(dados.empresaId)
            .collection("filhas").document(dados.filialId)
        )
        branch_snapshot = branch_ref.get()
        if not branch_snapshot.exists:
            raise HTTPException(status_code=403, detail="Filial não pertence à empresa informada.")
        branch_data = branch_snapshot.to_dict() or {}

        credentials_snapshot = user_ref.collection("mtr_creds").document(dados.filialId).get()
        credentials_data = credentials_snapshot.to_dict() if credentials_snapshot.exists else None
        cpf_cnpj = (credentials_data or {}).get("cpf") or user_data.get("cpf")
        password = (credentials_data or {}).get("pswSigor")
        unit = branch_data.get("unidadeSigor")
        if not cpf_cnpj or not password or not unit:
            raise HTTPException(status_code=422, detail="Credenciais ou unidade SIGOR não configuradas para a filial.")

        return uid, str(cpf_cnpj), str(password), str(unit)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Falha ao validar autorização SIGOR.")
        raise HTTPException(status_code=503, detail="Não foi possível validar o acesso SIGOR.")


def _cached_token(uid: str, cpf_cnpj: str, password: str, unit: str, user_agent: str) -> str:
    key = hashlib.sha256(f"{uid}\0{cpf_cnpj}\0{password}\0{unit}".encode()).hexdigest()
    now = time.time()
    with _TOKEN_LOCK:
        cached = _TOKEN_CACHE.get(key)
        if cached and cached["expires_at"] > now:
            return cached["token"]

        retry_after = int(_MIN_AUTH_INTERVAL_SECONDS - (now - _LAST_AUTHENTICATED_AT.get(key, 0)))
        if retry_after > 0:
            raise HTTPException(
                status_code=429,
                detail="A autenticação SIGOR está temporariamente limitada.",
                headers={"Retry-After": str(retry_after)},
            )

        _LAST_AUTHENTICATED_AT[key] = now
        token = gerar_token_sigor(cpf_cnpj, password, unit, user_agent=user_agent)
        expires_at = now + _TOKEN_TTL_SECONDS
        try:
            payload = token.removeprefix("Bearer ").split(".")[1]
            payload += "=" * (-len(payload) % 4)
            token_expiration = float(json.loads(base64.urlsafe_b64decode(payload).decode()).get("exp"))
            expires_at = min(expires_at, token_expiration)
        except (IndexError, ValueError, TypeError, json.JSONDecodeError):
            pass
        if expires_at <= now:
            raise HTTPException(status_code=502, detail="O SIGOR retornou um token expirado.")
        _TOKEN_CACHE[key] = {"token": token, "expires_at": expires_at}
        return token


def _sigor_response(method: str, path: str, token: str, user_agent: str, payload=None):
    headers = {"Authorization": token, "User-Agent": user_agent, "Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    try:
        upstream = requests.request(
            method, f"{SIGOR_BASE_URL}/{path}", headers=headers,
            json=payload, timeout=30,
        )
    except requests.Timeout:
        raise HTTPException(status_code=504, detail="Tempo limite excedido ao comunicar com o SIGOR.")
    except requests.RequestException:
        logger.exception("Falha de comunicação com o SIGOR em operação de manifesto.")
        raise HTTPException(status_code=502, detail="Falha de comunicação com o SIGOR.")

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("Content-Type", "application/octet-stream"),
        headers={"Cache-Control": "no-store"},
    )


@router.post("/get-token")
def sigor_get_token(request: Request, dados: SigorRequest, response: FastAPIResponse):
    context = _get_authorized_context(request, dados)
    token = _cached_token(*context, user_agent=_user_agent(request))
    response.headers["Cache-Control"] = "no-store"
    return {"mensagem": "Sucesso!", "objetoResposta": token, "erro": False}


@router.post("/emitir-manifesto")
def sigor_emitir_manifesto(request: Request, dados: SigorRequest):
    token = request.headers.get("X-Sigor-Token", "")
    if not isinstance(dados.dados, dict) or not token:
        raise HTTPException(status_code=400, detail="Dados ou token SIGOR ausentes.")
    _get_authorized_context(request, dados)
    return _sigor_response("POST", "salvarManifestoLote", token, _user_agent(request), dados.dados)


@router.post("/cancelar-manifesto")
def sigor_cancelar_manifesto(request: Request, dados: SigorRequest):
    token = request.headers.get("X-Sigor-Token", "")
    if not isinstance(dados.dados, dict) or not token:
        raise HTTPException(status_code=400, detail="Dados ou token SIGOR ausentes.")
    _get_authorized_context(request, dados)
    return _sigor_response("POST", "cancelarManifesto", token, _user_agent(request), dados.dados)


@router.post("/download-manifesto/{numero}")
def sigor_download_manifesto(request: Request, numero: str, dados: SigorRequest):
    token = request.headers.get("X-Sigor-Token", "")
    if not _SAFE_ID.fullmatch(numero) or not token:
        raise HTTPException(status_code=400, detail="Número de manifesto ou token SIGOR inválido.")
    _get_authorized_context(request, dados)
    return _sigor_response("POST", f"downloadManifesto/{numero}", token, _user_agent(request))
