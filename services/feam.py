import requests
from fastapi import HTTPException
from pydantic import BaseModel

FEAM_BASE_URL = "https://mtr.meioambiente.mg.gov.br/api"


# =========================
# Schema de entrada FEAM
# =========================
class ConsultaFeamManifestoRequest(BaseModel):
    cnpj: str
    senha: str
    unidadeGerador: int
    codigoDeBarras: str

# =========================
# Schema de entrada Get Cookies
# =========================
class ConsultaFeamCookiesRequest(BaseModel):
    cpf: str
    cnpj: str
    unidade: str
    senha: str

# =========================
# Schema de entrada
# =========================
class AtualizarItensDMRRequest(BaseModel):
    codDeclarante: str
    idDeclaracao: str
    dataInicial: str  # formato: DD/MM/YYYY
    dataFinal: str    # formato: DD/MM/YYYY
    JSESSIONID: str


# =========================
# Token FEAM
# =========================
def gerar_token_feam(cnpj: str, senha: str, unidade: int):
    url = f"{FEAM_BASE_URL}/gettoken"

    payload = {
        "pessoaCodigo": unidade,
        "pessoaCnpj": cnpj,
        "usuarioCpf": "13280058600",  # manter fixo por enquanto
        "senha": senha
    }

    headers = {"Content-Type": "application/json"}

    response = requests.post(url, json=payload, headers=headers, timeout=30)

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="Erro ao gerar token na FEAM"
        )

    data = response.json()

    if "token" not in data or "chave" not in data:
        raise HTTPException(
            status_code=401,
            detail=f"Falha na autenticação FEAM: {data}"
        )

    return data["token"], data["chave"]


# =========================
# Consulta Manifesto FEAM
# =========================
def retorna_manifesto_feam(
    cnpj: str,
    senha: str,
    unidade: int,
    codigo_barras: str
):
    token, chave = gerar_token_feam(cnpj, senha, unidade)

    url = f"{FEAM_BASE_URL}/retornaManifesto/{codigo_barras}"

    headers = {
        "Authorization": f"Bearer {token}",
        "chave_feam": chave
    }

    response = requests.post(url, headers=headers, timeout=30)

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="Erro ao consultar manifesto na FEAM"
        )

    return response.json()


# =========================
# Serviço de cookies FEAM
# =========================
def get_cookies_feam(
    cpf: str,
    cnpj: str,
    unidade: str,
    senha: str
):
    url = (
        "https://scheduler-python-dmr-webservice.4ps3wk.easypanel.host"
        f"/feam-login?cnpj={cnpj}&senha={senha}&cpf={cpf}&unidadeCodigo={unidade}"
    )

    try:
        response = requests.get(url, timeout=60)
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Erro ao comunicar com serviço Selenium FEAM: {str(e)}"
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="Falha ao autenticar na FEAM"
        )

    data = response.json()
    cookies = data.get("cookies")

    if not cookies:
        raise HTTPException(
            status_code=401,
            detail="Cookies não retornados pela FEAM"
        )

    # Converte lista → dict por nome
    cookies_map = {c["name"]: c["value"] for c in cookies}

    if "JSESSIONID" not in cookies_map:
        raise HTTPException(
            status_code=401,
            detail="JSESSIONID não encontrado nos cookies FEAM"
        )

    return {
        "JSESSIONID": cookies_map.get("JSESSIONID"),
        "_ga": cookies_map.get("_ga"),
        "_gid": cookies_map.get("_gid"),
        "_gat": cookies_map.get("_gat"),
        "_gs": cookies_map.get("_gs")
    }


FEAM_DMR_URL = (
    "https://mtr.meioambiente.mg.gov.br/"
    "ControllerServlet?acao=buscaResiduosDeclaracaoNovo"
)

# =========================
# Atualizar Itens DMR
# =========================
def atualizar_itens_dmr(
    cod_declarante: str,
    id_declaracao: str,
    data_inicial: str,
    data_final: str,
    jsessionid: str
):
    headers = {
        "Cookie": f"JSESSIONID={jsessionid}"
    }

    payload = {
        "acao": "buscaResiduosDeclaracaoNovo",
        "codDeclarante": cod_declarante,
        "idDeclaracao": id_declaracao,
        "dataInicial": data_inicial,
        "dataFinal": data_final
    }

    try:
        response = requests.post(
            FEAM_DMR_URL,
            headers=headers,
            data=payload,
            timeout=60
        )
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Erro de comunicação com FEAM (DMR): {str(e)}"
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="Erro ao buscar resíduos da DMR na FEAM"
        )

    # FEAM retorna HTML/texto
    return {
        "status_code": response.status_code,
        "conteudo": response.text
    }

import time
import json
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter, Retry


BASE_URL_LISTA_DMRS = (
    "https://mtr.meioambiente.mg.gov.br/"
    "br/com/brdti/mtr/controller/JqueryDatatablePluginDemo.java"
)

# =========================
# Session com retries
# =========================
def _session_with_retries() -> requests.Session:
    session = requests.Session()

    retries = Retry(
        total=5,
        backoff_factor=0.6,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )

    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


# =========================
# Schema de entrada
# =========================
class ListarDMRRequest(BaseModel):
    JSESSIONID: str
    iDisplayStart: int = 0
    iDisplayLength: int = 10
    sSearch: str = ""
    iColumns: int = 7
    sEcho: int = 1
    tabela: str = "DMR"


# =========================
# Listar DMR (DataTable)
# =========================
def listar_dmrs(
    jsessionid: str,
    i_display_start: int,
    i_display_length: int,
    s_search: str,
    i_columns: int,
    s_echo: int,
    tabela: str,
    timeout: int = 30,
) -> Dict[str, Any]:

    params = {
        "tabela": tabela,
        "sEcho": s_echo,
        "iColumns": i_columns,
        "sColumns": "",
        "iDisplayStart": i_display_start,
        "iDisplayLength": i_display_length,
        "sSearch": s_search,
        "_": int(time.time() * 1000),  # cache bust
    }

    cookies = {
        "JSESSIONID": jsessionid
    }

    session = _session_with_retries()

    try:
        resp = session.get(
            BASE_URL_LISTA_DMRS,
            params=params,
            cookies=cookies,
            timeout=timeout,
        )
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Erro de comunicação com FEAM (listar DMR): {str(e)}"
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Erro FEAM HTTP {resp.status_code}"
        )

    # Parsing resiliente
    try:
        return resp.json()
    except json.JSONDecodeError:
        txt = resp.text.strip()
        try:
            return json.loads(txt)
        except Exception:
            raise HTTPException(
                status_code=502,
                detail=f"Resposta FEAM não-JSON: {txt[:800]}"
            )
