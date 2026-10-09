from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

import main

BARCODE = "0000123456000000340000005600000078"


@pytest.mark.parametrize(("system", "required"), [("ima", "codigoBarras"), ("fepam", "manifestoCodigo"), ("semad", "pessoaCodigo")])
def test_query_validation_errors_never_echo_sensitive_input(system, required, caplog):
    payload = {"cpf": "cpf-sentinel", "cnpj": "cnpj-sentinel", "senha": "password-sentinel",
               "unidadeGerador": "34", "codigoBarras": BARCODE, "manifestoCodigo": "123456", "pessoaCodigo": 123}
    payload.pop(required)
    with patch(f"services.{system}.requests.post") as post:
        response = TestClient(main.app).post(f"/{system}/retorna-manifesto-codigo-de-barras", json=payload)
    assert response.status_code == 422
    assert "detail" in response.json()
    assert any(error["type"] == "missing" for error in response.json()["detail"])
    post.assert_not_called()
    for sentinel in ("cpf-sentinel", "password-sentinel"):
        assert sentinel not in response.text + caplog.text + repr([record.__dict__ for record in caplog.records])


def test_ima_success_does_not_echo_authentication_fields():
    upstream = Mock(status_code=200)
    upstream.json.return_value = {"manifestoCodigo": 123456, "cdfCodigo": 777,
                                  "cpf": "cpf-sentinel", "senha": "password-sentinel"}
    with patch("services.ima.requests.post", return_value=upstream):
        response = TestClient(main.app).post("/ima/retorna-manifesto-codigo-de-barras", json={
            "cpf": "cpf-sentinel", "cnpj": "cnpj-sentinel", "senha": "password-sentinel",
            "unidadeGerador": "34", "codigoBarras": BARCODE,
        })
    assert response.status_code == 200
    assert response.json() == {"sucesso": True, "dados": {"manifestoCodigo": 123456, "cdfCodigo": 777}}


def test_fepam_root_functional_error_cannot_be_hidden_by_nested_success():
    upstream = Mock(status_code=200)
    upstream.json.return_value = {"retornoCodigo": 900, "manifestoJSON": {"manifestoCodigo": 123456, "retornoCodigo": 0, "cdfCodigo": 777}}
    with patch("services.fepam.requests.post", return_value=upstream):
        response = TestClient(main.app).post("/fepam/retorna-manifesto-codigo-de-barras", json={
            "cpf": "cpf-sentinel", "cnpj": "cnpj-sentinel", "senha": "password-sentinel", "manifestoCodigo": "123456",
        })
    assert response.status_code == 401
