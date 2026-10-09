from unittest.mock import Mock, patch

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
