import requests
from fastapi import HTTPException
from pydantic import BaseModel
from typing import Any

CPRH_BASE_URL = "https://homologa-mtr.cprh.pe.gov.br/api"

CPRH_HOST = "https://mtr.cprh.pe.gov.br"
CPRH_CONTROLLER_URL = f"{CPRH_HOST}/ControllerServlet"

CPRH_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)

# =========================
# Credenciais de serviço CPRH (Busca Parceiro)
# =========================
CPRH_SERVICO_CNPJ = "39228967000160"
CPRH_SERVICO_CPF = "13280058600"
CPRH_SERVICO_SENHA = "Tree@2026"
CPRH_SERVICO_UNIDADE_CODIGO = "9071"


# =========================
# Schemas de entrada CPRH
# =========================
class ConsultaCprhManifestoRequest(BaseModel):
    pessoaCodigo: int
    cnpj: str
    cpf: str
    senha: str
    codigoBarras: str


class EmitirManifestoCprhRequest(BaseModel):
    pessoaCodigo: int
    cnpj: str
    cpf: str
    senha: str
    manifestoJSONDtos: list[dict[str, Any]]


class CancelarManifestoCprhRequest(BaseModel):
    pessoaCodigo: int
    cnpj: str
    cpf: str
    senha: str
    manifestoCodigo: str
    justificativa: str


class DownloadManifestoCprhRequest(BaseModel):
    pessoaCodigo: int
    cnpj: str
    cpf: str
    senha: str
    codigoBarras: str


class DownloadCdfCprhRequest(BaseModel):
    pessoaCodigo: int
    cnpj: str
    cpf: str
    senha: str
    numeroCdf: str


# =========================
# Passo 1 - Get Token CPRH
# =========================
def gerar_token_cprh(
    pessoa_codigo: int,
    cnpj: str,
    cpf: str,
    senha: str,
) -> str:
    url = f"{CPRH_BASE_URL}/gettoken"

    payload = {
        "pessoaCodigo": pessoa_codigo,
        "pessoaCnpj": cnpj,
        "usuarioCpf": cpf,
        "senha": senha,
    }

    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Erro de comunicação com a CPRH (token): {str(e)}")

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Erro ao gerar token na CPRH")

    data = response.json()

    if data.get("retornoCodigo") != 0 or "token" not in data:
        raise HTTPException(status_code=401, detail=f"Falha na autenticação CPRH: {data}")

    return data["token"]


# =========================
# Emitir MTR (Salvar Manifesto em Lote)
# =========================
def emitir_manifesto_cprh(
    pessoa_codigo: int,
    cnpj: str,
    cpf: str,
    senha: str,
    manifesto_json_dtos: list[dict[str, Any]],
) -> dict:
    token = gerar_token_cprh(pessoa_codigo=pessoa_codigo, cnpj=cnpj, cpf=cpf, senha=senha)

    url = f"{CPRH_BASE_URL}/salvarManifestoLote"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    payload = {"manifestoJSONDtos": manifesto_json_dtos}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Erro de comunicação com a CPRH (emitir MTR): {str(e)}")

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Erro ao emitir MTR na CPRH: HTTP {response.status_code}",
        )

    return response.json()


# =========================
# Cancelar MTR
# =========================
def cancelar_manifesto_cprh(
    pessoa_codigo: int,
    cnpj: str,
    cpf: str,
    senha: str,
    manifesto_codigo: str,
    justificativa: str,
) -> dict:
    token = gerar_token_cprh(pessoa_codigo=pessoa_codigo, cnpj=cnpj, cpf=cpf, senha=senha)

    url = f"{CPRH_BASE_URL}/cancelarManifesto"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    payload = {
        "manifestoCodigo": manifesto_codigo,
        "justificativa": justificativa,
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Erro de comunicação com a CPRH (cancelar MTR): {str(e)}")

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Erro ao cancelar MTR na CPRH: HTTP {response.status_code}",
        )

    return response.json()


# =========================
# Download MTR (PDF do Manifesto)
# =========================
def download_manifesto_cprh(
    pessoa_codigo: int,
    cnpj: str,
    cpf: str,
    senha: str,
    codigo_barras: str,
) -> requests.Response:
    token = gerar_token_cprh(pessoa_codigo=pessoa_codigo, cnpj=cnpj, cpf=cpf, senha=senha)

    url = f"{CPRH_BASE_URL}/buscaPdfManifestoPorCodigoBarras/{codigo_barras}"

    headers = {
        "Accept": "application/pdf",
        "Content-Type": "application/pdf",
        "Authorization": f"Bearer {token}",
    }

    try:
        return requests.post(url, headers=headers, timeout=60)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Erro de comunicação com a CPRH (download MTR): {str(e)}")


