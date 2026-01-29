from datetime import datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests

app = FastAPI(
    title="API FEAM - Consulta MTR",
    version="1.0.0"
)

FEAM_BASE_URL = "https://mtr.meioambiente.mg.gov.br/api"


class ConsultaMTRRequest(BaseModel):
    cnpj: str
    senha: str
    unidadeGerador: int
    codigoDeBarras: str


def gerar_token_feam(cnpj: str, senha: str, unidade: int):
    url = f"{FEAM_BASE_URL}/gettoken"

    payload = {
        "pessoaCodigo": unidade,
        "pessoaCnpj": cnpj,
        "usuarioCpf": "13280058600",  # ⚠️ Ajuste se for dinâmico no futuro
        "senha": senha
    }

    headers = {
        "Content-Type": "application/json"
    }

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


def consultar_manifesto(codigo_barras: str, token: str, chave: str):
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


@app.post("/feam/mtr/retorna-manifesto-codigo-de-barras")
def buscar_mtr(dados: ConsultaMTRRequest):
    try:
        token, chave = gerar_token_feam(
            cnpj=dados.cnpj,
            senha=dados.senha,
            unidade=dados.unidadeGerador
        )

        manifesto = consultar_manifesto(
            codigo_barras=dados.codigoDeBarras,
            token=token,
            chave=chave
        )

        return {
            "sucesso": True,
            "dados": manifesto
        }

    except HTTPException as e:
        raise e

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.get("/healthz")
def healthcheck():
    return {
        "status": "ok",
        "service": "api-feam-mtr",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
