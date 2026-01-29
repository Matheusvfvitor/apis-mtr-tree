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

    return data
