from pathlib import Path

from indexops.path_signals import infer_client_folder, infer_area_from_path


def test_client_from_first_segment(tmp_path):
    root = tmp_path / "Clientes"
    root.mkdir()
    client_dir = root / "ACME SL"
    client_dir.mkdir()
    doc = client_dir / "Fiscal" / "doc.pdf"
    doc.parent.mkdir(parents=True)
    doc.write_bytes(b"x")
    assert infer_client_folder(doc, root, ()) == "ACME SL"
    assert infer_area_from_path(doc) == "Fiscal"
