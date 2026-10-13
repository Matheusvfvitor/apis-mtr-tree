import requests
from services.query_response import sanitize_query_response
import logging
import re
import time
from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator
from typing import Dict, Tuple, Optional, Union, Any

SEMAD_BASE_URL = "https://mtr.meioambiente.go.gov.br/api"


# =========================
# Schema de entrada SEMAD
# =========================
class ConsultaSemadManifestoRequest(BaseModel):
    pessoaCodigo: str | int = Field()
    cnpj: str = Field(min_length=1)
    cpf: str = Field(min_length=1)
    senha: str = Field(min_length=1)
    codigoBarras: str = Field(pattern=r"^[0-9]{34}$")

    @field_validator("pessoaCodigo", mode="before")
    @classmethod
    def validar_pessoa_codigo(cls, value):
        if type(value) not in (str, int) or not str(value).strip():
            raise ValueError("pessoaCodigo não informado.")
        return str(value).strip()

    @field_validator("cnpj", "cpf", "senha")
    @classmethod
    def validar_obrigatorios(cls, value):
        if not value.strip():
            raise ValueError("Campo obrigatório SEMAD vazio.")
        return value


# =========================
# Passo 1 - Get Token SEMAD
# =========================
logger = logging.getLogger("semad")


def _consulta_semad_json(url: str, step: str, **kwargs) -> dict:
    started_at = time.perf_counter()
    context = {"system": "SEMAD", "step": f"semad.{step}.start"}
    logger.info(context["step"], extra=context)
    try:
        response = requests.post(url, timeout=30, **kwargs)
    except requests.Timeout as error:
        logger.error("semad.error", extra={**context, "error_type": type(error).__name__,
                     "elapsed_ms": (time.perf_counter() - started_at) * 1000})
        raise HTTPException(status_code=504, detail="Timeout na consulta SEMAD.") from None
    except requests.RequestException as error:
        logger.error("semad.error", extra={**context, "error_type": type(error).__name__,
                     "elapsed_ms": (time.perf_counter() - started_at) * 1000})
        raise HTTPException(status_code=502, detail="Erro de comunicação com a SEMAD.") from None
    logger.info(f"semad.{step}.http_response", extra={"system": "SEMAD", "step": f"semad.{step}.http_response",
                "upstream_status": response.status_code, "elapsed_ms": (time.perf_counter() - started_at) * 1000})
    if response.status_code != 200:
        status = response.status_code if response.status_code in {401, 403} else 502
        raise HTTPException(status_code=status, detail="Consulta SEMAD recusada.")
    try:
        data = response.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="Resposta inválida da SEMAD.") from None
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Resposta inválida da SEMAD.")
    if step == "manifest" and (
        data.get("erro") is True or data.get("sucesso") is False or data.get("success") is False
        or (type(data.get("retornoCodigo")) is int and data["retornoCodigo"] != 0)
    ):
        raise HTTPException(status_code=422, detail=sanitize_query_response(data))
    if data.get("erro") is True or data.get("sucesso") is False:
        raise HTTPException(status_code=502, detail="Resposta inválida da SEMAD.")
    return data


def gerar_token_semad(pessoa_codigo: str | int, cnpj: str, cpf: str, senha: str) -> str:
    if pessoa_codigo is None or not str(pessoa_codigo).strip():
        raise HTTPException(status_code=400, detail="pessoaCodigo SEMAD não informado.")
    if any(not isinstance(value, str) or not value.strip() for value in (cnpj, cpf, senha)):
        raise HTTPException(status_code=400, detail="Credenciais SEMAD incompletas.")
    data = _consulta_semad_json(
        f"{SEMAD_BASE_URL}/gettoken", "token",
        json={"pessoaCodigo": pessoa_codigo, "pessoaCnpj": cnpj, "usuarioCpf": cpf, "senha": senha},
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    token = data.get("token")
    if (type(data.get("retornoCodigo")) is not int or data["retornoCodigo"] != 0
            or not isinstance(token, str) or not token.strip()):
        raise HTTPException(status_code=502, detail="Token SEMAD não retornado ou contrato inválido.")
    return token.strip()


def buscar_parceiro_semad(
    cookies: Union[Dict[str, str], requests.cookies.RequestsCookieJar],
    cnpj: str,
    armazenador: bool = False,
    tipo_pessoa: str = "2",
    codigo_unidade: str = "armazenador",
    timeout: int = 30,
    session: Optional[requests.Session] = None,
) -> Dict[str, Any]:

    # Reaproveita session se você passar uma (recomendado).
    s = session or requests.Session()

    # Injeta cookies recebidos
    if isinstance(cookies, requests.cookies.RequestsCookieJar):
        s.cookies.update(cookies)
    else:
        s.cookies.update(cookies)

    headers = {
        "Accept": "*/*",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://mtr.meioambiente.go.gov.br",
        "Referer": "https://mtr.meioambiente.go.gov.br/ControllerServlet?acao=cadastroManifesto",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
        ),
    }

    # Form data na ordem (pra ficar bem próximo do Network do Chrome)
    if armazenador == True:
        form_fields = [
            ("acao", "buscaPessoaPorTipo"),
            ("cnpj", cnpj),
            ("tipoPessoa", tipo_pessoa),
            ("codigoUnidade", ""),
            ("armazenador", "S"),  # esse "S" solto do payload
        ]
    else:
        form_fields = [
            ("acao", "buscaPessoaPorTipo"),
            ("cnpj", cnpj),
            ("tipoPessoa", tipo_pessoa),
        ]

    BASE_URL = "https://mtr.meioambiente.go.gov.br/ControllerServlet"


    resp = s.post(BASE_URL, headers=headers, data=form_fields, timeout=timeout)
    resp.raise_for_status()

    # A resposta diz ser application/json;charset=utf-8
    try:
        return resp.json()
    except Exception:
        # fallback pra facilitar debug se o servidor devolver html/erro
        return {
            "ok": False,
            "status_code": resp.status_code,
            "content_type": resp.headers.get("content-type"),
            "text": resp.text[:2000],
        }




