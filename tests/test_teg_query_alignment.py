from unittest.mock import Mock, patch
from urllib.parse import quote

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main
from services.fepam import retorna_manifesto_fepam
from services.ima import selecionar_login_consulta_ima
from services.query_response import sanitize_query_response

BARCODE = "0000123456000000340000005600000078"


def upstream(data, status=200):
    return Mock(status_code=status, json=Mock(return_value=data))


@pytest.mark.parametrize("refused", [upstream({"retornoCodigo": 900}), upstream({}, 401), upstream({}, 403)])
def test_ima_falls_back_to_cnpj_when_cpf_login_is_refused(refused):
    manifest = {"manifestoCodigo": 123456, "cdfCodigo": 777}
    with patch("services.ima.requests.post", side_effect=[refused, upstream([]), upstream(manifest)]) as post:
        response = TestClient(main.app).post("/ima/retorna-manifesto-codigo-de-barras", json={
            "cpf": "cpf-fixture", "cnpj": "cnpj-fixture", "senha": "password-fixture",
            "unidadeGerador": "unit-fixture", "codigoBarras": BARCODE,
        })
    assert response.status_code == 200
    assert "/retornaListaClasse/cpf-fixture/" in post.call_args_list[0].args[0]
    assert "/retornaListaClasse/cnpj-fixture/" in post.call_args_list[1].args[0]
    assert post.call_args_list[2].args[0].endswith(
        f"{BARCODE}/cnpj-fixture/password-fixture/cnpj-fixture/unit-fixture"
    )


@pytest.mark.parametrize("status", [401, 403])
def test_ima_rejected_auth_stops_before_manifest(status):
    with patch("services.ima.requests.post", side_effect=[upstream({}, status), upstream({}, status)]) as post, pytest.raises(HTTPException) as error:
        selecionar_login_consulta_ima("cpf", "cnpj", "password", "unit")
    assert error.value.status_code == 401
    assert post.call_count == 2


def test_ima_bad_barcode_never_authenticates():
    with patch("services.ima.requests.post") as post:
        response = TestClient(main.app).post("/ima/retorna-manifesto-codigo-de-barras", json={
            "cpf": "cpf", "cnpj": "cnpj", "senha": "password", "unidadeGerador": "34", "codigoBarras": "bad",
        })
    assert response.status_code == 400
    post.assert_not_called()


@pytest.mark.parametrize("unit,expected", [("34", 34), ("unit-text", "unit-text")])
def test_fepam_preflight_and_unit_match_teg(unit, expected):
    manifest = {"manifestoJSON": {"manifestoCodigo": 123456, "retornoCodigo": 0}}
    with patch("services.fepam.requests.post", side_effect=[upstream([]), upstream(manifest)]) as post:
        result = retorna_manifesto_fepam("cnpj", "cpf", "password/value", "123456", unit)
    assert result == manifest
    first, second = post.call_args_list
    assert first.args[0].endswith("/retornaListaEstadoFisico/cpf/" + quote("password/value", safe="") + "/cnpj")
    assert second.kwargs["json"] == {
        "cnp": "cnpj", "login": "cpf", "senha": "password/value", "codUnidade": expected,
        "manifestoJSON": {"manifestoCodigo": "123456"},
    }


@pytest.mark.parametrize("data", [{}, {"retornoCodigo": 900}, {"retornoCodigo": 0, "erro": True}])
def test_fepam_empty_or_failed_auth_does_not_query_manifest(data):
    with patch("services.fepam.requests.post", return_value=upstream(data)) as post, pytest.raises(HTTPException) as error:
        retorna_manifesto_fepam("cnpj", "cpf", "password", "123456", "34")
    assert error.value.status_code == 401
    assert post.call_count == 1


@pytest.mark.parametrize("person", ["unit-text", "0", "-1", "123.0"])
def test_semad_person_code_is_not_numerically_validated(person):
    with patch("services.semad.requests.post", side_effect=[
        upstream({"retornoCodigo": 0, "token": "token-fixture"}),
        upstream({"manifestoCodigo": 123456}),
    ]) as post:
        response = TestClient(main.app).post("/semad/retorna-manifesto-codigo-de-barras", json={
            "pessoaCodigo": person, "cpf": "cpf", "cnpj": "cnpj", "senha": "password", "codigoBarras": BARCODE,
        })
    assert response.status_code == 200
    assert post.call_args_list[0].kwargs["json"]["pessoaCodigo"] == person


@pytest.mark.parametrize("system", ["ima", "semad", "fepam"])
def test_nested_query_authentication_echo_is_removed(system):
    manifest = {"manifestoCodigo": 123456, "retornoCodigo": 0, "cdfCodigo": 777,
                "nested": {"password": "private", "accessToken": "private", "nome": "gerador"}}
    payload = {"cpf": "cpf", "cnpj": "cnpj", "senha": "password"}
    if system == "ima":
        payload.update(unidadeGerador="34", codigoBarras=BARCODE)
        responses = [upstream([]), upstream(manifest)]
    elif system == "semad":
        payload.update(pessoaCodigo="34", codigoBarras=BARCODE)
        responses = [upstream({"retornoCodigo": 0, "token": "token"}), upstream(manifest)]
    else:
        payload.update(unidade="34", manifestoCodigo="123456")
        responses = [upstream([]), upstream({"manifestoJSON": manifest})]
    with patch(f"services.{system}.requests.post", side_effect=responses):
        response = TestClient(main.app).post(f"/{system}/retorna-manifesto-codigo-de-barras", json=payload)
    assert response.status_code == 200
    assert "private" not in response.text
    assert "gerador" in response.text


def test_response_filter_preserves_operational_cnpj_and_cdf():
    assert sanitize_query_response({"cnpj": "gerador", "cdfCodigo": 777, "items": [{"token": "secret", "cpf": "secret"}]}) == {
        "cnpj": "gerador", "cdfCodigo": 777, "items": [{}],
    }
