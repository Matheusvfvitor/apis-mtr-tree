from datetime import datetime
from services.fepam import (ConsultaFepamManifestoRequest, retorna_manifesto_fepam)
from services.feam import (ConsultaFeamManifestoRequest, gerar_token_feam, retorna_manifesto_feam)
from services.ima import(ConsultaIMAManifestoRequest,consultar_manifesto_ima)

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests

app = FastAPI(
    title="API FEAM - Consulta MTR",
    version="1.0.0"
)


# =========================
# FEAM - MG
# =========================
@app.post("/feam/retorna-manifesto")
def feam_retorna_manifesto(dados: ConsultaFeamManifestoRequest):
    try:
        manifesto = retorna_manifesto_feam(
            cnpj=dados.cnpj,
            senha=dados.senha,
            unidade=dados.unidadeGerador,
            codigo_barras=dados.codigoDeBarras
        )

        return {
            "sucesso": True,
            "orgao": "FEAM",
            "dados": manifesto
        }

    except HTTPException as e:
        raise e




@app.post("/ima/retorna-manifesto-codigo-de-barras")
def retorna_manifesto_ima(dados: ConsultaIMAManifestoRequest):
    try:
        manifesto = consultar_manifesto_ima(
            codigo_barras=dados.codigoBarras,
            unidade_gerador=dados.unidadeGerador,
            senha=dados.senha,
            cnpj=dados.cnpj
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


@app.post("/fepam/retorna-manifesto-codigo-de-barras")
def fepam_retorna_manifesto(dados: ConsultaFepamManifestoRequest):
    try:
        manifesto = retorna_manifesto_fepam(
            cnpj=dados.cnpj,
            cpf=dados.cpf,
            senha=dados.senha,
            manifesto_codigo=dados.manifestoCodigo
        )

        return {
            "sucesso": True,
            "orgao": "FEPAM",
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
