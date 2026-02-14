import requests
from fastapi import HTTPException
from pydantic import BaseModel
import json

SIGOR_BASE_URL = "https://mtrr.cetesb.sp.gov.br/apiws/rest"


# ==================================================
# Schema de entrada SIGOR
# ==================================================
class ConsultaSigorManifestoRequest(BaseModel):
    cpfCnpj: str
    senha: str
    unidade: str
    manifestoNumero: str

# ==================================================
# Passo 1 - Get Token SIGOR
# ==================================================
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

# ==================================================
# LOGIN NÃO OFICIAL
# ==================================================

def login_nao_oficial():

    try:
        url = "https://mtrr.cetesb.sp.gov.br/api/mtr/carregaDadosLogin"
        
        payload = json.dumps({
        "sistema": "",
        "email": "danielle@recicla.se",
        "senha": "Tree@2025",
        "login": "64806417000129",
        "parCodigo": 25427,
        "recaptcha": "TOKEN_DO_RECAPTCHA"
        })
        
        headers = {'Content-Type': 'application/json'}

        response = requests.request("POST", url, headers=headers, data=payload)
        
        response = response.json()
        objetoResposta = response.get('objetoResposta')
        token = objetoResposta.get('token')
        print('response', response)
        print('objetoResposta', objetoResposta)
        print('token', token)
        
        return token
    
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Erro de comunicação com o SIGOR (manifesto): {str(e)}"
        )
        
# ==================================================
# Passo 2 - Retorna Manifesto
# ==================================================

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

# ==================================================
# Retorna Dados Transportador
# ==================================================

def retorna_dados_transportador_sigor(cnpj):

    token = login_nao_oficial()
    print('token', token)

    url = f"https://mtrr.cetesb.sp.gov.br/api/mtr/pesquisaParceiro/5/{cnpj}"

    payload = {}
    headers = {
    'Authorization': f'Bearer {token}'
    }

    response = requests.request("GET", url, headers=headers, data=payload)
    print(response.text)
    return response.text

# ==================================================
# Retorna Dados Destino
# ==================================================

def retorna_dados_destino_sigor(cnpj):

    token = login_nao_oficial()
    print('token', token)

    url = f"https://mtrr.cetesb.sp.gov.br/api/mtr/pesquisaParceiro/9/{cnpj}"

    payload = {}
    headers = {
    'Authorization': f'Bearer {token}'
    }

    response = requests.request("GET", url, headers=headers, data=payload)
    print(response.text)
    return response.text

# ==================================================
# Retorna Dados Armazenador
# ==================================================

def retorna_dados_armazenador_sigor(cnpj):

    token = login_nao_oficial()
    print('token', token)

    url = f"https://mtrr.cetesb.sp.gov.br/api/mtr/pesquisaParceiro/10/{cnpj}"

    payload = {}
    headers = {
    'Authorization': f'Bearer {token}'
    }

    response = requests.request("GET", url, headers=headers, data=payload)
    print(response.text)
    return response.text


