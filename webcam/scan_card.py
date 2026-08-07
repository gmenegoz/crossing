#!/usr/bin/env python3
"""Detect a white rectangle bordered by a black frame in a JPG, correct
perspective distortion, crop, resize to a fixed size and save as PNG."""

import sys
from pathlib import Path

import cv2
import numpy as np

TARGET_SIZE = {
    "head": (367, 483),
    "body": (438, 331),
    "tail": (240, 534),
    "legfront": (758, 357),
    "legback": (758, 357),
    "wing": (759, 534),
}
DEFAULT_TARGET = (367, 483)
ASPECT_TOLERANCE = 0.05

# Piece markers are a small saturated square in one corner of the white
# rectangle. Hues are spaced 60 degrees apart around the wheel (OpenCV's
# 0-179 hue range) to stay distinguishable under lighting variation.
PIECE_HUES = {
    "head": 0,
    "body": 120,
    "legback": 60,
    "legfront": 30,
    "tail": 90,
    "wing": 150,
}
MARKER_HUE_TOLERANCE = 15  # max distance from a palette hue to accept a match
MARKER_SATURATION_THRESHOLD = 80
MARKER_MIN_PIXELS = 150  # below this, treat as noise rather than a real marker
MARKER_CORNER_FRACTION = 0.15  # fraction of width/height sampled at each corner


def piece_from_filename(filename: str) -> str | None:
    stem = Path(filename).stem.lower()
    for piece in TARGET_SIZE:
        if piece in stem:
            return piece
    return None


def _hue_distance(a: float, b: float) -> float:
    """Circular distance between two hues on OpenCV's 0-179 scale."""
    d = abs(a - b) % 180
    return min(d, 180 - d)


def find_marker_corner(warped: np.ndarray) -> tuple[str, int, int, int, int] | None:
    """Look for a saturated marker square in each corner of the (still
    unrotated) warped rectangle. Returns (corner_name, x, y, w, h) for the
    corner region with the largest saturated blob, or None if no corner has
    enough saturated pixels to be considered a real marker."""
    height, width = warped.shape[:2]
    ch = int(height * MARKER_CORNER_FRACTION)
    cw = int(width * MARKER_CORNER_FRACTION)
    regions = {
        "TL": (0, 0, cw, ch),
        "TR": (width - cw, 0, cw, ch),
        "BL": (0, height - ch, cw, ch),
        "BR": (width - cw, height - ch, cw, ch),
    }

    best = None
    for name, (x, y, w, h) in regions.items():
        region = warped[y : y + h, x : x + w]
        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
        saturated = hsv[:, :, 1] > MARKER_SATURATION_THRESHOLD
        count = int(saturated.sum())
        if count >= MARKER_MIN_PIXELS and (best is None or count > best[1]):
            hue = float(np.median(hsv[:, :, 0][saturated]))
            best = (name, count, hue, (x, y, w, h))

    if best is None:
        return None
    name, _count, hue, (x, y, w, h) = best
    return name, hue, x, y, w, h


def piece_from_marker_hue(hue: float) -> str | None:
    matches = [
        piece for piece, target_hue in PIECE_HUES.items()
        if _hue_distance(hue, target_hue) <= MARKER_HUE_TOLERANCE
    ]
    return matches[0] if len(matches) == 1 else None


def detect_piece_by_marker(warped: np.ndarray) -> tuple[str, tuple[int, int, int, int]] | None:
    """Return (piece_name, (x, y, w, h)) for the marker's corner region, or
    None if no confident marker was found."""
    found = find_marker_corner(warped)
    if found is None:
        return None
    _corner_name, hue, x, y, w, h = found
    piece = piece_from_marker_hue(hue)
    if piece is None:
        return None
    return piece, (x, y, w, h)


def erase_marker(warped: np.ndarray, region: tuple[int, int, int, int]) -> np.ndarray:
    """Paint over the marker's corner with the page's background color so it
    blends in and is dropped by remove_white_background rather than
    surviving as a colored patch in the final output."""
    x, y, w, h = region
    height, width = warped.shape[:2]
    # Sample background color just outside the marker region, on whichever
    # side has room, to approximate the local page tone under that corner.
    if x > 0:
        sample = warped[y : y + h, max(0, x - 10) : x]
    elif x + w < width:
        sample = warped[y : y + h, x + w : min(width, x + w + 10)]
    elif y > 0:
        sample = warped[max(0, y - 10) : y, x : x + w]
    else:
        sample = warped[y + h : min(height, y + h + 10), x : x + w]

    background_color = sample.reshape(-1, 3).mean(axis=0) if sample.size else np.array([255, 255, 255])
    erased = warped.copy()
    erased[y : y + h, x : x + w] = background_color
    return erased


class FrameNotFoundError(Exception):
    pass


class PieceNotIdentifiedError(Exception):
    pass


