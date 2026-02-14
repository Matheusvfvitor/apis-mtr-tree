from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
from typing import Dict, Tuple, Optional, Union, Any



class ConsultaIMAManifestoRequest(BaseModel):
    cpf: str
    cnpj: str
    senha: str
    unidadeGerador: str
    codigoBarras: str


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
buscar_transportador_ima('39228967000160')
buscar_destino_ima('43059086000130')
buscar_armazenador_ima('04647090002020')