import logging
from unittest.mock import Mock, patch

import pytest
import requests
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main
from services.sinir import (
    gerar_token_dinamico_sinir,
    normalizar_bearer,
    retorna_manifesto_sinir,
)

client = TestClient(main.app)


def test_rota_troca_token_ws_e_encaminha_token_dinamico():
    manifesto = {"numero": "123456"}
    token_ws = "token-ws-teste"
    token_dinamico = "token-dinamico-teste"

    with (
        patch("services.sinir.gerar_token_sinir") as gerar_token,
        patch("main.gerar_token_dinamico_sinir", return_value=token_dinamico) as trocar_token,
        patch("main.retorna_manifesto_sinir", return_value=manifesto) as retorna_manifesto,
    ):
        response = client.post(
            "/sinir/retorna-manifesto",
            json={"token": token_ws, "manifestoNumero": "351030485121"},
        )

    assert response.status_code == 200
    assert response.json() == {"sucesso": True, "orgao": "SINIR", "dados": manifesto}
    gerar_token.assert_not_called()
    trocar_token.assert_called_once_with(token_ws=token_ws)
    retorna_manifesto.assert_called_once_with(
        token_dinamico=token_dinamico,
        manifesto_numero="351030485121",
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
    response.json.return_value = {
        "erro": False,
        "objetoResposta": {
            "manNumero": "351030485121",
            "cdfNumero": None,
        },
    }

    with patch("services.sinir.requests.get", return_value=response) as get:
        result = retorna_manifesto_sinir(
            token_dinamico=token,
            manifesto_numero="351030485121",
        )

    assert result["objetoResposta"]["cdfNumero"] is None
    assert get.call_args.args[0] == (
        "https://admin.sinir.gov.br/api/retornaManifesto/351030485121"
    )
    assert get.call_args.kwargs["headers"]["Authorization"] == authorization


def test_retorna_manifesto_rejeita_token_vazio():
    with pytest.raises(HTTPException) as exc_info:
        normalizar_bearer("  ")

    assert getattr(exc_info.value, "status_code", None) == 400


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 429, 500, 502, 503, 504])
def test_retorna_manifesto_preserva_status_de_autenticacao_e_sistemico(status_code):
    response = Mock(status_code=status_code)

    with (
        patch("services.sinir.requests.get", return_value=response),
        pytest.raises(HTTPException) as exc_info,
    ):
        retorna_manifesto_sinir(token_dinamico="abc123", manifesto_numero="123456")

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
            token_dinamico="token-de-teste",
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
            token_dinamico="token-de-teste",
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
            token_dinamico=token,
            manifesto_numero="123456",
        )

    assert token not in str(exc_info.value.detail)


def test_troca_token_ws_chama_endpoint_sem_body_e_registra_somente_estrutura(caplog):
    token_ws = "token-ws-secreto"
    token_dinamico = "token-dinamico-secreto"
    response = Mock(status_code=200)
    response.json.return_value = {
        "mensagem": "Autenticado com sucesso",
        "objetoResposta": f"Bearer {token_dinamico}",
        "totalRecords": 0,
        "erro": False,
    }

    with (
        caplog.at_level(logging.INFO, logger="sinir"),
        patch("services.sinir.requests.post", return_value=response) as token_post,
    ):
        token = gerar_token_dinamico_sinir(token_ws)

    assert token == f"Bearer {token_dinamico}"
    assert token_post.call_args.args[0] == "https://admin.sinir.gov.br/apiws/rest/token"
    assert token_post.call_args.kwargs["headers"]["Authorization"] == "Bearer token-ws-secreto"
    assert token_post.call_args.kwargs["data"] == ""
    assert token_post.call_args.kwargs["timeout"] == 30
    assert "step=token_exchange.response" in caplog.text
    assert "status=200" in caplog.text
    assert "json_type=dict" in caplog.text
    assert "erro" in caplog.text
    assert "mensagem" in caplog.text
    assert "objetoResposta" in caplog.text
    assert token_ws not in caplog.text
    assert token_dinamico not in caplog.text
    assert "Authorization" not in caplog.text


def test_troca_token_sem_objeto_resposta_retorna_502():
    response = Mock(status_code=200)
    response.json.return_value = {"mensagem": "Autenticado", "erro": False}

    with (
        patch("services.sinir.requests.post", return_value=response),
        pytest.raises(HTTPException) as exc_info,
    ):
        gerar_token_dinamico_sinir("token-ws-teste")

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Token dinâmico SINIR não retornado."


def test_troca_token_resposta_nao_json_retorna_502():
    response = Mock(status_code=200)
    response.json.side_effect = ValueError("corpo não deve ser exposto")

    with (
        patch("services.sinir.requests.post", return_value=response),
        pytest.raises(HTTPException) as exc_info,
    ):
        gerar_token_dinamico_sinir("token-ws-teste")

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Resposta inválida na troca do token SINIR."
    assert "corpo não deve ser exposto" not in str(exc_info.value.detail)


def test_troca_token_erro_true_retorna_502():
    token_dinamico = "token-dinamico-secreto"
    response = Mock(status_code=200)
    response.json.return_value = {
        "mensagem": "Falha",
        "objetoResposta": f"Bearer {token_dinamico}",
        "erro": True,
    }

    with (
        patch("services.sinir.requests.post", return_value=response),
        pytest.raises(HTTPException) as exc_info,
    ):
        gerar_token_dinamico_sinir("token-ws-teste")

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Token dinâmico SINIR não retornado."
    assert token_dinamico not in str(exc_info.value.detail)


@pytest.mark.parametrize("status_code", [400, 401, 403, 500, 502, 503, 504])
def test_troca_token_preserva_status_http_upstream(status_code):
    response = Mock(status_code=status_code)

    with (
        patch("services.sinir.requests.post", return_value=response),
        pytest.raises(HTTPException) as exc_info,
    ):
        gerar_token_dinamico_sinir("token-ws")

    assert exc_info.value.status_code == status_code


def test_troca_token_timeout_retorna_504():
    with (
        patch("services.sinir.requests.post", side_effect=requests.Timeout("timeout")),
        pytest.raises(HTTPException) as exc_info,
    ):
        gerar_token_dinamico_sinir("token-ws")

    assert exc_info.value.status_code == 504


def test_troca_token_erro_de_rede_retorna_502():
    with (
        patch("services.sinir.requests.post", side_effect=requests.ConnectionError("erro")),
        pytest.raises(HTTPException) as exc_info,
    ):
        gerar_token_dinamico_sinir("token-ws")

    assert exc_info.value.status_code == 502
