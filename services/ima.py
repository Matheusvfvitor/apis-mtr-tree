from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
from typing import Dict, Tuple, Optional, Union, Any
from urllib.parse import urlparse
import logging
import json





class ConsultaIMAManifestoRequest(BaseModel):
    cpf: str
    cnpj: str
    senha: str
    unidadeGerador: str
    codigoBarras: str



# ==========================================================
# Configuração do workaround da API IMA
# ==========================================================

IMA_WORKAROUND_ENABLED = False


logger = logging.getLogger("ima")
logger.setLevel(logging.INFO)

def consultar_manifesto_ima(
    codigo_barras: str,
    unidade_gerador: str,
    senha: str,
    cnpj: str
):
    url = (
        f"https://mtr.ima.sc.gov.br/mtrservice/retornaManifesto/"
        f"{codigo_barras}/{unidade_gerador}/{senha}/{cnpj}"
    )

    headers = {
        "Content-Type": "application/json"
    }

    response = requests.post(url, headers=headers, timeout=30)

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="Erro ao consultar manifesto no IMA"
        )

    return response.json()

def autenticar_e_obter_cookies(
    cnpj: str,
    senha: str,
    cpf_usuario: str,
    unidade_codigo: str = "",
    timeout: int = 30,
) -> Tuple[Dict[str, str], str, requests.Session]:
    
    s = requests.Session()
    
    LOGIN_URL = "https://mtr.ima.sc.gov.br/ControllerServlet"


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
    
    print('cookies', cookies)

    return cookies, resp.text, s

