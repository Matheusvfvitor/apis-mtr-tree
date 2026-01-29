import requests
from fastapi import HTTPException
from pydantic import BaseModel

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
