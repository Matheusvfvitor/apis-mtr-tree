import requests
from fastapi import HTTPException
from pydantic import BaseModel

SINIR_BASE_URL = "https://admin.sinir.gov.br/apiws/rest"


# =========================
# Schema de entrada SINIR
# =========================
class ConsultaSinirManifestoRequest(BaseModel):
    cpfCnpj: str
    senha: str
    unidade: str
    manifestoNumero: str


# =========================
# Passo 1 - Get Token SINIR
# =========================
def gerar_token_sinir(cpf_cnpj: str, senha: str, unidade: str) -> str:
    url = f"{SINIR_BASE_URL}/gettoken"

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
            detail=f"Erro de comunicação com o SINIR (token): {str(e)}"
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="Erro ao gerar token no SINIR"
        )

    data = response.json()

    if data.get("erro") is True or "objetoResposta" not in data:
        raise HTTPException(
            status_code=401,
            detail=f"Falha na autenticação SINIR: {data}"
        )

    # objetoResposta já vem como: "Bearer xxxxx"
    return data["objetoResposta"]


# =========================
# Passo 2 - Retorna Manifesto
# =========================
def retorna_manifesto_sinir(
    token_bearer: str,
    manifesto_numero: str
):
    url = f"{SINIR_BASE_URL}/retornaManifesto/{manifesto_numero}"

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
            detail=f"Erro de comunicação com o SINIR (manifesto): {str(e)}"
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="Erro ao consultar manifesto no SINIR"
        )

    return response.json()
