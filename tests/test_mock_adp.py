import pytest
from fastapi.testclient import TestClient

from mock_sources import adp_api

KEY = {"X-API-Key": adp_api.API_KEY}


@pytest.fixture
def client(tmp_path, monkeypatch):
    (tmp_path / "form_941_2026Q1.pdf").write_bytes(b"%PDF-fake-941")
    monkeypatch.setattr(adp_api, "DOCUMENTS_DIR", tmp_path)
    return TestClient(adp_api.app)


def test_missing_key_is_rejected(client):
    assert client.get("/documents").status_code == 401


def test_wrong_key_is_rejected(client):
    response = client.get("/documents", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


def test_list_documents(client):
    response = client.get("/documents", headers=KEY)
    assert response.status_code == 200
    assert response.json() == [
        {"name": "form_941_2026Q1.pdf", "period": "2026Q1", "size_bytes": 13}
    ]


def test_download_document(client):
    response = client.get("/documents/form_941_2026Q1.pdf", headers=KEY)
    assert response.status_code == 200
    assert response.content == b"%PDF-fake-941"


def test_unknown_document_is_404(client):
    assert client.get("/documents/nope.pdf", headers=KEY).status_code == 404


def test_path_traversal_is_blocked(client):
    response = client.get("/documents/..%2F..%2F.env", headers=KEY)
    assert response.status_code == 404


def test_quarter_filter_includes_that_years_annual_documents(client, tmp_path):
    (tmp_path / "form_941_2026Q2.pdf").write_bytes(b"q2")
    (tmp_path / "w2_2026_E001.pdf").write_bytes(b"w2")

    response = client.get("/documents", params={"quarter": "2026Q2"}, headers=KEY)

    names = [d["name"] for d in response.json()]
    assert names == ["form_941_2026Q2.pdf", "w2_2026_E001.pdf"]
