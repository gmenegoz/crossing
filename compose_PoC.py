import base64
import io
import random
from datetime import datetime
from pathlib import Path

from PIL import Image

ASSETS_DIR = Path(__file__).parent / "assets"
OUTPUT_DIR = Path(__file__).parent / "output"

# Layers with _l/_r suffix are the left/right halves of the original PNG.
# The base name (without suffix) is the assets subfolder.
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

SIMPLE_LAYERS = {"head", "body", "wing", "tail"}


def pick_random_png(subfolder: str) -> Path:
    folder = ASSETS_DIR / subfolder
    pngs = sorted(folder.glob("*.png"))
    if not pngs:
        raise FileNotFoundError(f"No PNG files found in {folder}")
    return random.choice(pngs)


def load_piece(layer: str, path: Path) -> tuple[Image.Image, int, int]:
    """Load a PNG, apply split if needed, then autocrop to content bounding box."""
    img = Image.open(path).convert("RGBA")
    w, h = img.size

    if layer.endswith("_l"):
        img = img.crop((0, 0, w // 2, h))
    elif layer.endswith("_r"):
        img = img.crop((w // 2, 0, w, h))

    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)

    return img


def img_to_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def compose():
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Map subfolder -> chosen PNG path (so _l and _r share the same file)
    chosen: dict[str, Path] = {}
    for layer in LAYER_ORDER:
        subfolder = layer[:-2] if layer.endswith(("_l", "_r")) else layer
        if subfolder not in chosen:
            chosen[subfolder] = pick_random_png(subfolder)

    parts = []
    for layer in LAYER_ORDER:
        subfolder = layer[:-2] if layer.endswith(("_l", "_r")) else layer
        path = chosen[subfolder]
        img = load_piece(layer, path)
        w, h = img.size
        b64 = img_to_b64(img)
        x, y = LAYER_POSITION[layer]
        parts.append({"layer": layer, "x": x, "y": y, "w": w, "h": h, "b64": b64})
        print(f"  {layer:14s} → {path.name}  ({w}×{h}) at ({x},{y})")

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

# TODO Rescaling is now fixed, should depend on pieces
# TODO Centering is now bad

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="{min_x-100} {min_y-50} {vw-100} {vh-50}" '
        f'width="{vw}" height="{vh}">\n'
        f'  <g id="chimera", transform="scale(0.7)">\n'
        f"{images_xml}\n"
        f'  </g>\n'
        f"</svg>\n"
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUTPUT_DIR / f"crossing_{timestamp}.svg"
    out_path.write_text(svg, encoding="utf-8")
    print(f"\nSaved → {out_path}")


if __name__ == "__main__":
    compose()
