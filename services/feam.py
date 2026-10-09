import logging

import requests
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict

FEAM_BASE_URL = "https://mtr.meioambiente.mg.gov.br/api"
logger = logging.getLogger("feam")


def _feam_mask_identifier(value: str) -> str:
    digits = "".join(char for char in str(value or "") if char.isdigit())
    return f"***{digits[-4:]}" if len(digits) >= 4 else "***"


def _feam_response_preview(text: str, secrets=()) -> str:
    preview = str(text or "")
    for secret in secrets:
        secret = str(secret or "")
        if secret:
            preview = preview.replace(secret, "<REDACTED>")
    return " ".join(preview.split())[:400]


# =========================
# Schema de entrada FEAM
# =========================
class ConsultaFeamManifestoRequest(BaseModel):
    cpf: str
    cnpj: str
    senha: str
    unidadeGerador: int
    codigoDeBarras: str
    model_config = ConfigDict(extra="forbid")

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
def gerar_token_feam(cpf: str, cnpj: str, senha: str, unidade: int):
    url = f"{FEAM_BASE_URL}/gettoken"

    payload = {
        "pessoaCodigo": unidade,
        "pessoaCnpj": cnpj,
        "usuarioCpf": cpf,
        "senha": senha
    }

    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
    except requests.Timeout:
        raise HTTPException(
            status_code=504,
            detail="Timeout na comunicação com a FEAM (token).",
        )
    except requests.RequestException:
        raise HTTPException(
            status_code=502,
            detail="Erro de comunicação com a FEAM (token).",
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code
            if response.status_code in (401, 403) or response.status_code >= 500
            else 502,
            detail="Erro ao gerar token na FEAM",
        )

    data = response.json()

    if "token" not in data or "chave" not in data:
        raise HTTPException(
            status_code=401,
            detail="Falha na autenticação FEAM.",
        )

    return data["token"], data["chave"]


# =========================
# Consulta Manifesto FEAM
# =========================
def retorna_manifesto_feam(
    cpf: str,
    cnpj: str,
    senha: str,
    unidade: int,
    codigo_barras: str
):
    token, chave = gerar_token_feam(
        cpf=cpf,
        cnpj=cnpj,
        senha=senha,
        unidade=unidade,
    )

    url = f"{FEAM_BASE_URL}/retornaManifesto/{codigo_barras}"

    headers = {
        "Authorization": f"Bearer {token}",
        "chave_feam": chave
    }

    try:
        response = requests.post(url, headers=headers, timeout=30)
    except requests.Timeout:
        raise HTTPException(
            status_code=504,
            detail="Timeout na comunicação com a FEAM (manifesto).",
        )
    except requests.RequestException:
        raise HTTPException(
            status_code=502,
            detail="Erro de comunicação com a FEAM (manifesto).",
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code
            if response.status_code in (401, 403) or response.status_code >= 500
            else 502,
            detail="Erro ao consultar manifesto na FEAM",
        )

    return response.json()


