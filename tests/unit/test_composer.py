import io

import pytest
from PIL import Image

from app.composer import (
    LAYER_ORDER,
    _img_to_b64,
    _process_piece,
    available_pngs,
    compose_svg,
    process_imported,
    random_pieces,
)
from app.models import LAYERS, Pieces


def _rgba(w: int, h: int, color=(255, 0, 0, 255)) -> Image.Image:
    return Image.new("RGBA", (w, h), color)


class TestProcessPiece:
    def test_left_crop(self):
        img = _rgba(100, 50)
        result = _process_piece("legfront_l", img)
        assert result.size[0] == 50

    def test_right_crop(self):
        img = _rgba(100, 50)
        result = _process_piece("legfront_r", img)
        assert result.size[0] == 50

    def test_no_split_for_regular_layer(self):
        img = _rgba(100, 50)
        result = _process_piece("head", img)
        # autocrop on fully opaque image leaves it unchanged
        assert result.size == (100, 50)

    def test_autocrop_removes_transparent_border(self):
        # Create 10×10 fully transparent, draw a 2×2 opaque pixel in center
        img = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
        img.putpixel((4, 4), (255, 0, 0, 255))
        img.putpixel((5, 4), (255, 0, 0, 255))
        img.putpixel((4, 5), (255, 0, 0, 255))
        img.putpixel((5, 5), (255, 0, 0, 255))
        result = _process_piece("head", img)
        assert result.size == (2, 2)

    def test_fully_transparent_unchanged(self):
        img = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
        result = _process_piece("head", img)
        assert result.size == (10, 10)


class TestImgToB64:
    def test_returns_ascii_string(self):
        img = _rgba(4, 4)
        b64 = _img_to_b64(img)
        assert isinstance(b64, str)
        assert b64.isascii()

    def test_decodable_to_valid_png(self):
        import base64
        img = _rgba(4, 4)
        b64 = _img_to_b64(img)
        data = base64.b64decode(b64)
        decoded = Image.open(io.BytesIO(data))
        assert decoded.size == (4, 4)


class TestAvailablePngs:
    def test_all_layers_have_builtins(self):
        for layer in LAYERS:
            pngs = available_pngs(layer)
            assert len(pngs) > 0, f"{layer} has no built-in PNGs"

    def test_returns_sorted_list(self):
        for layer in LAYERS:
            pngs = available_pngs(layer)
            assert pngs == sorted(pngs)

    def test_extra_files_appended(self):
        extra = {"head": ["custom.png"], "body": [], "tail": [], "legfront": [], "legback": [], "wing": []}
        pngs = available_pngs("head", extra)
        assert "custom.png" in pngs
        assert pngs.index("custom.png") > 0  # builtins come first

    def test_no_extra_returns_only_builtins(self):
        without = available_pngs("head")
        with_empty = available_pngs("head", {"head": []})
        assert without == with_empty


class TestProcessImported:
    def _png_bytes(self, w=8, h=8) -> bytes:
        img = Image.new("RGBA", (w, h), (0, 255, 0, 200))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_regular_layer_returns_one_key(self):
        data = self._png_bytes()
        entries = process_imported("head", "custom.png", data)
        assert list(entries.keys()) == ["head/custom.png"]

    def test_leg_layer_returns_two_keys(self):
        data = self._png_bytes(8, 8)
        entries = process_imported("legfront", "custom.png", data)
        assert set(entries.keys()) == {"legfront_l/custom.png", "legfront_r/custom.png"}

    def test_legback_returns_two_keys(self):
        data = self._png_bytes(8, 8)
        entries = process_imported("legback", "custom.png", data)
        assert set(entries.keys()) == {"legback_l/custom.png", "legback_r/custom.png"}

    def test_entry_has_required_fields(self):
        data = self._png_bytes()
        entries = process_imported("tail", "t.png", data)
        entry = entries["tail/t.png"]
        assert "b64" in entry
        assert "w" in entry
        assert "h" in entry
        assert isinstance(entry["w"], int)
        assert isinstance(entry["h"], int)


class TestRandomPieces:
    def test_returns_pieces_instance(self):
        p = random_pieces()
        assert isinstance(p, Pieces)

    def test_all_fields_are_valid_filenames(self):
        p = random_pieces()
        for layer in LAYERS:
            filename = getattr(p, layer)
            assert filename in available_pngs(layer), f"{filename} not in {layer} builtins"

    def test_with_extra_files_can_pick_them(self):
        # Run many times; with only 1 extra file on a small layer (wing=2 files),
        # the extra should eventually be picked.
        extra = {l: [] for l in LAYERS}
        extra["wing"] = ["custom_wing.png"]
        picked = set()
        for _ in range(50):
            p = random_pieces(extra)
            picked.add(p.wing)
        assert "custom_wing.png" in picked


class TestComposeSvg:
    def test_returns_svg_string(self, sample_pieces):
        svg = compose_svg(sample_pieces)
        assert svg.startswith("<svg")
        assert "</svg>" in svg

    def test_contains_image_per_layer(self, sample_pieces):
        svg = compose_svg(sample_pieces)
        assert svg.count("<image") == len(LAYER_ORDER)

    def test_viewbox_is_present(self, sample_pieces):
        svg = compose_svg(sample_pieces)
        assert "viewBox=" in svg

    def test_extra_cache_used_for_imported_piece(self, sample_pieces):
        import base64
        tiny = Image.new("RGBA", (2, 2), (1, 2, 3, 255))
        buf = io.BytesIO()
        tiny.save(buf, format="PNG")
        b64_val = base64.b64encode(buf.getvalue()).decode()

        # Replace head with an imported piece
        pieces = sample_pieces.model_copy(update={"head": "imported_head.png"})
        extra_cache = {"head/imported_head.png": {"b64": b64_val, "w": 2, "h": 2}}
        svg = compose_svg(pieces, extra_cache)
        assert b64_val in svg
