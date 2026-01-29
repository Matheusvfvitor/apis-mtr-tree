from datetime import datetime
from services.fepam import (ConsultaFepamManifestoRequest, retorna_manifesto_fepam)
from services.feam import (ConsultaFeamManifestoRequest, gerar_token_feam, retorna_manifesto_feam)
from services.ima import(ConsultaIMAManifestoRequest,consultar_manifesto_ima)
from services.inea import(ConsultaIneaManifestoRequest,retorna_manifesto_inea)
from services.sinir import (ConsultaSinirManifestoRequest, gerar_token_sinir, retorna_manifesto_sinir)
from services.sigor_service import (ConsultaSigorManifestoRequest, gerar_token_sigor,retorna_manifesto_sigor)


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
@app.post("/feam/retorna-manifesto-codigo-de-barras")
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


# =========================
# IMA
# =========================

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

# =========================
# FEPAM
# =========================

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

# =========================
# INEA - RJ
# =========================
@app.post("/inea/retorna-manifesto-codigo-de-barras")
def inea_retorna_manifesto(dados: ConsultaIneaManifestoRequest):
    try:
        manifesto = retorna_manifesto_inea(
            cpf=dados.cpf,
            senha=dados.senha,
            cnpj=dados.cnpj,
            unidade_gerador=dados.unidadeGerador,
            codigo_barras=dados.codigoBarras
        )

        return {
            "sucesso": True,
            "orgao": "INEA",
            "dados": manifesto
        }

    except HTTPException as e:
        raise e


# =========================
# SINIR - Federal
# =========================
@app.post("/sinir/retorna-manifesto")
def sinir_retorna_manifesto(dados: ConsultaSinirManifestoRequest):
    try:
        token = gerar_token_sinir(
            cpf_cnpj=dados.cpfCnpj,
            senha=dados.senha,
            unidade=dados.unidade
        )

        manifesto = retorna_manifesto_sinir(
            token_bearer=token,
            manifesto_numero=dados.manifestoNumero
        )

        return {
            "sucesso": True,
            "orgao": "SINIR",
            "dados": manifesto
        }

    except HTTPException as e:
        raise e

# =========================
# SIGOR / CETESB - SP
# =========================
@app.post("/sigor/retorna-manifesto")
def sigor_retorna_manifesto(dados: ConsultaSigorManifestoRequest):
    try:
        token = gerar_token_sigor(
            cpf_cnpj=dados.cpfCnpj,
            senha=dados.senha,
            unidade=dados.unidade
        )

        manifesto = retorna_manifesto_sigor(
            token_bearer=token,
            manifesto_numero=dados.manifestoNumero
        )

        return {
            "sucesso": True,
            "orgao": "SIGOR",
            "dados": manifesto
        }

    except HTTPException as e:
        raise e


@app.get("/healthz")
def healthcheck():
    return {
        "status": "ok",
        "service": "api-feam-mtr",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
