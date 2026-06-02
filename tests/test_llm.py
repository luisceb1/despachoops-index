from despachoops_index.config import _parse_llm
from despachoops_index.llm_enrichment import _parse_json


def test_parse_llm_config():
    cfg = _parse_llm({"enabled": True, "enrich": {"model": "qwen3:8b"}})
    assert cfg.enabled and cfg.profile.model == "qwen3:8b"


def test_parse_llm_json():
    data, err = _parse_json('{"tipo_documental":"Factura","area":"Fiscal","resumen":"x","palabras_clave":[],"confianza":0.9,"necesita_revision":false}')
    assert not err and data["tipo_documental"] == "Factura"