def buscar_parceiro_ima(
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
        "Origin": "https://mtr.ima.sc.gov.br/",
        "Referer": "https://mtr.ima.sc.gov.br/ControllerServlet?acao=cadastroManifesto",
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

    BASE_URL = "https://mtr.ima.sc.gov.br/ControllerServlet"


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
# BUSCAR TRANSPORTADOR
# =========================

def buscar_transportador_ima(cnpj):
    print('\n===================BUSCANDO TRANSPORTADOR ========\n')

    print('\n===================BUSCANDO OS COOKIES =============')
    cookies = login_ima()  # deve retornar dict: {"JSESSIONID": "...", "route": "..."}
    if not isinstance(cookies, dict):
        raise RuntimeError(f"login_ima retornou algo inesperado: {type(cookies)} -> {cookies!r}")

    jsid = cookies.get("JSESSIONID")
    route = cookies.get("route")

    print('\n-------------------Cookies capturados --------------')
    print('JSESSIONID', jsid)
    print('route', route)
    print('---------------------------------------------------\n')

    if not jsid:
        raise RuntimeError(f"Cookie JSESSIONID não veio no login_ima: {cookies!r}")

    # ✅ Reaproveita uma Session e injeta cookies uma única vez
    s = requests.Session()
    s.cookies.update(cookies)

    # ✅ Chama o endpoint real do IMA usando a session com cookies
    r = buscar_parceiro_ima(
        cookies=s.cookies,     # pode passar o CookieJar da session (ou o dict cookies)
        cnpj=cnpj,
        tipo_pessoa="2",
        session=s,             # recomendado (reutiliza conexão + cookies)
        timeout=30
    )

    print('\n======= Resposta =========')
    print(r)
    print('==========================\n')

    return r

# =========================
# BUSCAR DESTINO
# =========================
  
def buscar_destino_ima(cnpj):
    print('\n===================BUSCANDO DESTINO ========\n')

    print('\n===================BUSCANDO OS COOKIES =============')
    cookies = login_ima()  # deve retornar dict: {"JSESSIONID": "...", "route": "..."}
    if not isinstance(cookies, dict):
        raise RuntimeError(f"login_ima retornou algo inesperado: {type(cookies)} -> {cookies!r}")

    jsid = cookies.get("JSESSIONID")
    route = cookies.get("route")

    print('\n-------------------Cookies capturados --------------')
    print('JSESSIONID', jsid)
    print('route', route)
    print('---------------------------------------------------\n')

    if not jsid:
        raise RuntimeError(f"Cookie JSESSIONID não veio no login_ima: {cookies!r}")

    # ✅ Reaproveita uma Session e injeta cookies uma única vez
    s = requests.Session()
    s.cookies.update(cookies)

    # ✅ Chama o endpoint real do IMA usando a session com cookies
    r = buscar_parceiro_ima(
        cookies=s.cookies,     # pode passar o CookieJar da session (ou o dict cookies)
        cnpj=cnpj,
        tipo_pessoa="4",
        session=s,             # recomendado (reutiliza conexão + cookies)
        timeout=30
    )

    print('\n======= Resposta =========')
    print(r)
    print('==========================\n')

    return r

# =========================
# BUSCAR ARMAZENADOR
# =========================
  
def buscar_armazenador_ima(cnpj):
    print('\n===================BUSCANDO ARMAZENADOR ========\n')

    print('\n===================BUSCANDO OS COOKIES =============')
    cookies = login_ima()  # deve retornar dict: {"JSESSIONID": "...", "route": "..."}
    if not isinstance(cookies, dict):
        raise RuntimeError(f"login_ima retornou algo inesperado: {type(cookies)} -> {cookies!r}")

    jsid = cookies.get("JSESSIONID")
    route = cookies.get("route")

    print('\n-------------------Cookies capturados --------------')
    print('JSESSIONID', jsid)
    print('route', route)
    print('---------------------------------------------------\n')

    if not jsid:
        raise RuntimeError(f"Cookie JSESSIONID não veio no login_ima: {cookies!r}")

    # ✅ Reaproveita uma Session e injeta cookies uma única vez
    s = requests.Session()
    s.cookies.update(cookies)

    # ✅ Chama o endpoint real do IMA usando a session com cookies
    r = buscar_parceiro_ima(
        cookies=s.cookies,     # pode passar o CookieJar da session (ou o dict cookies)
        cnpj=cnpj,
        tipo_pessoa="2",
        armazenador=True,
        session=s,             # recomendado (reutiliza conexão + cookies)
        timeout=30
    )

    print('\n======= Resposta =========')
    print(r)
    print('==========================\n')

    return r
 

def validar_url_salvar_manifesto_ima(
    url: str,
) -> tuple[str, str]:
    """
    Valida o endpoint real de salvamento em lote do IMA.

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
            detail=f"URL ou porta inválida: {str(error)}",
        )

    if parsed_url.scheme.lower() != "https":
        raise HTTPException(
            status_code=400,
            detail="A URL do IMA deve utilizar HTTPS.",
        )

    hostname = (parsed_url.hostname or "").strip().lower()

    if hostname != "mtr.ima.sc.gov.br":
        raise HTTPException(
            status_code=403,
            detail="Host da API IMA não autorizado.",
        )

    if parsed_port not in (None, 443):
        raise HTTPException(
            status_code=403,
            detail="Porta da API IMA não autorizada.",
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

    path = parsed_url.path.rstrip("/")

    if path != "/api/salvarManifestoLote":
        raise HTTPException(
            status_code=400,
            detail=(
                "Endpoint inválido. Esperado: "
                "/mtrservice/salvarManifestoLote"
            ),
        )
        

    url_validada = (
        "https://mtr.ima.sc.gov.br"
        "/mtrservice/salvarManifestoLote"
    )

    return "salvarManifestoLote", url_validada

def salvar_manifesto_ima(
    url: str,
    manifesto: dict,
) -> requests.Response:
    
    endpoint, url_mascarada = validar_url_salvar_manifesto_ima(url)

    modo = (
        "relay-local"
        if IMA_WORKAROUND_ENABLED
        else "direto"
    )

    destino_url = ""

    try:
        payload_ima = json.dumps(
            manifesto,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

    except (TypeError, ValueError) as error:
        logger.error(
            "API IMA Manifesto inválido para serialização | erro=%s",
            str(error),
        )

        raise HTTPException(
            status_code=400,
            detail=f"Manifesto inválido para serialização JSON: {str(error)}",
        )

    logger.info(
        "API IMA Salvamento de manifesto iniciado | "
        "modo=%s | endpoint=%s | url=%s | tamanho_payload=%s",
        modo,
        endpoint,
        url_mascarada,
        len(payload_ima),
    )

    # Evita registrar todo o manifesto, pois o objeto pode conter
    # informações pessoais ou operacionais sensíveis.
    logger.info(
        "API IMA Campos do manifesto | campos=%s",
        sorted(manifesto.keys()),
    )

    try:
        destino_url = url

        logger.info(
            "API IMA Salvamento direto no IMA | "
            "endpoint=%s | url=%s",
            endpoint,
            url_mascarada,
        )

        response_ima = requests.post(
            url=destino_url,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "application/json, text/plain, */*",
                "User-Agent": "Tree-ESG-API/1.0",
                "Connection": "close",
            },
            data=payload_ima,
            timeout=(15, 90),
            allow_redirects=False,
        )
    except HTTPException:
        raise

    except requests.ConnectTimeout as error:
        logger.error(
            "API IMA Timeout de conexão ao salvar manifesto | "
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
                if IMA_WORKAROUND_ENABLED
                else "Timeout ao estabelecer conexão com a API do IMA."
            ),
        )

    except requests.ReadTimeout as error:
        logger.error(
            "[API IMA] Timeout de resposta ao salvar manifesto | "
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
                if IMA_WORKAROUND_ENABLED
                else "A API do IMA demorou demais para processar o manifesto."
            ),
        )

    except requests.SSLError as error:
        logger.error(
            "API IMA Erro SSL ao salvar manifesto | "
            "modo=%s | destino=%s | endpoint=%s | erro=%s",
            modo,
            destino_url,
            endpoint,
            str(error),
        )

        raise HTTPException(
            status_code=502,
            detail=f"Erro SSL ao salvar manifesto no IMA: {str(error)}",
        )

    except requests.RequestException as error:
        logger.error(
            "API IMA Erro de comunicação ao salvar manifesto | "
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

    conteudo = response_ima.content or b""

    content_type = response_ima.headers.get(
        "Content-Type",
        "application/json; charset=utf-8",
    )

    logger.info(
        "API IMA Salvamento de manifesto finalizado | "
        "modo=%s | destino=%s | endpoint=%s | "
        "status=%s | content_type=%s | tamanho=%s",
        modo,
        destino_url,
        endpoint,
        response_ima.status_code,
        content_type,
        len(conteudo),
    )

    if response_ima.status_code >= 400:
        logger.warning(
            "API IMA Manifesto recusado | "
            "modo=%s | endpoint=%s | status=%s | resposta=%s",
            modo,
            endpoint,
            response_ima.status_code,
            response_ima.text[:1000],
        )

    return response_ima


def login_ima():
    url = "http://scheduler-python-login-ima.4ps3wk.easypanel.host/ima-login"

    params = {
        "cnpj": "39228967000160",
        "senha": "5099ea",
        "unidadeCodigo": "",
        "cpf": "04304532642"
    }

    response = requests.get(url, params=params, timeout=120)
    print("Status:", response.status_code)
    print("Body bruto:", response.text)  # <-- debug

    response.raise_for_status()

    data = response.json()
    print("JSON:", data)

    cookies = data.get("cookies") or {}
    print("Cookies:", cookies)

    return cookies  # <-- retorna cookies sempre



#autenticar_e_obter_cookies('39228967000160','5099ea','04304532642',"")
#buscar_transportador_ima('39228967000160')
#buscar_destino_ima('43059086000130')
#Sbuscar_armazenador_ima('04647090002020')