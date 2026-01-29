import requests
from fastapi import HTTPException
from pydantic import BaseModel

SIGOR_BASE_URL = "https://mtrr.cetesb.sp.gov.br/apiws/rest"


# =========================
# Schema de entrada SIGOR
# =========================
class ConsultaSigorManifestoRequest(BaseModel):
    cpfCnpj: str
    senha: str
    unidade: str
    manifestoNumero: str


# =========================
# Passo 1 - Get Token SIGOR
# =========================
def gerar_token_sigor(cpf_cnpj: str, senha: str, unidade: str) -> str:
    url = f"{SIGOR_BASE_URL}/gettoken"

    payload = {
        "cpfCnpj": cpf_cnpj,
        "senha": senha,
        "unidade": unidade
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
            detail=f"Erro de comunicação com o SIGOR (token): {str(e)}"
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="Erro ao gerar token no SIGOR"
        )

    data = response.json()

    if data.get("erro") is True or "objetoResposta" not in data:
        raise HTTPException(
            status_code=401,
            detail=f"Falha na autenticação SIGOR: {data}"
        )

    # objetoResposta já vem como: "Bearer xxxxx"
    return data["objetoResposta"]


# =========================
# Passo 2 - Retorna Manifesto
# =========================
def retorna_manifesto_sigor(
    token_bearer: str,
    manifesto_numero: str
):
    url = f"{SIGOR_BASE_URL}/retornaManifesto/{manifesto_numero}"

    headers = {
        "Authorization": token_bearer
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=30
        )
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Erro de comunicação com o SIGOR (manifesto): {str(e)}"
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="Erro ao consultar manifesto no SIGOR"
        )

    return response.json()
