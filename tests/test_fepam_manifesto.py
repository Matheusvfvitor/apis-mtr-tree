from unittest.mock import Mock, patch

import pytest
import requests
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main
from services.fepam import retorna_manifesto_fepam


def test_fepam_documented_request_and_nested_manifest_contract():
    data = {'manifestoJSON': {'manifestoCodigo': 123456, 'retornoCodigo': 0, 'cdfCodigo': 777}}
    upstream = Mock(status_code=200)
    upstream.json.return_value = data
    with patch('services.fepam.requests.post', return_value=upstream) as post:
        assert retorna_manifesto_fepam('cnpj-fixture', 'cpf-fixture', 'password-fixture', '123456') == data
    post.assert_called_once_with(
        'https://mtr.fepam.rs.gov.br/mtrservice/retornaManifesto',
        json={'cnp': 'cnpj-fixture', 'login': 'cpf-fixture', 'senha': 'password-fixture', 'manifestoJSON': {'manifestoCodigo': '123456'}},
        headers={'Content-Type': 'application/json'}, timeout=30,
    )


def test_fepam_documented_functional_error_fixture_is_not_a_manifest():
    data = {'retornoCodigo': 900}
    assert 'manifestoJSON' not in data
    assert 'cdfCodigo' not in data


@pytest.mark.parametrize(("code", "status"), [(900, 401), (901, 403), (902, 404), (903, 400), (999, 502)])
def test_fepam_documented_functional_errors_are_controlled(code, status):
    upstream = Mock(status_code=200)
    upstream.json.return_value = {"retornoCodigo": code, "senha": "secret-sentinel"}
    with patch("services.fepam.requests.post", return_value=upstream), pytest.raises(HTTPException) as error:
        retorna_manifesto_fepam("cnpj", "cpf", "password", "123456")
    assert error.value.status_code == status
    assert "secret-sentinel" not in error.value.detail


@pytest.mark.parametrize("data", [[], {}, {"manifestoJSON": {"retornoCodigo": 0, "manifestoCodigo": 999}}, {"manifestoJSON": {"retornoCodigo": 0, "manifestoCodigo": 123456, "cdfCodigo": {}}}])
def test_fepam_invalid_contract_does_not_return_success(data):
    upstream = Mock(status_code=200)
    upstream.json.return_value = data
    with patch("services.fepam.requests.post", return_value=upstream), pytest.raises(HTTPException) as error:
        retorna_manifesto_fepam("cnpj", "cpf", "password", "123456")
    assert error.value.status_code == 502


@pytest.mark.parametrize(("exception", "status"), [(requests.Timeout, 504), (requests.ConnectionError, 502), (requests.exceptions.SSLError, 502)])
def test_fepam_network_error_does_not_expose_credentials(exception, status, caplog):
    with patch("services.fepam.requests.post", side_effect=exception("password-sentinel cpf-sentinel")), pytest.raises(HTTPException) as error:
        retorna_manifesto_fepam("cnpj", "cpf-sentinel", "password-sentinel", "123456")
    assert error.value.status_code == status
    assert "password-sentinel" not in error.value.detail + caplog.text
    assert "cpf-sentinel" not in error.value.detail + caplog.text


@pytest.mark.parametrize(("status", "expected"), [(401, 401), (403, 403), (500, 502)])
def test_fepam_http_status(status, expected):
    with patch("services.fepam.requests.post", return_value=Mock(status_code=status)), pytest.raises(HTTPException) as error:
        retorna_manifesto_fepam("cnpj", "cpf", "password", "123456")
    assert error.value.status_code == expected


def test_fepam_non_json_is_controlled():
    upstream = Mock(status_code=200)
    upstream.json.side_effect = ValueError("password-sentinel")
    with patch("services.fepam.requests.post", return_value=upstream), pytest.raises(HTTPException) as error:
        retorna_manifesto_fepam("cnpj", "cpf", "password", "123456")
    assert error.value.status_code == 502
    assert "password-sentinel" not in error.value.detail


@pytest.mark.parametrize("cdf", [777, None])
def test_fepam_route_retains_envelope_and_removes_echoed_auth(cdf):
    upstream = Mock(status_code=200)
    manifest = {"manifestoCodigo": 123456, "retornoCodigo": 0, "cdfCodigo": cdf}
    upstream.json.return_value = {"login": "cpf-sentinel", "senha": "password-sentinel", "cnp": "cnpj-sentinel", "manifestoJSON": manifest}
    with patch("services.fepam.requests.post", return_value=upstream):
        result = TestClient(main.app).post("/fepam/retorna-manifesto-codigo-de-barras", json={
            "cpf": "cpf-sentinel", "cnpj": "cnpj-sentinel", "senha": "password-sentinel", "manifestoCodigo": "123456",
        })
    assert result.status_code == 200
    assert result.json() == {"sucesso": True, "orgao": "FEPAM", "dados": {"manifestoJSON": manifest}}
    assert "password-sentinel" not in result.text
    assert "cpf-sentinel" not in result.text
