from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests


FEAM_BASE_URL = "https://mtr.meioambiente.mg.gov.br/api"


class ConsultaMTRRequest(BaseModel):
    cnpj: str
    senha: str
    unidadeGerador: int
    codigoDeBarras: str


def gerar_token_feam(cnpj: str, senha: str, unidade: int):
    return data["token"], data["chave"]


def consultar_manifesto(codigo_barras: str, token: str, chave: str):
    return response.json()
