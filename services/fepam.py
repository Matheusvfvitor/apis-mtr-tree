import requests
from fastapi import HTTPException
from pydantic import BaseModel
from typing import Dict, Tuple, Optional, Union, Any

FEPAM_URL = "https://mtr.fepam.rs.gov.br/mtrservice/retornaManifesto"


# =========================
# Schema de entrada (local)
# =========================
class ConsultaFepamManifestoRequest(BaseModel):
    cpf: str
    cnpj: str
    senha: str
    manifestoCodigo: str


# =========================
# Chamada à API FEPAM
# =========================
def retorna_manifesto_fepam(
    cnpj: str,
    cpf: str,
    senha: str,
    manifesto_codigo: str
):
    payload = {
        "cnp": cnpj,
        "login": cpf,
        "senha": senha,
        "manifestoJSON": {
            "manifestoCodigo": manifesto_codigo
        }
    }

    headers = {
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            FEPAM_URL,
            json=payload,
            headers=headers,
            timeout=30
        )
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Erro de comunicação com a FEPAM: {str(e)}"
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="Erro ao consultar manifesto na FEPAM"
        )

    return response.json()


import requests
from fastapi import HTTPException
from typing import Optional, Tuple, Dict

def autenticar_fepam_e_obter_sessao(
    pessoa_codigo: Optional[str],
    cnpj: str,
    cpf: str,
    senha: str
) -> Tuple[requests.Session, Dict[str, str]]:
    url = "https://mtr.fepam.rs.gov.br/ControllerServlet"

    payload = {
        "acao": "autenticaUsuario",
        "txtUnidadeCodigo": pessoa_codigo or "",
        "txtCnpj": cnpj,
        "txtCpfUsuario": cpf,
        "txtSenha": senha,
        "tipoPessoaSociedade": "J",
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://mtr.fepam.rs.gov.br",
        "Referer": "https://mtr.fepam.rs.gov.br/",
        "Accept": "application/json, text/plain, */*",
    }

    session = requests.Session()

    try:
        resp = session.post(url, data=payload, headers=headers, timeout=30)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Erro de comunicação com a FEPAM (login): {e}")

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Erro ao autenticar na FEPAM: HTTP {resp.status_code}")

    # A FEPAM pode responder {"sucesso":"s"} (como você viu)
    # ou outro JSON. Vamos validar o sucesso sem exigir token.
    try:
        data = resp.json()
    except Exception:
        data = {"raw": resp.text[:500]}

    # ✅ se veio sucesso 's', considera autenticado
    if isinstance(data, dict) and data.get("sucesso") == "s":
        pass
    else:
        # Se não tiver esse flag, você pode adaptar a regra aqui conforme resposta real
        # (ex: data.get("retornoCodigo") == 0 etc.)
        # Por enquanto, só não vamos considerar sucesso.
        raise HTTPException(status_code=401, detail=f"Falha na autenticação FEPAM: {data}")

    # Cookies persistidos no session (inclui JSESSIONID quando existir)
    cookies_dict = session.cookies.get_dict()

    if not cookies_dict:
        # Às vezes vem em Set-Cookie e o Session pega; se não veio nada, vale inspecionar headers
        raise HTTPException(
            status_code=502,
            detail=f"Autenticou mas não capturou cookies. Set-Cookie={resp.headers.get('Set-Cookie')}"
        )

    return session, cookies_dict

def buscar_parceiro_fepam(
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
        "Origin": "https://mtr.fepam.rs.gov.br/ControllerServlet",
        "Referer": "https://mtr.fepam.rs.gov.br/ControllerServlet/ControllerServlet?acao=cadastroManifesto",
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

    BASE_URL = "https://mtr.fepam.rs.gov.br/ControllerServlet"


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

def buscar_transportador_fepam(cnpj):
    print('\n===================BUSCANDO TRANSPORTADOR ========\n')
    
    print('\n===================BUSCANDO OS COOKIES =============')
    session, cookies = autenticar_fepam_e_obter_sessao(
        cnpj="39228967000160",
        senha="T2m@2024",
        cpf="04304532642",
        pessoa_codigo=None
    )
    print('\n-------------------Cookies capturados --------------')
    print('cookies', cookies)
    print('JSESSIONID', cookies.get('JSESSIONID'))
    print('---------------------------------------------------\n')
    
    cookies_login = {
    "JSESSIONID": cookies.get('JSESSIONID'),
    }
    
    r = buscar_parceiro_fepam(
        cookies=cookies_login,
        cnpj=cnpj,
        tipo_pessoa="2",
    )
    print('\n======= Resposta =========')
    print(r)
    print('==========================\n')

    return r


# =========================
# BUSCAR TRANSPORTADOR
# =========================

def buscar_armazenador_fepam(cnpj):
    print('\n===================BUSCANDO ARMAZENADOR ========\n')
    
    print('\n===================BUSCANDO OS COOKIES =============')
    session, cookies = autenticar_fepam_e_obter_sessao(
        cnpj="39228967000160",
        senha="T2m@2024",
        cpf="04304532642",
        pessoa_codigo=None
    )
    print('\n-------------------Cookies capturados --------------')
    print('cookies', cookies)
    print('JSESSIONID', cookies.get('JSESSIONID'))
    print('---------------------------------------------------\n')
    
    cookies_login = {
    "JSESSIONID": cookies.get('JSESSIONID'),
    }
    
    r = buscar_parceiro_fepam(
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
# BUSCAR Destino
# =========================

def buscar_destino_fepam(cnpj):
    print('\n===================BUSCANDO DESTINO ========\n')
    
    print('\n===================BUSCANDO OS COOKIES =============')
    session, cookies = autenticar_fepam_e_obter_sessao(
        cnpj="39228967000160",
        senha="T2m@2024",
        cpf="04304532642",
        pessoa_codigo=None
    )
    print('\n-------------------Cookies capturados --------------')
    print('cookies', cookies)
    print('JSESSIONID', cookies.get('JSESSIONID'))
    print('---------------------------------------------------\n')
    
    cookies_login = {
    "JSESSIONID": cookies.get('JSESSIONID'),
    }
    
    r = buscar_parceiro_fepam(
        cookies=cookies_login,
        cnpj=cnpj,
        tipo_pessoa="4",
    )
    print('\n======= Resposta =========')
    print(r)
    print('==========================\n')

    return r



#buscar_transportador_fepam('19775328000108')
#buscar_armazenador_fepam('80415771000189')
#buscar_destino_fepam('80415771000189')