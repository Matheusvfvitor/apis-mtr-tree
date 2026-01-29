
class ConsultaIMAManifestoRequest(BaseModel):
    cpf: str
    cnpj: str
    senha: str
    unidadeGerador: str
    codigoBarras: str


def consultar_manifesto_ima(
    codigo_barras: str,
    unidade_gerador: str,
    senha: str,
    cnpj: str
):
    url = (
        f"https://mtr.ima.sc.gov.br/mtrservice/retornaManifesto/"
        f"{codigo_barras}/{unidade_gerador}/{senha}/{cnpj}"
    )

    headers = {
        "Content-Type": "application/json"
    }

    response = requests.post(url, headers=headers, timeout=30)

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="Erro ao consultar manifesto no IMA"
        )

    return response.json()
