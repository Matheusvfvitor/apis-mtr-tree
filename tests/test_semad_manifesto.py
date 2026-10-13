import logging
from unittest.mock import Mock, patch

import pytest
import requests
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main
from services.semad import gerar_token_semad, retorna_manifesto_semad

BARCODE = '0000123456000000340000005600000078'
CREDS = {'pessoa_codigo': 123, 'cnpj': 'cnpj-sentinel', 'cpf': 'cpf-sentinel', 'senha': 'password-sentinel'}


def call_stage(stage):
    if stage == 'token':
        return gerar_token_semad(**CREDS)
    return retorna_manifesto_semad('token-sentinel', BARCODE)


@pytest.mark.parametrize('token', ['token-sentinel', 'Bearer token-sentinel'])
def test_semad_route_preserves_contract_and_uses_single_bearer(token, caplog):
    auth = Mock(status_code=200)
    auth.json.return_value = {'retornoCodigo': 0, 'token': token}
    manifest = Mock(status_code=200)
    manifest.json.return_value = {'manifestoCodigo': 123456, 'situacaoManifestoCodigo': 3}
    with patch('services.semad.requests.post', side_effect=[auth, manifest]) as post, caplog.at_level(logging.INFO, logger='semad'):
        result = TestClient(main.app).post('/semad/retorna-manifesto-codigo-de-barras', json={
            'pessoaCodigo': 123, 'cnpj': CREDS['cnpj'], 'cpf': CREDS['cpf'], 'senha': CREDS['senha'], 'codigoBarras': BARCODE,
        })
    assert result.status_code == 200
    assert result.json() == {'sucesso': True, 'orgao': 'SEMAD', 'dados': manifest.json.return_value}
    first, second = post.call_args_list
    assert first.args[0] == 'https://mtr.meioambiente.go.gov.br/api/gettoken'
    assert first.kwargs['json'] == {'pessoaCodigo': '123', 'pessoaCnpj': CREDS['cnpj'], 'usuarioCpf': CREDS['cpf'], 'senha': CREDS['senha']}
    assert second.args[0] == f'https://mtr.meioambiente.go.gov.br/api/retornaManifesto/{BARCODE}'
    assert second.kwargs['headers']['Authorization'] == 'Bearer token-sentinel'
    assert first.kwargs['timeout'] == second.kwargs['timeout'] == 30
    for secret in (CREDS['cpf'], CREDS['senha'], 'token-sentinel'):
        assert secret not in caplog.text + result.text


@pytest.mark.parametrize('code', [None, '', ' ', True, 1.5])
def test_semad_invalid_person_code_rejected_before_http_without_echo(code):
    payload = {'cnpj': CREDS['cnpj'], 'cpf': CREDS['cpf'], 'senha': CREDS['senha'], 'codigoBarras': BARCODE}
    if code is not None:
        payload['pessoaCodigo'] = code
    with patch('services.semad.requests.post') as post:
        result = TestClient(main.app).post('/semad/retorna-manifesto-codigo-de-barras', json=payload)
    assert result.status_code == 422
    post.assert_not_called()
    assert CREDS['cpf'] not in result.text
    assert CREDS['senha'] not in result.text


@pytest.mark.parametrize('stage', ['token', 'manifest'])
@pytest.mark.parametrize(('status', 'expected'), [(401, 401), (403, 403), (500, 502), (503, 502)])
def test_semad_status_codes_are_controlled(stage, status, expected):
    with patch('services.semad.requests.post', return_value=Mock(status_code=status)), pytest.raises(HTTPException) as error:
        call_stage(stage)
    assert error.value.status_code == expected


