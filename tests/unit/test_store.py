from uuid import uuid4

import pytest

from app.models import Chimera, Pieces
from app.store import ChimeraStore, SessionRegistry


def _make_chimera(number: int = 1) -> Chimera:
    return Chimera(
        number=number,
        name=f"crossing{number}",
        pieces=Pieces(
            head="head10.png",
            body="body0.png",
            tail="tail0.png",
            legfront="legfront0.png",
            legback="legback0.png",
            wing="wing24.png",
        ),
        svg="<svg/>",
    )


class TestChimeraStore:
    def test_next_number_increments(self):
        store = ChimeraStore()
        assert store.next_number() == 1
        assert store.next_number() == 2
        assert store.next_number() == 3

    def test_add_and_get(self):
        store = ChimeraStore()
        c = _make_chimera()
        store.add(c)
        assert store.get(c.id) == c

    def test_get_unknown_returns_none(self):
        store = ChimeraStore()
        assert store.get(uuid4()) is None

    def test_delete_existing(self):
        store = ChimeraStore()
        c = _make_chimera()
        store.add(c)
        assert store.delete(c.id) is True
        assert store.get(c.id) is None

    def test_delete_unknown_returns_false(self):
        store = ChimeraStore()
        assert store.delete(uuid4()) is False

    def test_update_replaces(self):
        store = ChimeraStore()
        c = _make_chimera()
        store.add(c)
        updated = c.model_copy(update={"name": "renamed"})
        store.update(updated)
        assert store.get(c.id).name == "renamed"

    def test_all_ordered_by_number(self):
        store = ChimeraStore()
        c3 = _make_chimera(3)
        c1 = _make_chimera(1)
        c2 = _make_chimera(2)
        for c in (c3, c1, c2):
            store.add(c)
        ordered = store.all_ordered()
        assert [c.number for c in ordered] == [1, 2, 3]

    def test_all_ordered_empty(self):
        store = ChimeraStore()
        assert store.all_ordered() == []

    def test_add_imported_stores_entries(self):
        store = ChimeraStore()
        entries = {"head/custom.png": {"b64": "abc", "w": 10, "h": 10, "x": 0, "y": 15}}
        store.add_imported("head", "custom.png", entries)
        assert store.imported_cache() == entries

    def test_add_imported_registers_filename(self):
        store = ChimeraStore()
        store.add_imported("head", "custom.png", {})
        assert "custom.png" in store.imported_files()["head"]

    def test_add_imported_no_duplicate_filename(self):
        store = ChimeraStore()
        store.add_imported("head", "custom.png", {})
        store.add_imported("head", "custom.png", {})
        assert store.imported_files()["head"].count("custom.png") == 1

    def test_imported_files_returns_copy(self):
        store = ChimeraStore()
        files = store.imported_files()
        files["head"].append("injected.png")
        assert "injected.png" not in store.imported_files()["head"]


class TestSessionRegistry:
    def test_same_session_same_store(self):
        reg = SessionRegistry()
        s1 = reg.get_or_create("abc")
        s2 = reg.get_or_create("abc")
        assert s1 is s2

    def test_different_sessions_different_stores(self):
        reg = SessionRegistry()
        s1 = reg.get_or_create("abc")
        s2 = reg.get_or_create("xyz")
        assert s1 is not s2
