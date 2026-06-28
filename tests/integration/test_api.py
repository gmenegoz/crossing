"""Integration tests — full HTTP round-trips through the FastAPI app."""
import io
from uuid import uuid4

import pytest
from PIL import Image

from app.models import LAYERS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_pieces_payload() -> dict:
    return {
        "head": "head10.png",
        "body": "body0.png",
        "tail": "tail0.png",
        "legfront": "legfront0.png",
        "legback": "legback0.png",
        "wing": "wing24.png",
    }


def _png_bytes(w: int = 8, h: int = 8) -> bytes:
    img = Image.new("RGBA", (w, h), (100, 200, 50, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# GET /api/layers
# ---------------------------------------------------------------------------

class TestGetLayers:
    def test_returns_all_layers(self, client):
        r = client.get("/api/layers")
        assert r.status_code == 200
        data = r.json()
        for layer in LAYERS:
            assert layer in data
            assert len(data[layer]) > 0

    def test_values_are_png_filenames(self, client):
        data = client.get("/api/layers").json()
        for layer, files in data.items():
            for f in files:
                assert f.endswith(".png")


# ---------------------------------------------------------------------------
# POST /api/chimeras/random
# ---------------------------------------------------------------------------

class TestCreateRandom:
    def test_returns_chimera(self, client):
        r = client.post("/api/chimeras/random")
        assert r.status_code == 200
        body = r.json()
        assert "id" in body
        assert body["svg"].startswith("<svg")

    def test_sequential_numbers(self, client):
        r1 = client.post("/api/chimeras/random").json()
        r2 = client.post("/api/chimeras/random").json()
        assert r2["number"] == r1["number"] + 1

    def test_default_name_pattern(self, client):
        r = client.post("/api/chimeras/random").json()
        assert r["name"].startswith("crossing")


# ---------------------------------------------------------------------------
# POST /api/chimeras/manual
# ---------------------------------------------------------------------------

class TestCreateManual:
    def test_valid_request(self, client):
        r = client.post("/api/chimeras/manual", json={"pieces": _valid_pieces_payload()})
        assert r.status_code == 200
        body = r.json()
        assert body["pieces"]["head"] == "head10.png"
        assert body["svg"].startswith("<svg")

    def test_missing_piece_field_returns_422(self, client):
        payload = _valid_pieces_payload()
        del payload["head"]
        r = client.post("/api/chimeras/manual", json={"pieces": payload})
        assert r.status_code == 422

    def test_missing_body_returns_422(self, client):
        r = client.post("/api/chimeras/manual")
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/chimeras
# ---------------------------------------------------------------------------

class TestListChimeras:
    def test_empty_initially(self, client):
        r = client.get("/api/chimeras")
        assert r.status_code == 200
        assert r.json() == []

    def test_lists_created_chimeras(self, client):
        client.post("/api/chimeras/random")
        client.post("/api/chimeras/random")
        r = client.get("/api/chimeras")
        assert len(r.json()) == 2

    def test_ordered_by_number(self, client):
        client.post("/api/chimeras/random")
        client.post("/api/chimeras/random")
        items = client.get("/api/chimeras").json()
        numbers = [i["number"] for i in items]
        assert numbers == sorted(numbers)

    def test_list_item_has_no_pieces_field(self, client):
        client.post("/api/chimeras/random")
        item = client.get("/api/chimeras").json()[0]
        assert "pieces" not in item
        assert "svg" in item


# ---------------------------------------------------------------------------
# GET /api/chimeras/{id}
# ---------------------------------------------------------------------------

class TestGetChimera:
    def test_returns_chimera(self, client):
        created = client.post("/api/chimeras/random").json()
        r = client.get(f"/api/chimeras/{created['id']}")
        assert r.status_code == 200
        assert r.json()["id"] == created["id"]

    def test_unknown_id_returns_404(self, client):
        r = client.get(f"/api/chimeras/{uuid4()}")
        assert r.status_code == 404

    def test_invalid_uuid_returns_422(self, client):
        r = client.get("/api/chimeras/not-a-uuid")
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /api/chimeras/{id}/pieces
# ---------------------------------------------------------------------------

class TestUpdatePieces:
    def test_updates_pieces_and_svg(self, client):
        created = client.post("/api/chimeras/random").json()
        new_pieces = _valid_pieces_payload()
        r = client.patch(f"/api/chimeras/{created['id']}/pieces", json={"pieces": new_pieces})
        assert r.status_code == 200
        body = r.json()
        assert body["pieces"]["head"] == "head10.png"
        assert body["svg"].startswith("<svg")

    def test_unknown_id_returns_404(self, client):
        r = client.patch(f"/api/chimeras/{uuid4()}/pieces", json={"pieces": _valid_pieces_payload()})
        assert r.status_code == 404

    def test_invalid_payload_returns_422(self, client):
        created = client.post("/api/chimeras/random").json()
        r = client.patch(f"/api/chimeras/{created['id']}/pieces", json={"pieces": {"head": "x"}})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /api/chimeras/{id}/name
# ---------------------------------------------------------------------------

class TestRename:
    def test_renames_chimera(self, client):
        created = client.post("/api/chimeras/random").json()
        r = client.patch(f"/api/chimeras/{created['id']}/name", json={"name": "my creature"})
        assert r.status_code == 200
        assert r.json()["name"] == "my creature"

    def test_unknown_id_returns_404(self, client):
        r = client.patch(f"/api/chimeras/{uuid4()}/name", json={"name": "x"})
        assert r.status_code == 404

    def test_missing_name_field_returns_422(self, client):
        created = client.post("/api/chimeras/random").json()
        r = client.patch(f"/api/chimeras/{created['id']}/name", json={})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/chimeras/{id}
# ---------------------------------------------------------------------------

class TestDeleteChimera:
    def test_deletes_chimera(self, client):
        created = client.post("/api/chimeras/random").json()
        r = client.delete(f"/api/chimeras/{created['id']}")
        assert r.status_code == 200
        assert r.json() == {"ok": True}

    def test_deleted_chimera_not_found(self, client):
        created = client.post("/api/chimeras/random").json()
        client.delete(f"/api/chimeras/{created['id']}")
        r = client.get(f"/api/chimeras/{created['id']}")
        assert r.status_code == 404

    def test_unknown_id_returns_404(self, client):
        r = client.delete(f"/api/chimeras/{uuid4()}")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/imported-preview/{layer}/{filename}
# ---------------------------------------------------------------------------

class TestImportedPreview:
    def test_404_when_not_imported(self, client):
        r = client.get("/api/imported-preview/head/nonexistent.png")
        assert r.status_code == 404

    def test_returns_png_after_import(self, client):
        data = _png_bytes()
        client.post(
            "/api/import-pieces",
            files=[("files", ("head_custom.png", data, "image/png"))],
        )
        r = client.get("/api/imported-preview/head/head_custom.png")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"


# ---------------------------------------------------------------------------
# POST /api/import-pieces
# ---------------------------------------------------------------------------

class TestImportPieces:
    def test_import_head_piece(self, client):
        data = _png_bytes()
        r = client.post(
            "/api/import-pieces",
            files=[("files", ("head_import.png", data, "image/png"))],
        )
        assert r.status_code == 200
        body = r.json()
        assert "head" in body
        assert "head_import.png" in body["head"]

    def test_imported_file_appears_in_layers(self, client):
        data = _png_bytes()
        client.post(
            "/api/import-pieces",
            files=[("files", ("head_extra.png", data, "image/png"))],
        )
        layers = client.get("/api/layers").json()
        assert "head_extra.png" in layers["head"]

    def test_unrecognised_layer_in_filename_skipped(self, client):
        data = _png_bytes()
        r = client.post(
            "/api/import-pieces",
            files=[("files", ("mystery_file.png", data, "image/png"))],
        )
        assert r.status_code == 200
        assert r.json() == {}

    def test_import_leg_piece_splits_into_both_variants(self, client):
        data = _png_bytes(8, 8)
        client.post(
            "/api/import-pieces",
            files=[("files", ("legfront_custom.png", data, "image/png"))],
        )
        r = client.get("/api/imported-preview/legfront/legfront_custom.png")
        assert r.status_code == 200

    def test_imported_piece_usable_in_manual_create(self, client):
        data = _png_bytes()
        client.post(
            "/api/import-pieces",
            files=[("files", ("head_new.png", data, "image/png"))],
        )
        pieces = _valid_pieces_payload()
        pieces["head"] = "head_new.png"
        r = client.post("/api/chimeras/manual", json={"pieces": pieces})
        assert r.status_code == 200
        assert r.json()["pieces"]["head"] == "head_new.png"


# ---------------------------------------------------------------------------
# _infer_layer helper (tested indirectly via import-pieces)
# ---------------------------------------------------------------------------

class TestInferLayer:
    @pytest.mark.parametrize("filename,expected_layer", [
        ("legfront_abc.png", "legfront"),
        ("legback_abc.png", "legback"),
        ("head_abc.png", "head"),
        ("body_abc.png", "body"),
        ("tail_abc.png", "tail"),
        ("wing_abc.png", "wing"),
    ])
    def test_layer_inferred_from_filename(self, client, filename, expected_layer):
        data = _png_bytes()
        r = client.post(
            "/api/import-pieces",
            files=[("files", (filename, data, "image/png"))],
        )
        assert r.status_code == 200
        body = r.json()
        assert expected_layer in body
        assert filename in body[expected_layer]
