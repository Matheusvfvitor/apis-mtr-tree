from datetime import datetime
from services.fepam import (ConsultaFepamManifestoRequest, retorna_manifesto_fepam)
from services.feam import (ConsultaMTRRequest, gerar_token_feam, consultar_manifesto)
from services.ima import(ConsultaIMAManifestoRequest,retorna_manifesto_ima)

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests

app = FastAPI(
    title="API FEAM - Consulta MTR",
    version="1.0.0"
)


@app.post("/feam/retorna-manifesto-codigo-de-barras")
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
