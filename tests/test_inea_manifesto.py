from unittest.mock import Mock, patch

import pytest
import requests
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main
from services.inea import retorna_manifesto_inea

REQUEST = {
    "cpf": "cpf-teste",
    "senha": "senha-teste",
    "cnpj": "cnpj-teste",
    "unidadeGerador": "34",
    "codigoBarras": "codigo-teste",
}
INEA_URL = (
    "http://mtr.inea.rj.gov.br/api/retornaManifesto/"
    "cpf-teste/senha-teste/cnpj-teste/34/codigo-teste"
)
ARGS = {
    "cpf": REQUEST["cpf"],
    "senha": REQUEST["senha"],
    "cnpj": REQUEST["cnpj"],
    "unidade_gerador": REQUEST["unidadeGerador"],
    "codigo_barras": REQUEST["codigoBarras"],
}


def test_rota_inea_usa_relay_existente_e_preserva_envelope_e_cdf():
    manifesto = {"cdfCodigo": "CDF-INEA", "numero": "123456"}
    response = Mock(status_code=200)
    response.json.return_value = manifesto

    with (
        patch("services.inea.INEA_WORKAROUND_ENABLED", True),
        patch("services.inea.INEA_RELAY_KEY", "relay-key-teste"),
        patch("services.inea.obter_inea_relay_url", return_value="https://relay-teste.trycloudflare.com"),
        patch("services.inea.requests.post", return_value=response) as post,
    ):
        result = TestClient(main.app).post(
            "/inea/retorna-manifesto-codigo-de-barras", json=REQUEST,
        )

    assert result.status_code == 200
    assert result.json() == {"sucesso": True, "orgao": "INEA", "dados": manifesto}
    post.assert_called_once_with(
        url="https://relay-teste.trycloudflare.com/inea/retornaManifesto",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Tree-ESG-API/1.0",
            "Connection": "close",
            "X-Tree-Relay-Key": "relay-key-teste",
        },
        json={"url": INEA_URL},
        timeout=(15, 60),
        allow_redirects=False,
    )


def test_manifesto_direto_continua_disponivel_sem_workaround():
    response = Mock(status_code=200)
    response.json.return_value = {"cdfCodigo": "CDF-INEA"}

    with (
        patch("services.inea.INEA_WORKAROUND_ENABLED", False),
        patch("services.inea.executar_post_inea_relay") as relay,
        patch("services.inea.requests.post", return_value=response) as post,
    ):
        result = retorna_manifesto_inea(**ARGS)

    assert result == {"cdfCodigo": "CDF-INEA"}
    relay.assert_not_called()
    post.assert_called_once_with(INEA_URL, timeout=30)


@pytest.mark.parametrize("status", [500, 503])
def test_relay_nao_configurado_ou_indisponivel_nao_faz_fallback_direto(status):
    with (
        patch("services.inea.INEA_WORKAROUND_ENABLED", True),
        patch("services.inea.executar_post_inea_relay", side_effect=HTTPException(status_code=status, detail="Relay indisponível")),
        patch("services.inea.requests.post") as post,
        pytest.raises(HTTPException) as error,
    ):
        retorna_manifesto_inea(**ARGS)

    assert error.value.status_code == status
    post.assert_not_called()


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize(
    ("network_error", "status"),
    [
        (requests.Timeout, 504),
        (requests.ConnectTimeout, 504),
        (requests.ReadTimeout, 504),
        (requests.ConnectionError, 502),
        (requests.exceptions.SSLError, 502),
    ],
)
def test_manifesto_mapeia_timeout_rede_e_ssl_sem_expor_credenciais(enabled, network_error, status):
    with (
        patch("services.inea.INEA_WORKAROUND_ENABLED", enabled),
        patch("services.inea.executar_post_inea_relay", side_effect=network_error(INEA_URL)),
        patch("services.inea.requests.post", side_effect=network_error(INEA_URL)),
        pytest.raises(HTTPException) as error,
    ):
        retorna_manifesto_inea(**ARGS)

    assert error.value.status_code == status
    assert REQUEST["senha"] not in error.value.detail
    assert REQUEST["cpf"] not in error.value.detail


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("status", [400, 401, 403, 429, 500, 503])
def test_manifesto_preserva_status_http_recebido(enabled, status):
    response = Mock(status_code=status)

    with (
        patch("services.inea.INEA_WORKAROUND_ENABLED", enabled),
        patch("services.inea.executar_post_inea_relay", return_value=(response, "https://relay-teste")),
        patch("services.inea.requests.post", return_value=response),
        pytest.raises(HTTPException) as error,
    ):
        retorna_manifesto_inea(**ARGS)

    assert error.value.status_code == status
    response.json.assert_not_called()