# =========================
# Serviço de cookies FEAM
# =========================
def get_cookies_feam(
    cpf: str,
    cnpj: str,
    unidade: str,
    senha: str,
    context: str = "feam",
):
    url = (
        "https://scheduler-python-dmr-webservice.4ps3wk.easypanel.host"
        f"/feam-login?cnpj={cnpj}&senha={senha}&cpf={cpf}&unidadeCodigo={unidade}"
    )

    started_at = time.perf_counter()
    logger.info(
        "step=cookie_login.start context=%s cnpj=%s unidade=%s",
        context,
        _feam_mask_identifier(cnpj),
        unidade,
    )

    try:
        response = requests.get(url, timeout=60)
    except requests.RequestException as e:
        logger.error(
            "step=cookie_login.transport_error context=%s cnpj=%s error_type=%s elapsed_ms=%.0f",
            context,
            _feam_mask_identifier(cnpj),
            type(e).__name__,
            (time.perf_counter() - started_at) * 1000,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Erro ao comunicar com serviço Selenium FEAM: {str(e)}",
        ) from e

    logger.info(
        "step=cookie_login.response context=%s cnpj=%s http_status=%s elapsed_ms=%.0f content_type=%s",
        context,
        _feam_mask_identifier(cnpj),
        response.status_code,
        (time.perf_counter() - started_at) * 1000,
        response.headers.get("Content-Type", ""),
    )

    if response.status_code != 200:
        logger.warning(
            "step=cookie_login.rejected context=%s cnpj=%s http_status=%s body=%s",
            context,
            _feam_mask_identifier(cnpj),
            response.status_code,
            _feam_response_preview(response.text, (cpf, cnpj, unidade, senha)),
        )
        raise HTTPException(
            status_code=502,
            detail="Falha ao autenticar na FEAM"
        )

    try:
        data = response.json()
    except ValueError:
        logger.warning(
            "step=cookie_login.invalid_json context=%s cnpj=%s body=%s",
            context,
            _feam_mask_identifier(cnpj),
            _feam_response_preview(response.text, (cpf, cnpj, unidade, senha)),
        )
        raise

    cookies = data.get("cookies")

    if not cookies:
        logger.warning(
            "step=cookie_login.cookies_missing context=%s cnpj=%s response_keys=%s",
            context,
            _feam_mask_identifier(cnpj),
            sorted(data.keys()) if isinstance(data, dict) else type(data).__name__,
        )
        raise HTTPException(
            status_code=401,
            detail="Cookies não retornados pela FEAM"
        )

    # Converte lista → dict por nome
    cookies_map = {c["name"]: c["value"] for c in cookies}

    if "JSESSIONID" not in cookies_map:
        logger.warning(
            "step=cookie_login.jsessionid_missing context=%s cnpj=%s cookie_names=%s",
            context,
            _feam_mask_identifier(cnpj),
            sorted(cookies_map.keys()),
        )
        raise HTTPException(
            status_code=401,
            detail="JSESSIONID não encontrado nos cookies FEAM"
        )

    logger.info(
        "step=cookie_login.success context=%s cnpj=%s cookie_names=%s jsessionid_present=true",
        context,
        _feam_mask_identifier(cnpj),
        sorted(cookies_map.keys()),
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

import re
import time
import json
from typing import Any, Dict, List, Optional, Tuple, Union

import requests
from requests.adapters import HTTPAdapter, Retry
from bs4 import BeautifulSoup
from fastapi import HTTPException
from pydantic import BaseModel


#==========================================================================================
# BUSCA DECLARAÇÃO
#==========================================================================================

BASE_URL_DECLARACAO = "https://mtr.meioambiente.mg.gov.br/ControllerServlet"


# =====================
# Utils de parsing
# =====================
def _text(node) -> str:
    return re.sub(r'\s+', ' ', (node.get_text(strip=True) if node else '')).strip()


def _find_input_value(soup: BeautifulSoup, input_id: str) -> Optional[str]:
    el = soup.select_one(f'#{re.escape(input_id)}')
    if el and el.get('value') is not None:
        return str(el.get('value')).strip()
    return None


def _ptbr_to_float(s: str) -> Optional[float]:
    if not s:
        return None
    s = s.strip().replace('.', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None


# =====================
# Parse HTML da DMR
# =====================
def parse_dmr_page(html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, 'lxml')

    header = {
        "tipoDeclaracao": _text(soup.select_one('#lblSemestre')) or "DMR",
        "dataInicial": _find_input_value(soup, 'txtDataInicial') or '',
        "dataFinal": _find_input_value(soup, 'txtDataFinal') or '',
    }

    perfil = _text(soup.select_one('#spanPerfil'))

    dados_gerador = {
        "declarantePerfil": perfil,
        "cnpjRazaoOuCpfNome": "",
        "telefone": "",
        "loNumero": _find_input_value(soup, 'idLao') or "",
        "endereco": "",
        "fax": "",
        "codigoAtividade": _find_input_value(soup, 'idAtividade') or "",
        "municipio": "",
        "estado": "",
        "dataValidade": _find_input_value(soup, 'txtDataValidade') or "",
        "responsavel": _find_input_value(soup, 'txtNomeResp') or "",
        "cargoResponsavel": _find_input_value(soup, 'txtCargoResp') or "",
        "responsavelLegal": _find_input_value(soup, 'txtNomeRespLegal') or "",
    }

    residuos: List[Dict[str, Any]] = []
    tb = soup.select_one('#tbResiduo')

    if tb:
        for tr in tb.find_all('tr'):
            tds = tr.find_all('td')
            if len(tds) < 8:
                continue

            residuos.append({
                "destinador": _text(tds[0]),
                "denominacaoResiduos": _text(tds[1]),
                "classe": _text(tds[2]),
                "quantidadeDestinada": _ptbr_to_float(_text(tds[3])),
                "quantidadeGerada": _ptbr_to_float(
                    tds[4].find('input').get('value') if tds[4].find('input') else ''
                ),
                "quantidadeArmazenada": _ptbr_to_float(_text(tds[5])),
                "unidade": _text(tds[6]),
                "tecnologia": _text(tds[7]),
            })

    observacoes = _find_input_value(soup, 'txtObservacoes') or ''

    return {
        "cabecalho": header,
        "dadosGerador": dados_gerador,
        "residuos": residuos,
        "observacoes": observacoes.strip(),
    }


# =====================
# Session com retries
# =====================
def _session_with_retries() -> requests.Session:
    s = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=0.6,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.mount("http://", HTTPAdapter(max_retries=retries))
    return s


# =====================
# Schema API
# =====================
class BuscarDeclaracaoDMRRequest(BaseModel):
    idDeclaracao: Union[str, int]
    condicao: Union[str, int]
    JSESSIONID: str


# =====================
# Busca + Parse da Declaração
# =====================
def buscar_declaracao_dmr(
    id_declaracao: Union[str, int],
    condicao: Union[str, int],
    jsessionid: str,
    timeout: int = 30,
) -> Dict[str, Any]:

    params = {
        "acao": "buscaDeclaracao",
        "idDeclaracao": str(id_declaracao),
        "condicao": str(condicao),
    }

    cookies = {
        "JSESSIONID": jsessionid
    }

    session = _session_with_retries()

    try:
        resp = session.get(
            BASE_URL_DECLARACAO,
            params=params,
            cookies=cookies,
            timeout=timeout,
            allow_redirects=True,
        )
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Erro de comunicação com FEAM (busca declaração): {str(e)}"
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Erro FEAM HTTP {resp.status_code}"
        )

    html = resp.content.decode("utf-8", errors="ignore")
    return parse_dmr_page(html)



#==========================================================================================
# BUSCA PARCEIROS
#==========================================================================================

def _registrar_resposta_parceiro_feam(response, tipo: str, cnpj: str, started_at: float):
    cnpj_log = _feam_mask_identifier(cnpj)
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    logger.info(
        "step=partner_lookup.upstream_response tipo=%s cnpj=%s http_status=%s elapsed_ms=%.0f content_type=%s",
        tipo,
        cnpj_log,
        response.status_code,
        elapsed_ms,
        response.headers.get("Content-Type", ""),
    )

    if response.status_code != 200:
        logger.warning(
            "step=partner_lookup.upstream_rejected tipo=%s cnpj=%s http_status=%s body=%s",
            tipo,
            cnpj_log,
            response.status_code,
            _feam_response_preview(response.text, (cnpj,)),
        )
        raise HTTPException(
            status_code=502,
            detail=f"Erro FEAM HTTP {response.status_code}"
        )

    try:
        result = response.json()
    except ValueError:
        logger.warning(
            "step=partner_lookup.invalid_json tipo=%s cnpj=%s body=%s",
            tipo,
            cnpj_log,
            _feam_response_preview(response.text, (cnpj,)),
        )
        raise

    result_keys = sorted(result.keys()) if isinstance(result, dict) else []
    logger.info(
        "step=partner_lookup.success tipo=%s cnpj=%s response_type=%s response_keys=%s elapsed_ms=%.0f",
        tipo,
        cnpj_log,
        type(result).__name__,
        result_keys,
        elapsed_ms,
    )
    return result

# =====================
# Busca Transportador
# =====================

def buscar_transportador_feam(cnpj):
    started_at = time.perf_counter()
    cnpj_log = _feam_mask_identifier(cnpj)
    logger.info("step=partner_lookup.start tipo=transportador cnpj=%s tipo_pessoa=2", cnpj_log)
    
    cookies = get_cookies_feam('04304532642','39228967000160', '201050', 'T2m@2024', context='partner:transportador')
    logger.info(
        "step=partner_lookup.cookies_ready tipo=transportador cnpj=%s cookie_names=%s",
        cnpj_log,
        sorted(name for name, value in cookies.items() if value),
    )
    
    params = {
    "acao": "buscaPessoaPorTipo",
    "cnpj": str(cnpj),
    "tipoPessoa": str(2),
    }
    
    session = _session_with_retries()
    timeout: int = 30
    request_started_at = time.perf_counter()
    logger.info("step=partner_lookup.upstream_request.start tipo=transportador cnpj=%s", cnpj_log)
    
    try:
        resp = session.post(
            'https://mtr.meioambiente.mg.gov.br/ControllerServlet',
            params=params,
            cookies=cookies,
            timeout=timeout,
            allow_redirects=True,
        )
    except requests.RequestException as e:
        logger.error(
            "step=partner_lookup.upstream_request.transport_error tipo=transportador cnpj=%s error_type=%s elapsed_ms=%.0f",
            cnpj_log,
            type(e).__name__,
            (time.perf_counter() - request_started_at) * 1000,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Erro de comunicação com FEAM (busca declaração): {str(e)}"
        )

    result = _registrar_resposta_parceiro_feam(
        resp, "transportador", cnpj, request_started_at,
    )
    logger.info(
        "step=partner_lookup.complete tipo=transportador cnpj=%s total_elapsed_ms=%.0f",
        cnpj_log,
        (time.perf_counter() - started_at) * 1000,
    )
    return result

          
# =====================
# Busca Armazenador
# =====================

def buscar_armazenador_feam(cnpj):
    started_at = time.perf_counter()
    cnpj_log = _feam_mask_identifier(cnpj)
    logger.info("step=partner_lookup.start tipo=armazenador cnpj=%s tipo_pessoa=2", cnpj_log)
    
    cookies = get_cookies_feam('04304532642','39228967000160', '201050', 'T2m@2024', context='partner:armazenador')
    logger.info(
        "step=partner_lookup.cookies_ready tipo=armazenador cnpj=%s cookie_names=%s",
        cnpj_log,
        sorted(name for name, value in cookies.items() if value),
    )
    
    params = {
    "acao": "buscaPessoaPorTipo",
    "cnpj": str(cnpj),
    "tipoPessoa": str(2),
    "codigoUnidade": "",
    "armazenador": "S"
    }
    
    session = _session_with_retries()
    timeout: int = 30
    request_started_at = time.perf_counter()
    logger.info("step=partner_lookup.upstream_request.start tipo=armazenador cnpj=%s", cnpj_log)
    
    try:
        resp = session.post(
            'https://mtr.meioambiente.mg.gov.br/ControllerServlet',
            params=params,
            cookies=cookies,
            timeout=timeout,
            allow_redirects=True,
        )
    except requests.RequestException as e:
        logger.error(
            "step=partner_lookup.upstream_request.transport_error tipo=armazenador cnpj=%s error_type=%s elapsed_ms=%.0f",
            cnpj_log,
            type(e).__name__,
            (time.perf_counter() - request_started_at) * 1000,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Erro de comunicação com FEAM (busca declaração): {str(e)}"
        )

    result = _registrar_resposta_parceiro_feam(
        resp, "armazenador", cnpj, request_started_at,
    )
    logger.info(
        "step=partner_lookup.complete tipo=armazenador cnpj=%s total_elapsed_ms=%.0f",
        cnpj_log,
        (time.perf_counter() - started_at) * 1000,
    )
    return result
# =====================
# Busca Destino
# =====================

def buscar_destino_feam(cnpj):
    started_at = time.perf_counter()
    cnpj_log = _feam_mask_identifier(cnpj)
    logger.info("step=partner_lookup.start tipo=destino cnpj=%s tipo_pessoa=4", cnpj_log)
    
    cookies = get_cookies_feam('04304532642','39228967000160', '201050', 'T2m@2024', context='partner:destino')
    logger.info(
        "step=partner_lookup.cookies_ready tipo=destino cnpj=%s cookie_names=%s",
        cnpj_log,
        sorted(name for name, value in cookies.items() if value),
    )
    
    params = {
    "acao": "buscaPessoaPorTipo",
    "cnpj": str(cnpj),
    "tipoPessoa": str(4),
    }
    
    session = _session_with_retries()
    timeout: int = 30
    request_started_at = time.perf_counter()
    logger.info("step=partner_lookup.upstream_request.start tipo=destino cnpj=%s", cnpj_log)
    
    try:
        resp = session.post(
            'https://mtr.meioambiente.mg.gov.br/ControllerServlet',
            params=params,
            cookies=cookies,
            timeout=timeout,
            allow_redirects=True,
        )
    except requests.RequestException as e:
        logger.error(
            "step=partner_lookup.upstream_request.transport_error tipo=destino cnpj=%s error_type=%s elapsed_ms=%.0f",
            cnpj_log,
            type(e).__name__,
            (time.perf_counter() - request_started_at) * 1000,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Erro de comunicação com FEAM (busca declaração): {str(e)}"
        )

    result = _registrar_resposta_parceiro_feam(
        resp, "destino", cnpj, request_started_at,
    )
    logger.info(
        "step=partner_lookup.complete tipo=destino cnpj=%s total_elapsed_ms=%.0f",
        cnpj_log,
        (time.perf_counter() - started_at) * 1000,
    )
    return result
            

#buscar_transportador_feam('39228967000160')
#buscar_armazenador_feam('39228967000160')
#buscar_destino_feam('10880302000155')
