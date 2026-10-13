"""Sanitize operational responses of IMA, FEPAM and SEMAD queries."""
from typing import Any


def sanitize_query_response(value: Any) -> Any:
    if isinstance(value, list):
        return [sanitize_query_response(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        normalized = "".join(char for char in str(key).lower() if char.isalnum())
        if (normalized in {"cpf", "login", "cnp", "authorization"}
                or normalized.endswith("cpf") or normalized.startswith("chave")
                or any(part in normalized for part in ("senha", "password", "token", "cookie", "jsessionid"))):
            continue
        result[key] = sanitize_query_response(item)
    return result