# =========================
# Serviço de cookies FEAM
# =========================
LOGIN_URL = "https://mtr.meioambiente.go.gov.br/ControllerServlet"

def autenticar_e_obter_cookies(
    cnpj: str,
    senha: str,
    cpf_usuario: str,
    unidade_codigo: str = "",
    cpf_usuario2: str = "",   # caso exista "txtCpfUsuario" e outro campo, deixe aqui se precisar
    timeout: int = 30,
) -> Tuple[Dict[str, str], str, requests.Session]:

    s = requests.Session()

    # Headers parecidos com o browser (os essenciais)
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://mtr.meioambiente.go.gov.br",
        "Referer": "https://mtr.meioambiente.go.gov.br/index.jsp",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
        ),
    }

    data = {
        "acao": "autenticaUsuario",
        "txtCnpj": cnpj,
        "txtSenha": senha,
        "txtUnidadeCodigo": unidade_codigo,
        "txtCpfUsuario": cpf_usuario,
        "tipoPessoaSociedade": "J",
    }

    resp = s.post(LOGIN_URL, headers=headers, data=data, timeout=timeout)
    resp.raise_for_status()

    # Cookies que a sessão armazenou (vindos dos Set-Cookie do servidor)
    cookies = s.cookies.get_dict()

    return cookies, resp.text, s

BASE_URL = "https://mtr.meioambiente.go.gov.br/ControllerServlet"


# =========================
# BUSCAR TRANSPORTADOR
# =========================

def buscar_transportador_semad(cnpj):
    print('\n===================BUSCANDO TRANSPORTADOR ========\n')
    
    print('\n===================BUSCANDO OS COOKIES =============')
    cookies, body, session = autenticar_e_obter_cookies(
        cnpj="39228967000160",
        senha="Tree@2025",
        cpf_usuario="04304532642",
        unidade_codigo=""
    )
    print('\n-------------------Cookies capturados --------------')
    print('JSESSIONID', cookies.get('JSESSIONID'))
    print('COOKIE_GENERICO', cookies.get('CookieGenericoGoias'))
    print('TS01925403', cookies.get('TS01925403'))
    print('---------------------------------------------------\n')
    
    cookies_login = {
    "JSESSIONID": cookies.get('JSESSIONID'),
    "TS01925403": cookies.get('TS01925403'),
    "CookieGenericoGoias": cookies.get('CookieGenericoGoias'),
    }
    
    r = buscar_parceiro_semad(
        cookies=cookies_login,
        cnpj=cnpj,
        tipo_pessoa="2",
    )
    print('\n======= Resposta =========')
    print(r)
    print('==========================\n')

    return r
  
# =========================
# BUSCAR DESTINO
# =========================
  
def buscar_destino_semad(cnpj):
    print('\n===================BUSCANDO DESTINO ==============\n')
    
    print('\n===================BUSCANDO OS COOKIES =============')
    cookies, body, session = autenticar_e_obter_cookies(
        cnpj="39228967000160",
        senha="Tree@2025",
        cpf_usuario="04304532642",
        unidade_codigo=""
    )
    print('\n-------------------Cookies capturados --------------')
    print('JSESSIONID', cookies.get('JSESSIONID'))
    print('COOKIE_GENERICO', cookies.get('CookieGenericoGoias'))
    print('TS01925403', cookies.get('TS01925403'))
    print('---------------------------------------------------\n')
    
    cookies_login = {
    "JSESSIONID": cookies.get('JSESSIONID'),
    "TS01925403": cookies.get('TS01925403'),
    "CookieGenericoGoias": cookies.get('CookieGenericoGoias'),
    }
    
    r = buscar_parceiro_semad(
        cookies=cookies_login,
        cnpj=cnpj,
        tipo_pessoa="4",
    )
    print('\n======= Resposta =========')
    print(r)
    print('==========================\n')

    return r
  
# =========================
# BUSCAR ARMAZENADOR
# =========================
  
