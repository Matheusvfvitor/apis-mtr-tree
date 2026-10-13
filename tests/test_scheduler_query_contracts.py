"""Local QA requires the sibling scheduler checkout (or TREE_SCHEDULER_ROOT)."""

import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

import main

scheduler_root = Path(os.getenv("TREE_SCHEDULER_ROOT", str(Path(__file__).resolve().parents[2] / "tree-automation")))
if not (scheduler_root / "app/jobs/smartwaste/mtr_cdf_check.py").is_file():
    pytest.skip("Requires scheduler checkout for joint contract QA", allow_module_level=True)
sys.path.insert(0, str(scheduler_root))
from app.jobs.smartwaste.mtr_cdf_check import ROUTES, _payload_for_system, extract_cdf


@pytest.mark.parametrize("system", ["IMA", "FEPAM"])
def test_real_scheduler_payload_is_accepted_by_api_and_returns_documented_cdf(system):
    credential = {"sistema": system, "cpf": "cpf-sentinel", "cnpj": "cnpj-sentinel", "psw": "password-sentinel", "unidade": "34"}
    shipment = {"mtr": "123456", "unidadeGerador": "34.0", "unidadeColetor": 56, "unidadeDestino": 78}
    payload = _payload_for_system(system, credential, {}, shipment)
    manifest = {"manifestoCodigo": 123456, "cdfCodigo": 777, "retornoCodigo": 0}
    upstream = Mock(status_code=200)
    upstream.json.return_value = {"manifestoJSON": manifest} if system == "FEPAM" else manifest
    with patch(f"services.{system.lower()}.requests.post", side_effect=[Mock(status_code=200, json=Mock(return_value=[])), upstream]):
        response = TestClient(main.app).post(ROUTES[system], json=payload)
    assert response.status_code == 200
    assert extract_cdf(system, response.json()) == "777"
    assert "password-sentinel" not in response.text
    assert "cpf-sentinel" not in response.text
