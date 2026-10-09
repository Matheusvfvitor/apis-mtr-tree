from unittest.mock import Mock, patch

import pytest
import requests
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main
from services.feam import gerar_token_feam, retorna_manifesto_feam

client = TestClient(main.app)


def test_rota_feam_encaminha_credenciais_do_request():
    manifesto_response = Mock(status_code=200)
    manifesto_response.json.return_value = {"numero": "123456"}

    with (
        patch("services.feam.requests.post", return_value=manifesto_response),
        patch("services.feam.gerar_token_feam", return_value=("token-secreto", "chave-secreta")) as gerar_token,
    ):
        response = client.post(
            "/feam/retorna-manifesto-codigo-de-barras",
            json={
                "cpf": "cpf-do-request",
                "cnpj": "cnpj-do-request",
                "senha": "senha-do-request",
                "unidadeGerador": 42,
                "codigoDeBarras": "123456",
            },
        )

    assert response.status_code == 200
    gerar_token.assert_called_once_with(
        cpf="cpf-do-request",
        cnpj="cnpj-do-request",
        senha="senha-do-request",
        unidade=42,
    )
    assert response.json()["dados"] == {"numero": "123456"}


def test_gerar_token_feam_usa_cpf_cnpj_senha_e_unidade_recebidos():
    response = Mock(status_code=200)
    response.json.return_value = {"token": "token-feam", "chave": "chave-feam"}

    with patch("services.feam.requests.post", return_value=response) as post:
        credentials = gerar_token_feam(
            cpf="cpf-do-request",
            cnpj="cnpj-do-request",
            senha="senha-do-request",
            unidade=17,
        )

    assert credentials == ("token-feam", "chave-feam")
    assert post.call_args.kwargs["json"] == {
        "pessoaCodigo": 17,
        "pessoaCnpj": "cnpj-do-request",
        "usuarioCpf": "cpf-do-request",
        "senha": "senha-do-request",
    }


def test_retorna_manifesto_feam_envia_token_e_chave_recebidos():
    response = Mock(status_code=200)
    response.json.return_value = {"numero": "123456"}

    with (
        patch("services.feam.gerar_token_feam", return_value=("token-feam", "chave-feam")) as gerar_token,
        patch("services.feam.requests.post", return_value=response) as post,
    ):
        result = retorna_manifesto_feam(
            cpf="cpf-do-request",
            cnpj="cnpj-do-request",
            senha="senha-do-request",
            unidade=17,
            codigo_barras="123456",
        )

    assert result == {"numero": "123456"}
    gerar_token.assert_called_once_with(
        cpf="cpf-do-request",
        cnpj="cnpj-do-request",
        senha="senha-do-request",
        unidade=17,
    )
    assert post.call_args.kwargs["headers"] == {
        "Authorization": "Bearer token-feam",
        "chave_feam": "chave-feam",
    }


def test_gerar_token_feam_timeout_retorna_504():
    with (
        patch("services.feam.requests.post", side_effect=requests.Timeout("timeout")),
        pytest.raises(HTTPException) as exc_info,
    ):
        gerar_token_feam("cpf", "cnpj", "senha", 1)

    assert exc_info.value.status_code == 504
    assert exc_info.value.detail == "Timeout na comunicação com a FEAM (token)."


def test_retorna_manifesto_feam_timeout_retorna_504():
    with (
        patch("services.feam.gerar_token_feam", return_value=("token", "chave")),
        patch("services.feam.requests.post", side_effect=requests.Timeout("timeout")),
        pytest.raises(HTTPException) as exc_info,
    ):
        retorna_manifesto_feam("cpf", "cnpj", "senha", 1, "123456")

    assert exc_info.value.status_code == 504
    assert exc_info.value.detail == "Timeout na comunicação com a FEAM (manifesto)."


@pytest.mark.parametrize("operation", ["token", "manifesto"])
def test_feam_erro_de_rede_retorna_502(operation):
    with (
        patch("services.feam.requests.post", side_effect=requests.ConnectionError("erro")),
        patch("services.feam.gerar_token_feam", return_value=("token", "chave")),
        pytest.raises(HTTPException) as exc_info,
    ):
        if operation == "token":
            gerar_token_feam("cpf", "cnpj", "senha", 1)
        else:
            retorna_manifesto_feam("cpf", "cnpj", "senha", 1, "123456")

    assert exc_info.value.status_code == 502


@pytest.mark.parametrize("status_code", [401, 403, 500, 502, 503, 504])
@pytest.mark.parametrize("operation", ["token", "manifesto"])
def test_feam_preserva_status_de_autenticacao_e_sistemico(status_code, operation):
    response = Mock(status_code=status_code)
    with (
        patch("services.feam.requests.post", return_value=response),
        patch("services.feam.gerar_token_feam", return_value=("token", "chave")),
        pytest.raises(HTTPException) as exc_info,
    ):
        if operation == "token":
            gerar_token_feam("cpf", "cnpj", "senha", 1)
        else:
            retorna_manifesto_feam("cpf", "cnpj", "senha", 1, "123456")

    assert exc_info.value.status_code == status_code


@pytest.mark.parametrize("operation", ["token", "manifesto"])
def test_feam_nao_expoe_credenciais_em_erro(operation):
    secrets = ("senha-super-secreta", "token-super-secreto", "chave-super-secreta")
    with (
        patch("services.feam.requests.post", side_effect=requests.ConnectionError("erro")),
        patch("services.feam.gerar_token_feam", return_value=(secrets[1], secrets[2])),
        pytest.raises(HTTPException) as exc_info,
    ):
        if operation == "token":
            gerar_token_feam("cpf-completo", "cnpj", secrets[0], 1)
        else:
            retorna_manifesto_feam("cpf-completo", "cnpj", secrets[0], 1, "123456")

    detail = str(exc_info.value.detail)
    assert all(secret not in detail for secret in (*secrets, "cpf-completo"))


def test_gerar_token_feam_nao_expoe_resposta_sensivel_em_detail():
    response = Mock(status_code=200)
    response.json.return_value = {"token": "token-super-secreto"}

    with (
        patch("services.feam.requests.post", return_value=response),
        pytest.raises(HTTPException) as exc_info,
    ):
        gerar_token_feam("cpf", "cnpj", "senha-super-secreta", 1)

    assert exc_info.value.status_code == 401
    assert "token-super-secreto" not in str(exc_info.value.detail)
    assert "senha-super-secreta" not in str(exc_info.value.detail)


def test_rota_feam_rejeita_campos_extra_e_exige_cpf():
    response = client.post(
        "/feam/retorna-manifesto-codigo-de-barras",
        json={
            "cnpj": "cnpj",
            "senha": "senha",
            "unidadeGerador": 1,
            "codigoDeBarras": "123456",
            "campoExtra": "valor",
        },
    )

    assert response.status_code == 422