# =========================
# Download CDF (PDF do Certificado)
# =========================
def download_cdf_cprh(
    pessoa_codigo: int,
    cnpj: str,
    cpf: str,
    senha: str,
    numero_cdf: str,
) -> requests.Response:
    token = gerar_token_cprh(pessoa_codigo=pessoa_codigo, cnpj=cnpj, cpf=cpf, senha=senha)

    url = f"{CPRH_BASE_URL}/buscaPdfCdf/{numero_cdf}"

    headers = {
        "Accept": "application/pdf",
        "Content-Type": "application/pdf",
        "Authorization": f"Bearer {token}",
    }

    try:
        return requests.post(url, headers=headers, timeout=60)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Erro de comunicação com a CPRH (download CDF): {str(e)}")


# =========================
# CheckStatus (Retorna Manifesto por código de barras)
# =========================
def consulta_status_cprh(
    pessoa_codigo: int,
    cnpj: str,
    cpf: str,
    senha: str,
    codigo_barras: str,
) -> dict:
    token = gerar_token_cprh(pessoa_codigo=pessoa_codigo, cnpj=cnpj, cpf=cpf, senha=senha)

    url = f"{CPRH_BASE_URL}/retornaManifesto/{codigo_barras}"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    try:
        response = requests.post(url, headers=headers, timeout=30)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Erro de comunicação com a CPRH (check status): {str(e)}")

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Erro ao consultar status do MTR na CPRH: HTTP {response.status_code}",
        )

    return response.json()


# =========================
# Busca Parceiro (transportador / armazenador / destino)
# =========================
# A CPRH roda no mesmo portal legado (ControllerServlet) usado por
# FEAM/FEPAM/SEMAD para o cadastro de manifesto. Esse endpoint não é
# documentado no manual da API REST da CPRH.
def autenticar_cprh_controller(
    cnpj: str,
    cpf_usuario: str,
    senha: str,
    unidade_codigo: str = "",
) -> requests.Session:
    payload = {
        "acao": "autenticaUsuario",
        "txtCnpj": cnpj,
        "txtSenha": senha,
        "txtUnidadeCodigo": unidade_codigo or "",
        "txtCpfUsuario": cpf_usuario,
        "tipoPessoaSociedade": "J",
    }

    headers = {
        "Accept": "*/*",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": CPRH_HOST,
        "Referer": f"{CPRH_HOST}/",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": CPRH_USER_AGENT,
    }

    session = requests.Session()

    try:
        response = session.post(CPRH_CONTROLLER_URL, data=payload, headers=headers, timeout=30)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Erro de comunicação com a CPRH (login): {str(e)}")

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Erro ao autenticar na CPRH: HTTP {response.status_code}")

    try:
        data = response.json()
    except ValueError:
        data = {}

    sucesso = isinstance(data, dict) and str(data.get("sucesso", "")).lower() == "s"

    if not sucesso and not session.cookies.get_dict():
        raise HTTPException(status_code=401, detail=f"Falha na autenticação CPRH: {data}")

    return session


def buscar_parceiro_cprh(
    session: requests.Session,
    cnpj: str,
    tipo_pessoa: str = "2",
    armazenador: bool = False,
    timeout: int = 30,
) -> dict:
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": CPRH_HOST,
        "Referer": f"{CPRH_HOST}/ControllerServlet?acao=cadastroManifesto",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": CPRH_USER_AGENT,
    }

    if armazenador:
        form_fields = [
            ("acao", "buscaPessoaPorTipo"),
            ("cnpj", cnpj),
            ("tipoPessoa", tipo_pessoa),
            ("codigoUnidade", ""),
            ("armazenador", "S"),
        ]
    else:
        form_fields = [
            ("acao", "buscaPessoaPorTipo"),
            ("cnpj", cnpj),
            ("tipoPessoa", tipo_pessoa),
        ]

    try:
        response = session.post(CPRH_CONTROLLER_URL, headers=headers, data=form_fields, timeout=timeout)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Erro de comunicação com a CPRH (busca parceiro): {str(e)}")

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Erro ao consultar parceiro na CPRH: HTTP {response.status_code}",
        )

    try:
        return response.json()
    except ValueError:
        return {
            "ok": False,
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type"),
            "text": response.text[:2000],
        }


def _autenticar_cprh_servico() -> requests.Session:
    return autenticar_cprh_controller(
        cnpj=CPRH_SERVICO_CNPJ,
        cpf_usuario=CPRH_SERVICO_CPF,
        senha=CPRH_SERVICO_SENHA,
        unidade_codigo=CPRH_SERVICO_UNIDADE_CODIGO,
    )


def buscar_transportador_cprh(cnpj: str) -> dict:
    session = _autenticar_cprh_servico()
    return buscar_parceiro_cprh(session=session, cnpj=cnpj, tipo_pessoa="2")


def buscar_destino_cprh(cnpj: str) -> dict:
    session = _autenticar_cprh_servico()
    return buscar_parceiro_cprh(session=session, cnpj=cnpj, tipo_pessoa="4")


def buscar_armazenador_cprh(cnpj: str) -> dict:
    session = _autenticar_cprh_servico()
    return buscar_parceiro_cprh(session=session, cnpj=cnpj, tipo_pessoa="2", armazenador=True)
