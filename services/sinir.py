import requests
from fastapi import HTTPException
from pydantic import BaseModel
import json

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

# ==================================================
# LOGIN NÃO OFICIAL
# ==================================================

def login_nao_oficial_sinir(login: str = "04304532642", senha: str = "Sinir@2601", parCodigo: int = 490976):
    
    print('login sinir api não oficial...')

    try:
        url = "https://mtr.sinir.gov.br/api/mtr/login"
        
        payload = json.dumps({
            "parCodigo": parCodigo,
            "login": login,
            "senha": senha
        })
        
        headers = {'Content-Type': 'application/json'}

        response = requests.request("POST", url, headers=headers, data=payload)
        
        response = response.json()
        objetoResposta = response.get('objetoResposta')
        token = objetoResposta.get('token')
        
        return token
    
    except requests.RequestException as e:
        
        raise HTTPException(
            status_code=502,
            detail=f"Erro de comunicação com o SIGOR (manifesto): {str(e)}"
        )
    
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

# ==================================================
# Retorna Dados Transportador
# ==================================================

def retorna_dados_transportador_sinir(cnpj):
    print('\nretornando dados do transportador')

    token = login_nao_oficial_sinir()
    url = f"https://mtr.sinir.gov.br/api/mtr/pesquisaParceiro/5/{cnpj}"

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

def retorna_dados_destino_sinir(cnpj):
    print('\nretornando dados do destino')

    token = login_nao_oficial_sinir()

    url = f"https://mtr.sinir.gov.br/api/mtr/pesquisaParceiro/9/{cnpj}"

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

def retorna_dados_armazenador_sinir(cnpj):
    
    print('\n... retornando dados do armazenador')
    token = login_nao_oficial_sinir()

    url = f"https://mtr.sinir.gov.br/api/mtr/pesquisaParceiro/10/{cnpj}"

    payload = {}
    headers = {
    'Authorization': f'Bearer {token}'
    }

    response = requests.request("GET", url, headers=headers, data=payload)
    print(response.text)
    return response.text

#retorna_dados_armazenador('50891995000104')
#retorna_dados_transportador('39228967000160')
#retorna_dados_destino('50891995000104')



# ==================================================
# BUSCA MODELOS 
# ==================================================  
def busca_modelos_sinir(login: str = "04304532642", senha: str = "Sinir@2601", parCodigo: int = 490976):
    print('\n... buscando modelos')

    token = login_nao_oficial_sinir()
    
    print('token:', token)

    url = f"https://mtr.sinir.gov.br/api/mtr/manifestoModelo/{parCodigo}"

    payload = {}
    headers = {
    'Authorization': f'Bearer {token}'
    }

    response = requests.request("GET", url, headers=headers, data=payload)
    print(response.text)
    return response.text

busca_modelos_sinir(senha='$Thjrwgf02', parCodigo='386496', login='04304532642')