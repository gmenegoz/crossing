import pytest
from pydantic import ValidationError
from uuid import UUID

from app.models import (
    Chimera,
    ChimeraListItem,
    CreateManualRequest,
    Pieces,
    RenameRequest,
    UpdatePiecesRequest,
)


def _valid_pieces() -> dict:
    return {
        "head": "head10.png",
        "body": "body0.png",
        "tail": "tail0.png",
        "legfront": "legfront0.png",
        "legback": "legback0.png",
        "wing": "wing24.png",
    }


class TestPieces:
    def test_valid_construction(self):
        p = Pieces(**_valid_pieces())
        assert p.head == "head10.png"

    def test_missing_field_raises(self):
        data = _valid_pieces()
        del data["head"]
        with pytest.raises(ValidationError):
            Pieces(**data)

    def test_all_fields_present(self):
        p = Pieces(**_valid_pieces())
        for field in ("head", "body", "tail", "legfront", "legback", "wing"):
            assert getattr(p, field) is not None


class TestChimera:
    def test_auto_uuid(self):
        c = Chimera(number=1, name="test", pieces=Pieces(**_valid_pieces()), svg="<svg/>")
        assert isinstance(c.id, UUID)

    def test_two_chimeras_have_different_ids(self):
        kwargs = dict(number=1, name="x", pieces=Pieces(**_valid_pieces()), svg="<svg/>")
        c1 = Chimera(**kwargs)
        c2 = Chimera(**kwargs)
        assert c1.id != c2.id

    def test_missing_number_raises(self):
        with pytest.raises(ValidationError):
            Chimera(name="x", pieces=Pieces(**_valid_pieces()), svg="<svg/>")


class TestChimeraListItem:
    def test_construction(self):
        from uuid import uuid4
        item = ChimeraListItem(id=uuid4(), number=1, name="x", svg="<svg/>")
        assert item.name == "x"


class TestCreateManualRequest:
    def test_valid(self):
        req = CreateManualRequest(pieces=Pieces(**_valid_pieces()))
        assert req.pieces.head == "head10.png"

    def test_missing_pieces_raises(self):
        with pytest.raises(ValidationError):
            CreateManualRequest()


class TestUpdatePiecesRequest:
    def test_valid(self):
        req = UpdatePiecesRequest(pieces=Pieces(**_valid_pieces()))
        assert req.pieces is not None


class TestRenameRequest:
    def test_valid_name(self):
        req = RenameRequest(name="new name")
        assert req.name == "new name"

    def test_empty_string_accepted(self):
        req = RenameRequest(name="")
        assert req.name == ""

    def test_missing_name_raises(self):
        with pytest.raises(ValidationError):
            RenameRequest()
