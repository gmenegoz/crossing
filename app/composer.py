import base64
import io
import random
from pathlib import Path

from PIL import Image

from app.models import LAYERS, Pieces

ASSETS_DIR = Path(__file__).parent.parent / "assets"

LAYER_ORDER = ["legback_l", "legback_r", "body", "legfront_l", "legfront_r", "head", "tail", "wing"]
LAYER_POSITION = {
    "head":       (0, 30),
    "body":       (110, 131),
    "wing":       (300, 0),
    "legfront_l": (40, 220),
    "legfront_r": (269, 220),
    "legback_l":  (40, 220),
    "legback_r":  (269, 220),
    "tail":       (460, 50),
}

# Global cache for built-in assets: "layer_variant/filename" -> {b64, w, h}
_cache: dict[str, dict] = {}


def _process_piece(layer: str, img: Image.Image) -> Image.Image:
    """Apply left/right split (for leg layers) and autocrop to content bounding box."""
    w, h = img.size
    if layer.endswith("_l"):
        img = img.crop((0, 0, w // 2, h))
    elif layer.endswith("_r"):
        img = img.crop((w // 2, 0, w, h))
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    return img


def _img_to_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _build_cache() -> None:
    for layer in LAYERS:
        folder = ASSETS_DIR / layer
        for png in folder.glob("*.png"):
            img = Image.open(png).convert("RGBA")
            if layer in ("legfront", "legback"):
                for variant in ("_l", "_r"):
                    processed = _process_piece(layer + variant, img.copy())
                    pw, ph = processed.size
                    _cache[f"{layer}{variant}/{png.name}"] = {"b64": _img_to_b64(processed), "w": pw, "h": ph}
            else:
                processed = _process_piece(layer, img)
                pw, ph = processed.size
                _cache[f"{layer}/{png.name}"] = {"b64": _img_to_b64(processed), "w": pw, "h": ph}


_build_cache()


def available_pngs(layer: str, extra_files: dict[str, list[str]] | None = None) -> list[str]:
    builtin = sorted(p.name for p in (ASSETS_DIR / layer).glob("*.png"))
    if extra_files and extra_files.get(layer):
        return builtin + extra_files[layer]
    return builtin


def process_imported(layer: str, filename: str, data: bytes) -> dict[str, dict]:
    """Process an uploaded PNG for the given layer. Returns cache entries to store."""
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    entries: dict[str, dict] = {}
    if layer in ("legfront", "legback"):
        for variant in ("_l", "_r"):
            processed = _process_piece(layer + variant, img.copy())
            pw, ph = processed.size
            entries[f"{layer}{variant}/{filename}"] = {"b64": _img_to_b64(processed), "w": pw, "h": ph}
    else:
        processed = _process_piece(layer, img)
        pw, ph = processed.size
        entries[f"{layer}/{filename}"] = {"b64": _img_to_b64(processed), "w": pw, "h": ph}
    return entries


def random_pieces(extra_files: dict[str, list[str]] | None = None) -> Pieces:
    return Pieces(**{layer: random.choice(available_pngs(layer, extra_files)) for layer in LAYERS})


def compose_svg(pieces: Pieces, extra_cache: dict[str, dict] | None = None) -> str:
    parts = []
    for layer in LAYER_ORDER:
        subfolder = layer[:-2] if layer.endswith(("_l", "_r")) else layer
        filename = getattr(pieces, subfolder)
        key = f"{layer}/{filename}"
        entry = (extra_cache or {}).get(key) or _cache[key]
        x, y = LAYER_POSITION[layer]
        parts.append({"x": x, "y": y, "w": entry["w"], "h": entry["h"], "b64": entry["b64"]})

    min_x = min(p["x"] for p in parts)
    min_y = min(p["y"] for p in parts)
    max_x = max(p["x"] + p["w"] for p in parts)
    max_y = max(p["y"] + p["h"] for p in parts)
    vw, vh = max_x - min_x, max_y - min_y

    images_xml = "\n".join(
        f'    <image x="{p["x"]}" y="{p["y"]}" width="{p["w"]}" height="{p["h"]}" '
        f'xlink:href="data:image/png;base64,{p["b64"]}" />'
        for p in parts
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="{min_x - 100} {min_y - 50} {vw - 100} {vh - 50}" '
        f'width="{vw}" height="{vh}">\n'
        f'  <g id="chimera" transform="scale(0.7)">\n'
        f"{images_xml}\n"
        f'  </g>\n'
        f"</svg>\n"
    )