@pytest.mark.parametrize('stage', ['token', 'manifest'])
@pytest.mark.parametrize(('exception', 'expected'), [(requests.ConnectTimeout, 504), (requests.ReadTimeout, 504), (requests.ConnectionError, 502), (requests.exceptions.SSLError, 502)])
def test_semad_network_errors_are_sanitized(stage, exception, expected, caplog):
    sentinel = 'cpf-sentinel password-sentinel token-sentinel'
    with patch('services.semad.requests.post', side_effect=exception(sentinel)), pytest.raises(HTTPException) as error:
        call_stage(stage)
    assert error.value.status_code == expected
    for secret in sentinel.split():
        assert secret not in caplog.text + error.value.detail


@pytest.mark.parametrize('data', [[], {}, {'retornoCodigo': 0}, {'retornoCodigo': 0, 'token': ''}, {'retornoCodigo': False, 'token': 'private'}, {'retornoCodigo': '0', 'token': 'private'}, {'retornoCodigo': 900, 'token': 'private'}, {'retornoCodigo': 0, 'token': 123}])
def test_semad_token_errors_never_expose_response(data):
    upstream = Mock(status_code=200)
    upstream.json.return_value = data
    with patch('services.semad.requests.post', return_value=upstream), pytest.raises(HTTPException) as error:
        gerar_token_semad(**CREDS)
    assert error.value.status_code == 502
    assert 'private' not in error.value.detail


@pytest.mark.parametrize('data', [[], {}, {'retornoCodigo': 900}, {'manifestoCodigo': 123456, 'erro': True}, {'manifestoCodigo': 999}, {'manifestoCodigo': 123456, 'retornoCodigo': 9}])
def test_semad_unknown_or_functional_error_is_not_success(data):
    upstream = Mock(status_code=200)
    upstream.json.return_value = data
    with patch('services.semad.requests.post', return_value=upstream), pytest.raises(HTTPException) as error:
        retorna_manifesto_semad('token-sentinel', BARCODE)
    functional = isinstance(data, dict) and (data.get("erro") is True or type(data.get("retornoCodigo")) is int and data["retornoCodigo"] != 0)
    assert error.value.status_code == (422 if functional else 502)


@pytest.mark.parametrize('stage', ['token', 'manifest'])
def test_semad_non_json_is_controlled(stage):
    upstream = Mock(status_code=200)
    upstream.json.side_effect = ValueError('password-sentinel token-sentinel')
    with patch('services.semad.requests.post', return_value=upstream), pytest.raises(HTTPException) as error:
        call_stage(stage)
    assert error.value.status_code == 502
    assert 'sentinel' not in error.value.detail


@pytest.mark.parametrize('barcode', ['', '1' * 33, 'a' * 34])
def test_semad_invalid_barcode_never_calls_token_or_manifest(barcode):
    with patch('services.semad.requests.post') as post:
        result = TestClient(main.app).post('/semad/retorna-manifesto-codigo-de-barras', json={
            'pessoaCodigo': 123, 'cnpj': CREDS['cnpj'], 'cpf': CREDS['cpf'], 'senha': CREDS['senha'], 'codigoBarras': barcode,
        })
    assert result.status_code == 422
    post.assert_not_called()


@pytest.mark.parametrize("field", ["cpf", "cnpj", "senha"])
def test_semad_missing_credentials_fail_validation_before_http(field):
    payload = {"pessoaCodigo": 123, "cnpj": CREDS["cnpj"], "cpf": CREDS["cpf"], "senha": CREDS["senha"], "codigoBarras": BARCODE}
    payload.pop(field)
    with patch("services.semad.requests.post") as post:
        result = TestClient(main.app).post("/semad/retorna-manifesto-codigo-de-barras", json=payload)
    assert result.status_code == 422
    assert CREDS["cpf"] not in result.text
    assert CREDS["senha"] not in result.text
    post.assert_not_called()


def test_semad_repeated_bearer_is_rejected_locally():
    with patch("services.semad.requests.post") as post, pytest.raises(HTTPException) as error:
        retorna_manifesto_semad("Bearer Bearer token-sentinel", BARCODE)
    assert error.value.status_code == 400
    post.assert_not_called()