def buscar_armazenador_semad(cnpj):
    print('\n============== BUSCANDO ARMAZENADOR ==============\n')
    
    print('\n===================BUSCANDO OS COOKIES =============')
    cookies, body, session = autenticar_e_obter_cookies(
        cnpj="39228967000160",
        senha="Tree@2025",
        cpf_usuario="04304532642",
        unidade_codigo=""
    )
    print('\n-------------------Cookies capturados --------------')
    print('JSESSIONID', cookies.get('JSESSIONID'))
    print('COOKIE_GENERICO', cookies.get('CookieGenericoGoias'))
    print('TS01925403', cookies.get('TS01925403'))
    print('---------------------------------------------------\n')
    
    cookies_login = {
    "JSESSIONID": cookies.get('JSESSIONID'),
    "TS01925403": cookies.get('TS01925403'),
    "CookieGenericoGoias": cookies.get('CookieGenericoGoias'),
    }
    
    r = buscar_parceiro_semad(
        cookies=cookies_login,
        cnpj=cnpj,
        tipo_pessoa="2",
        armazenador=True
    )
    print('\n======= Resposta =========')
    print(r)
    print('==========================\n')

    return r
   

# =========================
# Passo 2 - Retorna Manifesto
# =========================
def retorna_manifesto_semad(token: str, codigo_barras: str):
    if not re.fullmatch(r"[0-9]{34}", codigo_barras or ""):
        raise HTTPException(status_code=400, detail="Código de barras SEMAD inválido.")
    token = str(token or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token or token.lower() == "bearer" or token.lower().startswith("bearer "):
        raise HTTPException(status_code=400, detail="Token SEMAD não informado.")
    data = _consulta_semad_json(
        f"{SEMAD_BASE_URL}/retornaManifesto/{codigo_barras}", "manifest",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "application/json"},
    )
    identifier = data.get("manifestoCodigo")
    if (type(identifier) not in (str, int) or not re.fullmatch(r"[0-9]+", str(identifier))
            or int(str(identifier)) != int(codigo_barras[:10])
            or ("retornoCodigo" in data and (type(data["retornoCodigo"]) is not int or data["retornoCodigo"] != 0))):
        raise HTTPException(status_code=502, detail="Contrato de manifesto SEMAD não reconhecido.")
    return sanitize_query_response(data)


def download_mtr_semad(
    pessoa_codigo: int,
    cnpj: str,
    cpf: str,
    senha: str,
    codigo_barras: str
) -> requests.Response:
    codigo_barras = str(codigo_barras or "").strip()

    if len(codigo_barras) != 34:
        raise HTTPException(
            status_code=400,
            detail=(
                "O código de barras do MTR SEMAD "
                "deve possuir 34 caracteres."
            )
        )

    session = requests.Session()

    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/145.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*"
    })

    try:
        session.get(
            "https://mtr.meioambiente.go.gov.br/",
            timeout=20
        )
    except requests.RequestException:
        pass

    token_url = f"{SEMAD_BASE_URL}/gettoken"

    token_payload = {
        "pessoaCodigo": pessoa_codigo,
        "pessoaCnpj": cnpj,
        "usuarioCpf": cpf,
        "senha": senha
    }

    try:
        token_response = session.post(
            token_url,
            json=token_payload,
            headers={
                "Content-Type": "application/json"
            },
            timeout=30
        )
    except requests.RequestException as error:
        raise HTTPException(
            status_code=502,
            detail=(
                "Erro de comunicação com a SEMAD "
                f"durante a autenticação: {str(error)}"
            )
        )

    if token_response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=(
                "A SEMAD recusou a autenticação. "
                f"Status: {token_response.status_code}"
            )
        )

    try:
        token_data = token_response.json()
    except ValueError:
        raise HTTPException(
            status_code=502,
            detail=(
                "A SEMAD retornou uma resposta inválida "
                "durante a autenticação."
            )
        )

    token = token_data.get("token")

    if (
        token_data.get("retornoCodigo") != 0
        or not token
    ):
        mensagem_semad = (
            token_data.get("retorno")
            or "Credenciais não autorizadas."
        )

        raise HTTPException(
            status_code=401,
            detail=f"Falha na autenticação SEMAD: {mensagem_semad}"
        )

    download_url = (
        f"{SEMAD_BASE_URL}"
        f"/buscaPdfManifestoPorCodigoBarras/{codigo_barras}"
    )


    try:
        download_response = session.post(
            download_url,
            headers={
                "Accept": "application/pdf",
                "Content-Type": "application/pdf",
                "Authorization": f"Bearer {token}"
            },
            timeout=60
        )
    except requests.RequestException as error:
        raise HTTPException(
            status_code=502,
            detail=(
                "Erro de comunicação com a SEMAD "
                f"durante o download: {str(error)}"
            )
        )

    return download_response

#buscar_transportador_semad('39228967000160')
#buscar_destino_semad('39228967000160')
#buscar_armazenador_semad('39228967000160')