from datetime import datetime
from services.fepam import (ConsultaFepamManifestoRequest, retorna_manifesto_fepam)
from services.feam import (BuscarDeclaracaoDMRRequest,ListarDMRRequest, AtualizarItensDMRRequest, ConsultaFeamCookiesRequest, ConsultaFeamManifestoRequest,atualizar_itens_dmr, buscar_declaracao_dmr, get_cookies_feam, gerar_token_feam, listar_dmrs, retorna_manifesto_feam)
from services.feam import(buscar_armazenador_feam, buscar_destino_feam, buscar_transportador_feam)
from services.ima import (buscar_armazenador_ima, buscar_destino_ima, buscar_transportador_ima)
from services.fepam import (buscar_armazenador_fepam, buscar_destino_fepam, buscar_transportador_fepam)
from services.sigor import (retorna_dados_armazenador_sigor, retorna_dados_destino_sigor, retorna_dados_transportador_sigor)
from services.sinir import (retorna_dados_transportador_sinir, retorna_dados_armazenador_sinir, retorna_dados_destino_sinir)
from services.semad import (buscar_armazenador_semad, buscar_destino_semad, buscar_transportador_semad)

from services.ima import(ConsultaIMAManifestoRequest,consultar_manifesto_ima)
from services.inea import(ConsultaIneaManifestoRequest,retorna_manifesto_inea)
from services.sinir import (ConsultaSinirManifestoRequest, gerar_token_sinir, retorna_manifesto_sinir)
from services.sigor import (ConsultaSigorManifestoRequest, gerar_token_sigor,retorna_manifesto_sigor)
from services.semad import (ConsultaSemadManifestoRequest,gerar_token_semad,retorna_manifesto_semad)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel
import requests