def order_corners(pts: np.ndarray) -> np.ndarray:
    """Order 4 points as top-left, top-right, bottom-right, bottom-left."""
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).flatten()
    top_left = pts[np.argmin(s)]
    bottom_right = pts[np.argmax(s)]
    top_right = pts[np.argmin(diff)]
    bottom_left = pts[np.argmax(diff)]
    return np.array([top_left, top_right, bottom_right, bottom_left], dtype="float32")


RING_CONTRAST_RATIO = 0.6  # surrounding black frame must be this much darker than the rectangle
MIN_BORDER_SAMPLE = 1  # minimum px of margin needed on a side to trust its darkness sample


def is_framed_by_black_border(gray: np.ndarray, x: int, y: int, w: int, h: int) -> bool:
    """Check that a candidate white rectangle is fully enclosed by a darker
    border on all 4 sides (not just adjacent to another bright region like a
    stray photo or lightbox). Padding is clamped to whatever margin the image
    actually has, so a rectangle framed close to the photo's edge can still
    be validated with a thinner sample on that side."""
    img_height, img_width = gray.shape
    pad = max(10, int(0.04 * max(w, h)))

    top_pad = min(pad, y)
    bottom_pad = min(pad, img_height - (y + h))
    left_pad = min(pad, x)
    right_pad = min(pad, img_width - (x + w))
    if min(top_pad, bottom_pad, left_pad, right_pad) < MIN_BORDER_SAMPLE:
        return False

    inner_mean = gray[y : y + h, x : x + w].mean()
    top = gray[y - top_pad : y, x : x + w]
    bottom = gray[y + h : y + h + bottom_pad, x : x + w]
    left = gray[y : y + h, x - left_pad : x]
    right = gray[y : y + h, x + w : x + w + right_pad]

    return all(side.mean() < inner_mean * RING_CONTRAST_RATIO for side in (top, bottom, left, right))


