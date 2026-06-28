import io
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.models import Pieces
from app.router import get_store
from app.store import ChimeraStore


@pytest.fixture()
def store():
    return ChimeraStore()


@pytest.fixture()
def client(store):
    """TestClient with dependency override so every request hits the same isolated store."""
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def sample_pieces():
    return Pieces(
        head="head10.png",
        body="body0.png",
        tail="tail0.png",
        legfront="legfront0.png",
        legback="legback0.png",
        wing="wing24.png",
    )


@pytest.fixture()
def minimal_png() -> bytes:
    """4×4 RGBA PNG with no external files."""
    img = Image.new("RGBA", (4, 4), (255, 0, 0, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
