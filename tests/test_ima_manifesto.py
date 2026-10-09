import logging
from unittest.mock import Mock, patch
from urllib.parse import quote

import pytest
import requests
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main
from services.ima import consultar_manifesto_ima

BARCODE = '0000123456000000340000005600000078'
ARGS = {'codigo_barras': BARCODE, 'login': 'cpf-sentinel', 'senha': 'secret/sentinel?#', 'cnpj': 'cnpj-sentinel'}


def test_ima_route_preserves_contract_and_uses_cpf_login(caplog):
    upstream = Mock(status_code=200)
    upstream.json.return_value = {'manifestoCodigo': 123456, 'cdfCodigo': 'CDF-IMA'}
    with patch('services.ima.requests.post', return_value=upstream) as post, caplog.at_level(logging.INFO, logger='ima'):
        response = TestClient(main.app).post('/ima/retorna-manifesto-codigo-de-barras', json={
            'codigoBarras': BARCODE, 'cpf': ARGS['login'], 'senha': ARGS['senha'],
            'cnpj': ARGS['cnpj'], 'unidadeGerador': 'unit-distinct-from-cpf',
        })
    assert response.json() == {'sucesso': True, 'dados': upstream.json.return_value}
    post.assert_called_once_with('https://mtr.ima.sc.gov.br/mtrservice/retornaManifesto/' + '/'.join(
        quote(value, safe='') for value in (BARCODE, ARGS['login'], ARGS['senha'], ARGS['cnpj'])
    ), headers={'Content-Type': 'application/json'}, timeout=30)
    assert 'unit-distinct-from-cpf' not in post.call_args.args[0]
    assert ARGS['senha'] not in caplog.text
    assert ARGS['login'] not in caplog.text
    assert 'https://' not in caplog.text


@pytest.mark.parametrize('barcode', ['', '1' * 33, '1' * 35, 'a' * 34])
def test_invalid_barcode_never_calls_upstream(barcode):
    with patch('services.ima.requests.post') as post, pytest.raises(HTTPException) as error:
        consultar_manifesto_ima(**{**ARGS, 'codigo_barras': barcode})
    assert error.value.status_code == 400
    post.assert_not_called()


@pytest.mark.parametrize(('status', 'expected'), [(401, 401), (403, 403), (500, 502), (503, 502)])
def test_ima_upstream_http_errors(status, expected):
    with patch('services.ima.requests.post', return_value=Mock(status_code=status)), pytest.raises(HTTPException) as error:
        consultar_manifesto_ima(**ARGS)
    assert error.value.status_code == expected


@pytest.mark.parametrize(('exception', 'expected'), [(requests.ConnectTimeout, 504), (requests.ReadTimeout, 504), (requests.ConnectionError, 502), (requests.exceptions.SSLError, 502)])
def test_ima_transport_errors_are_sanitized(exception, expected, caplog):
    with patch('services.ima.requests.post', side_effect=exception(str(ARGS))), pytest.raises(HTTPException) as error:
        consultar_manifesto_ima(**ARGS)
    assert error.value.status_code == expected
    for secret in (ARGS['senha'], ARGS['login']):
        assert secret not in caplog.text
        assert secret not in error.value.detail


@pytest.mark.parametrize('data', [[], {}, {'retornoCodigo': 99}, {'erro': True, 'manifestoCodigo': 123456}, {'manifestoCodigo': 999}, {'manifestoCodigo': 123456, 'cdfCodigo': {}}, {'manifestoCodigo': 123456, 'retornoCodigo': 99}])
def test_ima_invalid_or_functional_error_is_not_success(data):
    upstream = Mock(status_code=200)
    upstream.json.return_value = data
    with patch('services.ima.requests.post', return_value=upstream), pytest.raises(HTTPException) as error:
        consultar_manifesto_ima(**ARGS)
    assert error.value.status_code == 502


def test_ima_non_json_is_controlled():
    upstream = Mock(status_code=200)
    upstream.json.side_effect = ValueError('secret-sentinel')
    with patch('services.ima.requests.post', return_value=upstream), pytest.raises(HTTPException) as error:
        consultar_manifesto_ima(**ARGS)
    assert error.value.status_code == 502
    assert 'secret-sentinel' not in error.value.detail


def test_ima_manifest_without_cdf_remains_valid():
    upstream = Mock(status_code=200)
    upstream.json.return_value = {'manifestoCodigo': 123456, 'cdfCodigo': None}
    with patch('services.ima.requests.post', return_value=upstream):
        assert consultar_manifesto_ima(**ARGS) == upstream.json.return_value
