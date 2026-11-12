import base64
import io
import random
import heapq
from pathlib import Path
from itertools import groupby

from PIL import Image

from app.models import LAYERS, Pieces

ASSETS_DIR = Path(__file__).parent.parent / "assets"

LAYER_ORDER = ["tail", "legback", "body", "legfront", "head", "wing"]
LAYER_POSITION = {
    "head":         (0, 0),
    "body":         (183, 51),
    "wing":         (345, 0),
    "legfront":     (0, 181),
    "legfront_l":   (0, 181),
    "legfront_r":   (0, 181), # Sarebbe 380 ma c'è l'offset dato da split-legs
    "legback":      (0, 181),
    "legback_l":    (0, 181),
    "legback_r":    (0, 181),
    "tail":         (519, 0),
}

LAYER_PROBABILITY = {
    "head": 1,
    "body": 1,
    "wing": 0.15,
    "tail": 0.8,
    "legback": 0.95,
    "legfront": 0.95
}

OPTIONAL_LAYERS = {layer for layer, p in LAYER_PROBABILITY.items() if p < 1}


# Global cache for built-in assets: "layer_variant/filename" -> {b64, w, h}
_cache: dict[str, dict] = {}

def load_piece( path: Path) -> Image.Image:
    img = Image.open(path).convert("RGBA")
    return img

def parse_projection( img: Image.Image) -> list[int]:
    w, h = img.size
    pixel_map = img.getchannel('A').load()
    xProjection = img.getchannel('A').getprojection()[0]

    for column in range(w):
        pixelCount = 0
        if xProjection[column] == 1:
            for row in range(h):
                if pixel_map[column, row] != 0:
                    pixelCount = pixelCount + 1
            if pixelCount < 15:
                xProjection[column] = 0

    grouped = [(k, len(list(g))) for k, g in groupby(xProjection)]
    return grouped


def split_legs(img: Image.Image) -> list:
    w, h = img.size

    grouped = parse_projection(img)
    if len(grouped) <= 3:
        legs = [(img,0)]
    else:
        tentative_legs = heapq.nlargest(
            2,
            (i for i, (flag, _) in enumerate(grouped) if flag == 1),
            key=lambda i: grouped[i][1],
        )
        left_leg_index = min(tentative_legs)
        left_leg_left_margin = sum(v for _, v in grouped[:left_leg_index])
        left_leg_right_margin = left_leg_left_margin + grouped[left_leg_index][1]
        leftLeg = img.crop((left_leg_left_margin, 0, left_leg_right_margin, h))
        right_leg_index = max(tentative_legs)
        right_leg_left_margin = sum(v for _, v in grouped[:right_leg_index])
        right_leg_right_margin = right_leg_left_margin + grouped[right_leg_index][1]
        rightLeg = img.crop((right_leg_left_margin, 0, right_leg_right_margin, h))
        
        legs = [(leftLeg, left_leg_left_margin), (rightLeg, right_leg_left_margin)]

    return legs

def _img_to_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _build_cache() -> None:
    for layer in LAYERS:
        folder = ASSETS_DIR / layer
        for png in folder.glob("*.png"):
            img = load_piece(png)
            _cache[f"{layer}/{png.name}"] = img


_build_cache()




def builtin_pngs(layer: str) -> list[str]:
    return sorted(p.name for p in (ASSETS_DIR / layer).glob("*.png"))


# Pieces.<layer> values starting with this prefix refer to an imported piece;
# plain names refer to built-in pieces. This keeps a built-in and an imported
# file with the same name (e.g. body12.png) distinct.
IMPORTED_PREFIX = "imported:"


def lookup_piece(layer: str, filename: str, extra_cache: dict | None = None):
    """Resolve a Pieces value to its image, honouring the built-in/imported distinction."""
    extra_cache = extra_cache or {}
    if filename.startswith(IMPORTED_PREFIX):
        return extra_cache[f"{layer}/{filename[len(IMPORTED_PREFIX):]}"]
    key = f"{layer}/{filename}"
    # Plain names are built-in; fall back to imported only for legacy, untagged values
    return _cache[key] if key in _cache else extra_cache[key]


def available_pngs(layer: str, extra_files: dict[str, list[str]] | None = None) -> list[str]:
    builtin = builtin_pngs(layer)
    if extra_files and extra_files.get(layer):
        return builtin + extra_files[layer]
    return builtin


def process_imported(layer: str, filename: str, data: bytes) -> dict[str, dict]:
    """Process an uploaded PNG for the given layer. Returns cache entries to store."""
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    entries: dict[str, dict] = {}
    entries[f"{layer}/{filename}"] = img
    return entries


def random_pieces(extra_files: dict[str, list[str]] | None = None) -> Pieces:
    parts = {}
    for layer in LAYER_ORDER:
        threshold = LAYER_PROBABILITY[layer]
        if layer == "legfront":
            if "legback" in parts.keys():
                threshold = 1.0
            else:
                continue
        if random.random() >= threshold:
            continue
        choices = builtin_pngs(layer) + [
            IMPORTED_PREFIX + f for f in (extra_files or {}).get(layer, [])
        ]
        parts[layer] = random.choice(choices)
        
    return Pieces(**parts)


def add_part(img: Image.Image, layer: str, path: str, parts: list, additional_offset: int = 0) -> list:
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    w, h = img.size
    b64 = _img_to_b64(img)
    offset = (bbox[0]+ additional_offset, bbox[1]) if bbox else (0,0)
    x, y =  tuple(map(sum, zip(LAYER_POSITION[layer], offset)))
    parts.append({"layer": layer, "x": x, "y": y, "w": w, "h": h, "b64": b64})
    print(f"  {layer:14s} → {path}  ({w}×{h}) at ({x},{y})")
    return parts

def compose_svg(pieces: Pieces, extra_cache: dict[str, dict] | None = None) -> str:
    parts = []
    print(pieces)
    for layer in LAYER_ORDER:
        subfolder = layer
        filename = getattr(pieces, subfolder)
        if(filename):
            key = f"{layer}/{filename}"
            entry = lookup_piece(layer, filename, extra_cache)
            if layer.startswith("leg"):
                legs = split_legs(entry)
                if len(legs) == 1:
                    parts = add_part(legs[0][0], layer, key, parts)
                else:
                    parts = add_part(legs[0][0], layer+"_l", key, parts, legs[0][1])
                    parts = add_part(legs[1][0], layer+"_r", key, parts, legs[1][1])
            else:
                parts = add_part(entry, layer, key, parts)

    min_x = min(p["x"] for p in parts)
    min_y = min(p["y"] for p in parts)
    max_x = max(p["x"] + p["w"] for p in parts)
    max_y = max(p["y"] + p["h"] for p in parts)
    vw, vh = max_x - min_x, max_y - min_y


    images_xml = "\n".join(
        f'    <image id="{p["layer"]}" x="{p["x"] + 240}" y="{p["y"] + 150}" width="{p["w"]}" height="{p["h"]}" '
        f'xlink:href="data:image/png;base64,{p["b64"]}" />'
        for p in parts
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="{min_x} {min_y} {vw} {vh}" '
        f'width="{vw}" height="{vh}">\n'
        f'  <g id="chimera" transform="scale(0.5)">\n'
        f"{images_xml}\n"
        f'  </g>\n'
        f"</svg>\n"
    )
