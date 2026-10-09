from unittest.mock import Mock, patch

import pytest
import requests
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main
from services.sinir import normalizar_token_sinir, retorna_manifesto_sinir

client = TestClient(main.app)


def test_retorna_manifesto_usa_token_recebido_sem_gerar_token():
    manifesto = {"numero": "123456"}

    with (
        patch("services.sinir.gerar_token_sinir") as gerar_token,
        patch("main.retorna_manifesto_sinir", return_value=manifesto) as retorna_manifesto,
    ):
        response = client.post(
            "/sinir/retorna-manifesto",
            json={"token": "token-de-teste", "manifestoNumero": "123456"},
        )

    assert response.status_code == 200
    assert response.json() == {"sucesso": True, "orgao": "SINIR", "dados": manifesto}
    gerar_token.assert_not_called()
    retorna_manifesto.assert_called_once_with(
        token_bearer="token-de-teste",
        manifesto_numero="123456",
    )


def test_rota_rejeita_campos_antigos_do_contrato():
    response = client.post(
        "/sinir/retorna-manifesto",
        json={
            "cpfCnpj": "12345678901234",
            "senha": "senha-de-teste",
            "unidade": "1",
            "manifestoNumero": "123456",
        },
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("token", "authorization"),
    [
        ("abc123", "Bearer abc123"),
        ("Bearer abc123", "Bearer abc123"),
        ("  bEaReR abc123  ", "bEaReR abc123"),
    ],
)
def test_retorna_manifesto_normaliza_authorization(token, authorization):
    response = Mock(status_code=200)
    response.json.return_value = {"numero": "123456"}

    with patch("services.sinir.requests.get", return_value=response) as get:
        retorna_manifesto_sinir(token_bearer=token, manifesto_numero="123456")

    assert get.call_args.kwargs["headers"]["Authorization"] == authorization


def test_retorna_manifesto_rejeita_token_vazio():
    with pytest.raises(HTTPException) as exc_info:
        normalizar_token_sinir("  ")

    assert getattr(exc_info.value, "status_code", None) == 400


@pytest.mark.parametrize("status_code", [401, 403, 500, 502, 503, 504])
def test_retorna_manifesto_preserva_status_de_autenticacao_e_sistemico(status_code):
    response = Mock(status_code=status_code)

    with (
        patch("services.sinir.requests.get", return_value=response),
        pytest.raises(HTTPException) as exc_info,
    ):
        retorna_manifesto_sinir(token_bearer="abc123", manifesto_numero="123456")

    assert getattr(exc_info.value, "status_code", None) == status_code


def test_retorna_manifesto_timeout_retorna_504():
    with (
        patch(
            "services.sinir.requests.get",
            side_effect=requests.Timeout("timeout"),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        retorna_manifesto_sinir(
            token_bearer="token-de-teste",
            manifesto_numero="123456",
        )

    assert exc_info.value.status_code == 504
    assert exc_info.value.detail == "Timeout na comunicação com o SINIR (manifesto)."


def test_retorna_manifesto_erro_de_rede_retorna_502():
    with (
        patch(
            "services.sinir.requests.get",
            side_effect=requests.ConnectionError("erro de teste"),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        retorna_manifesto_sinir(
            token_bearer="token-de-teste",
            manifesto_numero="123456",
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Erro de comunicação com o SINIR (manifesto)."


@pytest.mark.parametrize(
    "network_error",
    [
        requests.ConnectionError("erro"),
        requests.Timeout("timeout"),
    ],
)
def test_retorna_manifesto_nao_expoe_token_em_erro(network_error):
    token = "token-super-secreto-de-teste"

    with (
        patch("services.sinir.requests.get", side_effect=network_error),
        pytest.raises(HTTPException) as exc_info,
    ):
        retorna_manifesto_sinir(
            token_bearer=token,
            manifesto_numero="123456",
        )

    assert token not in str(exc_info.value.detail)
