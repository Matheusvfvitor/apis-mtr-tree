import requests
from fastapi import HTTPException
from pydantic import BaseModel

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