def find_frame_corners(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Dark speckle noise in the artwork can touch the black frame border
    # (e.g. a jagged illustration edge close to the rectangle's edge),
    # cutting a notch into the white rectangle's contour. Closing bridges
    # such thin gaps; is_framed_by_black_border rejects any case where this
    # accidentally merges in a neighboring bright object instead.
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, np.ones((45, 45), np.uint8))

    contours, _ = cv2.findContours(closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise FrameNotFoundError("no contours found")

    image_area = gray.shape[0] * gray.shape[1]
    candidates = sorted(contours, key=cv2.contourArea, reverse=True)

    for contour in candidates[:15]:
        area = cv2.contourArea(contour)
        if area < image_area * 0.02 or area > image_area * 0.95:
            continue
        # Artwork/text inside the white rectangle can be dark enough to be
        # classified as background, carving notches into its contour; take
        # the convex hull so a busy interior doesn't break the quad fit.
        hull = cv2.convexHull(contour)
        perimeter = cv2.arcLength(hull, True)
        approx = cv2.approxPolyDP(hull, 0.02 * perimeter, True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        x, y, w, h = cv2.boundingRect(approx)
        # The real scan target is a white rectangle fully enclosed by a black
        # frame; other bright regions in the shot (stray photos, lightboxes)
        # won't have a darker border on all 4 sides.
        if is_framed_by_black_border(gray, x, y, w, h):
            return order_corners(approx.reshape(4, 2).astype("float32"))

    raise FrameNotFoundError("no quadrilateral frame contour found")


def warp_to_rectangle(image: np.ndarray, corners: np.ndarray) -> np.ndarray:
    (top_left, top_right, bottom_right, bottom_left) = corners

    width_top = np.linalg.norm(top_right - top_left)
    width_bottom = np.linalg.norm(bottom_right - bottom_left)
    height_left = np.linalg.norm(bottom_left - top_left)
    height_right = np.linalg.norm(bottom_right - top_right)

    warped_width = int(round(max(width_top, width_bottom)))
    warped_height = int(round(max(height_left, height_right)))
    warped_width = max(warped_width, 1)
    warped_height = max(warped_height, 1)

    destination = np.array(
        [
            [0, 0],
            [warped_width - 1, 0],
            [warped_width - 1, warped_height - 1],
            [0, warped_height - 1],
        ],
        dtype="float32",
    )

    matrix = cv2.getPerspectiveTransform(corners, destination)
    return cv2.warpPerspective(image, matrix, (warped_width, warped_height))


TRIM_FRACTION = 0.015  # shave this fraction off each side to drop stray black-frame slivers


def trim_border(warped: np.ndarray) -> np.ndarray:
    """Detected corners can include a sliver of the black frame at the edges
    (perspective/threshold detection isn't pixel-perfect); shave a small
    margin off each side before it's treated as foreground by background
    removal."""
    height, width = warped.shape[:2]
    trim_x = max(1, int(round(width * TRIM_FRACTION)))
    trim_y = max(1, int(round(height * TRIM_FRACTION)))
    return warped[trim_y : height - trim_y, trim_x : width - trim_x]


def check_aspect_ratio(warped: np.ndarray, filename: str, target_size: tuple[int, int]) -> None:
    target_width, target_height = target_size
    target_ratio = target_width / target_height
    height, width = warped.shape[:2]
    ratio = width / height
    if abs(ratio - target_ratio) / target_ratio > ASPECT_TOLERANCE:
        print(
            f"[WARN] {filename}: detected aspect ratio {ratio:.3f} differs from "
            f"target {target_ratio:.3f} by more than {ASPECT_TOLERANCE:.0%}, "
            f"forcing resize anyway",
            file=sys.stderr,
        )


def correct_rotation(warped: np.ndarray, target_size: tuple[int, int]) -> np.ndarray:
    """Rotate 90° if the warped image's orientation doesn't match the target's."""
    target_width, target_height = target_size
    height, width = warped.shape[:2]
    is_portrait_target = target_height >= target_width
    is_portrait_image = height >= width
    if is_portrait_target != is_portrait_image:
        return cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)
    return warped


FLOOD_DIFF = 2  # per-step gradient tolerance for border flood-fill
FLOOD_SEED_STEP = 15  # px spacing between seed points along the image border


def _background_mask_by_flood_fill(image: np.ndarray) -> np.ndarray:
    """Classify background as pixels reachable from the image border through
    a chain of similarly-toned neighbors. A brightness-only classifier (e.g.
    Otsu) can't tell a bright highlight inside the artwork from real page
    background and punches holes in it; flood-fill can't reach an interior
    highlight unless there's a real gap in the ink outline around it, so
    holes are only created where the artwork's own outline is broken."""
    height, width = image.shape[:2]
    background_mask = np.zeros((height, width), np.uint8)

    xs = list(range(0, width, FLOOD_SEED_STEP)) + [width - 1]
    ys = list(range(0, height, FLOOD_SEED_STEP)) + [height - 1]
    seeds = [(x, 0) for x in xs] + [(x, height - 1) for x in xs]
    seeds += [(0, y) for y in ys] + [(width - 1, y) for y in ys]

    for seed_x, seed_y in seeds:
        if background_mask[seed_y, seed_x]:
            continue  # already reached by a previous flood
        flood_mask = np.zeros((height + 2, width + 2), np.uint8)
        cv2.floodFill(
            image.copy(),
            flood_mask,
            (seed_x, seed_y),
            newVal=0,
            loDiff=(FLOOD_DIFF,) * 3,
            upDiff=(FLOOD_DIFF,) * 3,
        )
        background_mask |= flood_mask[1:-1, 1:-1] * 255

    return background_mask


def remove_white_background(image: np.ndarray) -> np.ndarray:
    """Convert the cropped artwork to RGBA, making the white page background
    transparent while keeping bright regions inside the artwork itself
    (e.g. highlights) opaque."""
    blurred = cv2.GaussianBlur(image, (5, 5), 0)
    background_mask = _background_mask_by_flood_fill(blurred)
    foreground_mask = cv2.morphologyEx(
        255 - background_mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)
    )

    bgra = cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)
    bgra[:, :, 3] = foreground_mask
    return bgra


def next_available_output_path(folder: Path, piece: str) -> Path:
    """Smallest-numbered <piece><n>.png in folder that doesn't already exist."""
    n = 1
    while True:
        candidate = folder / f"{piece}{n}.png"
        if not candidate.exists():
            return candidate
        n += 1


def process_image(jpg_path: Path) -> Path:
    image = cv2.imread(str(jpg_path))
    if image is None:
        raise FrameNotFoundError(f"could not read image: {jpg_path}")

    corners = find_frame_corners(image)
    warped = warp_to_rectangle(image, corners)

    marker = detect_piece_by_marker(warped)
    if marker is not None:
        piece, region = marker
        warped = erase_marker(warped, region)
    else:
        piece = piece_from_filename(jpg_path.name)

    if piece is None:
        raise PieceNotIdentifiedError(
            "no color marker or filename match identifies the piece type"
        )

    target_size = TARGET_SIZE[piece]
    warped = correct_rotation(warped, target_size)
    warped = trim_border(warped)
    check_aspect_ratio(warped, jpg_path.name, target_size)

    resized = cv2.resize(warped, target_size, interpolation=cv2.INTER_AREA)
    transparent = remove_white_background(resized)

    output_path = next_available_output_path(jpg_path.parent, piece)
    cv2.imwrite(str(output_path), transparent)
    return output_path


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path/to/image.jpg>", file=sys.stderr)
        return 2

    jpg_path = Path(sys.argv[1])
    try:
        output_path = process_image(jpg_path)
    except (FrameNotFoundError, PieceNotIdentifiedError) as exc:
        print(f"[WARN] {jpg_path.name}: {exc}, skipping", file=sys.stderr)
        return 1

    print(f"[OK] {jpg_path.name} -> {output_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
