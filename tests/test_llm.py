from indexops.llm.settings import parse_llm_config
from indexops.llm_enrichment import _parse_enrichment_json


def test_parse_llm_config():
    cfg = parse_llm_config(
        {
            "enabled": True,
            "max_files_per_run": 15,
            "enrich": {"model": "mistral", "base_url": "http://127.0.0.1:11434"},
        }
    )
    assert cfg.enabled is True
    assert cfg.max_files_per_run == 15
    assert cfg.profile.model == "mistral"


def test_parse_enrichment_json():
    parsed, err = _parse_enrichment_json(
        '{"tipo_documental":"Modelo_303","area":"Fiscal","resumen":"IVA","palabras_clave":["303"],'
        '"confianza":0.9,"necesita_revision":false}'
    )
    assert err == ""
    assert parsed["tipo_documental"] == "Modelo_303"
