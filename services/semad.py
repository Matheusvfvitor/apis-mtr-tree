import requests
from fastapi import HTTPException
from pydantic import BaseModel
from typing import Dict, Tuple, Optional, Union, Any

SEMAD_BASE_URL = "https://mtr.meioambiente.go.gov.br/api"


# =========================
# Schema de entrada SEMAD
# =========================
class ConsultaSemadManifestoRequest(BaseModel):
    pessoaCodigo: int
    cnpj: str
    cpf: str
    senha: str
    codigoBarras: str


# =========================
# Passo 1 - Get Token SEMAD
# =========================
def gerar_token_semad(
    pessoa_codigo: int,
    cnpj: str,
    cpf: str,
    senha: str
) -> str:
    url = f"{SEMAD_BASE_URL}/gettoken"

    payload = {
        "pessoaCodigo": pessoa_codigo,
        "pessoaCnpj": cnpj,
        "usuarioCpf": cpf,
        "senha": senha
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
            detail=f"Erro de comunicação com a SEMAD (token): {str(e)}"
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="Erro ao gerar token na SEMAD"
        )

    data = response.json()

    if data.get("retornoCodigo") != 0 or "token" not in data:
        raise HTTPException(
            status_code=401,
            detail=f"Falha na autenticação SEMAD: {data}"
        )

    return data["token"]


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
def retorna_manifesto_semad(
    token: str,
    codigo_barras: str
):
    url = f"{SEMAD_BASE_URL}/retornaManifesto/{codigo_barras}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            timeout=30
        )
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Erro de comunicação com a SEMAD (manifesto): {str(e)}"
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="Erro ao consultar manifesto na SEMAD"
        )

    return response.json()


#buscar_transportador_semad('39228967000160')
#buscar_destino_semad('39228967000160')
#buscar_armazenador_semad('39228967000160')