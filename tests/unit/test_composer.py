import io

import pytest
from PIL import Image

from app.composer import (
    LAYER_ORDER,
    _img_to_b64,
    _process_piece,
    _split_legs,
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
        result = _split_legs("legfront_l", img)
        assert result.size[0] == 50

    def test_right_crop(self):
        img = _rgba(100, 50)
        result = _split_legs("legfront_r", img)
        assert result.size[0] == 50

    def test_no_split_for_regular_layer(self):
        img = _rgba(100, 50)
        result = _split_legs("head", img)
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

    def test_layer_returns_one_key(self):
        data = self._png_bytes()
        entries = process_imported("head", "custom.png", data)
        assert list(entries.keys()) == ["head/custom.png"]

    

class TestComposeSvg:
    def test_returns_svg_string(self, sample_pieces):
        svg = compose_svg(sample_pieces)
        assert svg.startswith("<svg")
        assert "</svg>" in svg

    def test_viewbox_is_present(self, sample_pieces):
        svg = compose_svg(sample_pieces)
        assert "viewBox=" in svg