app = FastAPI(
    title="API FEAM - Consulta MTR",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class BuscaParceiro(BaseModel):
    cnpj: str
    tipoParceiro: str

# ================================================================================================================
# FEAM - MG
# ================================================================================================================

# -------------------------
# FEAM - MG
# -------------------------
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

# -------------------------
# FEAM - Atualizar Itens DMR
# -------------------------
@app.post("/feam/dmr/atualizar-itens")
def feam_atualizar_itens_dmr(dados: AtualizarItensDMRRequest):

    try:

        resultado = atualizar_itens_dmr(
            cod_declarante=dados.codDeclarante,
            id_declaracao=dados.idDeclaracao,
            data_inicial=dados.dataInicial,
            data_final=dados.dataFinal,
            jsessionid=dados.JSESSIONID
        )

        return {
            "sucesso": True,
            "orgao": "FEAM",
            "acao": "ATUALIZAR_ITENS_DMR",
            "dados": resultado
        }

    except HTTPException as e:
        raise e

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# -------------------------
# FEAM - Get Cookies (Selenium)
# -------------------------
@app.post("/feam/get-cookies")
def feam_get_cookies(dados: ConsultaFeamCookiesRequest):

    try:
        cookies = get_cookies_feam(
            cpf=dados.cpf,
            cnpj=dados.cnpj,
            unidade=dados.unidade,
            senha=dados.senha
        )

        return {
            "sucesso": True,
            "orgao": "FEAM",
            "cookies": cookies
        }

    except HTTPException as e:
        raise e

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# -------------------------
# FEAM - Listar DMRs
# -------------------------
@app.post("/feam/dmr/listar")
def feam_listar_dmrs(dados: ListarDMRRequest):

    try:
        resultado = listar_dmrs(
            jsessionid=dados.JSESSIONID,
            i_display_start=dados.iDisplayStart,
            i_display_length=dados.iDisplayLength,
            s_search=dados.sSearch,
            i_columns=dados.iColumns,
            s_echo=dados.sEcho,
            tabela=dados.tabela
        )

        return {
            "sucesso": True,
            "orgao": "FEAM",
            "acao": "LISTAR_DMRS",
            "dados": resultado
        }

    except HTTPException as e:
        raise e

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# =========================
# FEAM - Buscar Declaração DMR
# =========================
@app.post("/feam/dmr/buscar-declaracao")
def feam_buscar_declaracao_dmr(dados: BuscarDeclaracaoDMRRequest):

    try:
        resultado = buscar_declaracao_dmr(
            id_declaracao=dados.idDeclaracao,
            condicao=dados.condicao,
            jsessionid=dados.JSESSIONID
        )

        return {
            "sucesso": True,
            "orgao": "FEAM",
            "acao": "BUSCAR_DECLARACAO_DMR",
            "dados": resultado
        }

    except HTTPException as e:
        raise e

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.post("/feam/busca-parceiro")
def feam_buscar_parceiro(dados: BuscaParceiro):
    tipo = (dados.tipoParceiro or "").strip().lower()

    if tipo == "destino":
        resultado = buscar_destino_feam(dados.cnpj)
    elif tipo == "transportador":
        resultado = buscar_transportador_feam(dados.cnpj)
    elif tipo == "armazenador":
        resultado = buscar_armazenador_feam(dados.cnpj)
    else:
        raise HTTPException(status_code=400, detail="Tipo de parceiro inválido. Use: destino, transportador, armazenador")

    return {"tipoParceiro": tipo, "cnpj": dados.cnpj, "resultado": resultado}
        

# ================================================================================================================
# IMA
# ================================================================================================================

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

@app.post("/ima/busca-parceiro")
def ima_buscar_parceiro(dados: BuscaParceiro):
    tipo = (dados.tipoParceiro or "").strip().lower()

    if tipo == "destino":
        resultado = buscar_destino_ima(dados.cnpj)
    elif tipo == "transportador":
        resultado = buscar_transportador_ima(dados.cnpj)
    elif tipo == "armazenador":
        resultado = buscar_armazenador_ima(dados.cnpj)
    else:
        raise HTTPException(status_code=400, detail="Tipo de parceiro inválido. Use: destino, transportador, armazenador")

    return {"tipoParceiro": tipo, "cnpj": dados.cnpj, "resultado": resultado}

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


@app.post("/fepam/busca-parceiro")
def fepam_buscar_parceiro(dados: BuscaParceiro):
    tipo = (dados.tipoParceiro or "").strip().lower()

    if tipo == "destino":
        resultado = buscar_destino_fepam(dados.cnpj)
    elif tipo == "transportador":
        resultado = buscar_transportador_fepam(dados.cnpj)
    elif tipo == "armazenador":
        resultado = buscar_armazenador_fepam(dados.cnpj)
    else:
        raise HTTPException(status_code=400, detail="Tipo de parceiro inválido. Use: destino, transportador, armazenador")

    return {"tipoParceiro": tipo, "cnpj": dados.cnpj, "resultado": resultado}

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

@app.post("/sinir/busca-parceiro")
def sinir_buscar_parceiro(dados: BuscaParceiro):
    tipo = (dados.tipoParceiro or "").strip().lower()

    if tipo == "destino":
        resultado = retorna_dados_destino_sinir(dados.cnpj)
    elif tipo == "transportador":
        resultado = retorna_dados_transportador_sinir(dados.cnpj)
    elif tipo == "armazenador":
        resultado = retorna_dados_armazenador_sinir(dados.cnpj)
    else:
        raise HTTPException(status_code=400, detail="Tipo de parceiro inválido. Use: destino, transportador, armazenador")

    return {"tipoParceiro": tipo, "cnpj": dados.cnpj, "resultado": resultado}


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

@app.post("/sigor/busca-parceiro")
def sigor_buscar_parceiro(dados: BuscaParceiro):
    tipo = (dados.tipoParceiro or "").strip().lower()

    if tipo == "destino":
        resultado = retorna_dados_destino_sigor(dados.cnpj)
    elif tipo == "transportador":
        resultado = retorna_dados_transportador_sigor(dados.cnpj)
    elif tipo == "armazenador":
        resultado = retorna_dados_armazenador_sigor(dados.cnpj)
    else:
        raise HTTPException(status_code=400, detail="Tipo de parceiro inválido. Use: destino, transportador, armazenador")

    return {"tipoParceiro": tipo, "cnpj": dados.cnpj, "resultado": resultado}


# =========================
# SEMAD - GO
# =========================
@app.post("/semad/retorna-manifesto-codigo-de-barras")
def semad_retorna_manifesto(dados: ConsultaSemadManifestoRequest):
    try:
        token = gerar_token_semad(
            pessoa_codigo=dados.pessoaCodigo,
            cnpj=dados.cnpj,
            cpf=dados.cpf,
            senha=dados.senha
        )

        manifesto = retorna_manifesto_semad(
            token=token,
            codigo_barras=dados.codigoBarras
        )

        return {
            "sucesso": True,
            "orgao": "SEMAD",
            "dados": manifesto
        }

    except HTTPException as e:
        raise e

@app.post("/semad/busca-parceiro")
def semad_buscar_parceiro(dados: BuscaParceiro):
    tipo = (dados.tipoParceiro or "").strip().lower()

    if tipo == "destino":
        resultado = buscar_destino_semad(dados.cnpj)
    elif tipo == "transportador":
        resultado = buscar_transportador_semad(dados.cnpj)
    elif tipo == "armazenador":
        resultado = buscar_armazenador_semad(dados.cnpj)
    else:
        raise HTTPException(status_code=400, detail="Tipo de parceiro inválido. Use: destino, transportador, armazenador")

    return {"tipoParceiro": tipo, "cnpj": dados.cnpj, "resultado": resultado}



@app.get("/healthz")
def healthcheck():
    return {
        "status": "ok",
        "service": "api-feam-mtr",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
