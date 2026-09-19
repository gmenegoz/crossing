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
    "head": 5,
    "body": 110,
    "legback": 75,
    "legfront": 30,
    "tail": 15,
    "wing": 150,
}
MARKER_HUE_TOLERANCE = 10  # max distance from a palette hue to accept a match
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


AMBIGUITY_MARGIN = 3  # if the two nearest palette colors are this close together, treat as a tie


def _ranked_piece_hues(hue: float) -> list[tuple[str, float]]:
    """Palette pieces ranked nearest-first, each with its circular distance
    from the measured hue."""
    return sorted(PIECE_HUES.items(), key=lambda item: _hue_distance(hue, item[1]))


def piece_from_marker_hue(hue: float) -> str | None:
    """Nearest palette color within tolerance, unless the runner-up is
    nearly as close (within AMBIGUITY_MARGIN) — a real near-exact tie, e.g.
    a hue sitting almost equidistant between two colors, which shouldn't be
    resolved to whichever happens to round closer."""
    ranked = _ranked_piece_hues(hue)
    (nearest_piece, nearest_hue), (_runner_up_piece, runner_up_hue) = ranked[0], ranked[1]
    nearest_distance = _hue_distance(hue, nearest_hue)
    runner_up_distance = _hue_distance(hue, runner_up_hue)

    if nearest_distance > MARKER_HUE_TOLERANCE:
        return None
    if runner_up_distance - nearest_distance < AMBIGUITY_MARGIN:
        return None
    return nearest_piece


class MarkerDetectionResult:
    """Outcome of looking for a piece marker: either a confident match, or
    enough diagnostic detail (measured hue, nearest palette color) to explain
    why one wasn't found."""

    def __init__(
        self,
        piece: str | None,
        region: tuple[int, int, int, int] | None = None,
        corner_name: str | None = None,
        hue: float | None = None,
        nearest_piece: str | None = None,
        nearest_distance: float | None = None,
        runner_up_piece: str | None = None,
        runner_up_distance: float | None = None,
    ):
        self.piece = piece
        self.region = region
        self.corner_name = corner_name
        self.hue = hue
        self.nearest_piece = nearest_piece
        self.nearest_distance = nearest_distance
        self.runner_up_piece = runner_up_piece
        self.runner_up_distance = runner_up_distance

    def describe_failure(self) -> str:
        if self.hue is None:
            return "no saturated marker square found in any corner"
        if self.nearest_distance > MARKER_HUE_TOLERANCE:
            return (
                f"marker found (hue={self.hue:.0f}) but closest palette color is "
                f"'{self.nearest_piece}' (hue={PIECE_HUES[self.nearest_piece]}, "
                f"distance={self.nearest_distance:.0f}, tolerance={MARKER_HUE_TOLERANCE})"
            )
        return (
            f"marker found (hue={self.hue:.0f}) but ambiguous between "
            f"'{self.nearest_piece}' (distance={self.nearest_distance:.0f}) and "
            f"'{self.runner_up_piece}' (distance={self.runner_up_distance:.0f}), "
            f"within {AMBIGUITY_MARGIN} of each other"
        )


def detect_piece_by_marker(warped: np.ndarray) -> MarkerDetectionResult:
    """Look for a confident piece marker in any corner of the rectangle."""
    found = find_marker_corner(warped)
    if found is None:
        return MarkerDetectionResult(piece=None)
    corner_name, hue, x, y, w, h = found
    piece = piece_from_marker_hue(hue)
    ranked = _ranked_piece_hues(hue)
    nearest_piece, nearest_hue = ranked[0]
    runner_up_piece, runner_up_hue = ranked[1]
    if piece is None:
        return MarkerDetectionResult(
            piece=None,
            corner_name=corner_name,
            hue=hue,
            nearest_piece=nearest_piece,
            nearest_distance=_hue_distance(hue, nearest_hue),
            runner_up_piece=runner_up_piece,
            runner_up_distance=_hue_distance(hue, runner_up_hue),
        )
    return MarkerDetectionResult(piece=piece, region=(x, y, w, h), corner_name=corner_name, hue=hue)


def erase_marker(warped: np.ndarray, region: tuple[int, int, int, int]) -> np.ndarray:
    height, width = warped.shape[:2]
    erased = warped.copy()
    erased[height - 50 : height, width - 50: width] = np.array([0, 0, 0,0])
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
RING_PAD_FRACTION = 0.04  # ring thickness as a fraction of the candidate's larger dimension
MIN_RING_SIDE_PIXELS = 50  # a side with fewer ring pixels than this is treated as missing/off-frame


def is_framed_by_black_border(gray: np.ndarray, hull: np.ndarray) -> bool:
    """Check that a candidate white rectangle is fully enclosed by a darker
    border on all 4 sides (not just adjacent to another bright region like a
    stray photo or lightbox, and not touching the image edge on any side).

    The ring is built by dilating the hull's own filled mask and taking the
    difference, so it follows the true (possibly bowed/curved) boundary
    instead of assuming straight edges — a rigid rectangular offset strip
    can end up sampling real foreground on a curved edge's outward bulge.
    Ring pixels are then split into 4 directional groups by their angle from
    the candidate's centroid, and each of the 4 sides must independently be
    both present (enough pixels — rules out a side that's missing because it
    touches the image edge) and darker than the inner region."""
    img_height, img_width = gray.shape
    x, y, w, h = cv2.boundingRect(hull)

    mask = np.zeros(gray.shape, np.uint8)
    cv2.drawContours(mask, [hull], -1, 255, thickness=-1)
    if mask.sum() == 0:
        return False

    pad = max(10, int(RING_PAD_FRACTION * max(w, h)))
    kernel = np.ones((pad * 2 + 1, pad * 2 + 1), np.uint8)
    dilated = cv2.dilate(mask, kernel)
    ring = cv2.bitwise_and(dilated, cv2.bitwise_not(mask))
    ring[0, :] = ring[-1, :] = ring[:, 0] = ring[:, -1] = 0  # drop pixels that fell off-image

    ring_ys, ring_xs = np.nonzero(ring)
    if len(ring_xs) == 0:
        return False

    inner_mean = gray[mask > 0].mean()
    center_x, center_y = x + w / 2, y + h / 2
    dx = ring_xs - center_x
    dy = ring_ys - center_y
    is_vertical_side = np.abs(dy) > np.abs(dx)

    side_selectors = {
        "top": is_vertical_side & (dy < 0),
        "bottom": is_vertical_side & (dy > 0),
        "left": (~is_vertical_side) & (dx < 0),
        "right": (~is_vertical_side) & (dx > 0),
    }
    for selector in side_selectors.values():
        if selector.sum() < MIN_RING_SIDE_PIXELS:
            return False
        side_mean = gray[ring_ys[selector], ring_xs[selector]].mean()
        if side_mean >= inner_mean * RING_CONTRAST_RATIO:
            return False
    return True


MARKER_RESCUE_DILATION = 15  # px: how far from the white region a saturated patch can still be rescued


def _white_region_mask(gray: np.ndarray, image: np.ndarray) -> np.ndarray:
    """Otsu-threshold mask of the white rectangle, patched so a saturated
    marker sitting at/near its edge isn't carved out as a false notch.

    A colored marker can be dark enough in grayscale (despite being clearly
    saturated/colored) that Otsu classifies it as background, cutting a
    notch into the rectangle's contour right where the marker sits — this
    breaks both marker detection (the marker area is missing from the
    warped output) and the crop itself (a real notch can clip into nearby
    artwork). Fix: also treat saturated pixels as foreground, but ONLY
    within a small dilation of the existing white-region mask, so this
    can rescue a marker-sized notch at the rectangle's own edge without
    merging in unrelated saturated objects elsewhere in the photo (e.g. a
    stray colored photo, skin tone, or a second lightbox)."""
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, np.ones((45, 45), np.uint8))

    dilate_kernel = np.ones((MARKER_RESCUE_DILATION * 2 + 1,) * 2, np.uint8)
    near_white_region = cv2.dilate(closed, dilate_kernel)
    saturation = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)[:, :, 1]
    rescuable_saturated = cv2.bitwise_and(
        (saturation > MARKER_SATURATION_THRESHOLD).astype(np.uint8) * 255, near_white_region
    )

    combined = cv2.bitwise_or(thresh, rescuable_saturated)
    return cv2.morphologyEx(combined, cv2.MORPH_CLOSE, np.ones((45, 45), np.uint8))


def find_frame_corners(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Dark speckle noise in the artwork can touch the black frame border
    # (e.g. a jagged illustration edge close to the rectangle's edge),
    # cutting a notch into the white rectangle's contour. Closing bridges
    # such thin gaps; is_framed_by_black_border rejects any case where this
    # accidentally merges in a neighboring bright object instead.
    closed = _white_region_mask(gray, image)

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
        # The real scan target is a white rectangle fully enclosed by a black
        # frame; other bright regions in the shot (stray photos, lightboxes)
        # won't have a darker border on all 4 sides. Check this on the hull
        # itself (not a 4-point fit) so it still works even if the edges are
        # too bowed to reduce cleanly to 4 points below.
        if not is_framed_by_black_border(gray, hull):
            continue

        corners = fit_quad_corners(hull)
        if corners is not None:
            return expand_corners(order_corners(corners))

    raise FrameNotFoundError("no quadrilateral frame contour found")


CORNER_EXPAND_FRACTION = 0.06  # push detected corners outward by this fraction, away from center


def expand_corners(corners: np.ndarray) -> np.ndarray:
    """Push the 4 detected corners outward from their centroid by a small
    fraction. Otsu's threshold can classify a strip of true white page as
    background near the rectangle's actual edge — e.g. a shadow cast by the
    page's own raised edge creates a gradient rather than a clean white/black
    step, and the darker end of that gradient reads as background. That
    silently shrinks the detected rectangle inward of the true edge, which
    can clip artwork drawn close to the border. Deliberately overshooting is
    cheap to correct (trim_border and the black frame margin absorb the
    extra), whereas undershooting loses artwork with no way to recover it
    after the fact."""
    center = corners.mean(axis=0)
    return (center + (corners - center) * (1 + CORNER_EXPAND_FRACTION)).astype("float32")


def fit_quad_corners(hull: np.ndarray) -> np.ndarray | None:
    """Reduce a hull to its 4 corners. A camera's lens/perspective distortion
    can bow a physically straight edge just enough that approxPolyDP needs a
    5th point at a tight epsilon; retrying with a slightly looser epsilon
    lets mild bowing collapse to 4 points. If it still won't, fall back to
    minAreaRect's best-fit rotated rectangle, accepted only if it's a close
    match to the hull's actual area (otherwise the fallback could paper over
    a shape that genuinely isn't a quadrilateral)."""
    perimeter = cv2.arcLength(hull, True)
    for eps_fraction in (0.02, 0.03, 0.04, 0.05, 0.07, 0.1):
        approx = cv2.approxPolyDP(hull, eps_fraction * perimeter, True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            return approx.reshape(4, 2).astype("float32")

    rect = cv2.minAreaRect(hull)
    rect_area = rect[1][0] * rect[1][1]
    hull_area = cv2.contourArea(hull)
    if rect_area <= 0 or abs(hull_area - rect_area) / rect_area > 0.1:
        return None
    return cv2.boxPoints(rect).astype("float32")


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


TRIM_FRACTION = 0.045  # shave this fraction off each side to drop stray black-frame slivers


def trim_border(warped: np.ndarray) -> np.ndarray:
    """Detected corners can include a sliver of the black frame at the edges
    (perspective/threshold detection isn't pixel-perfect, and expand_corners
    deliberately over-shoots outward to avoid clipping artwork); shave a
    margin off each side before it's treated as foreground by background
    removal. Sized to match expand_corners' overshoot (~6%) rather than just
    covering detection jitter: measured against real photos, the black
    canvas/backdrop takes 2-6% of the image to fade to clean white paper, so
    trimming less than that leaves a visible dark sliver around the artwork.
    A user who draws too close to this margin may lose a bit of artwork to
    the trim — acceptable, since removing the frame takes priority and they
    can redraw with more clearance."""
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


# How a corner label transforms under one 90° clockwise rotation.
_CORNER_AFTER_CLOCKWISE_ROTATION = {"TL": "TR", "TR": "BR", "BR": "BL", "BL": "TL"}


def correct_rotation(warped: np.ndarray, target_size: tuple[int, int], marker_corner: str | None) -> np.ndarray:
    """Rotate the warped image so the marker (if any) ends up bottom-right —
    the corner convention the rest of the pipeline (erase_marker, etc.)
    assumes — while still matching the target's portrait/landscape
    orientation. Picking a single fixed rotation direction regardless of
    which corner the marker started in silently flips artwork upside down
    whenever the marker isn't already top-left/bottom-right relative to that
    fixed direction (e.g. a bottom-left marker needs the opposite rotation
    from a top-right one to end up bottom-right, even though both need "some
    90° turn" to fix portrait/landscape). With no marker there's nothing to
    anchor a rotation direction to, so fall back to the orientation-only
    heuristic."""
    if marker_corner is None:
        target_width, target_height = target_size
        height, width = warped.shape[:2]
        is_portrait_target = target_height >= target_width
        is_portrait_image = height >= width
        if is_portrait_target != is_portrait_image:
            return cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)
        return warped

    rotated = warped
    corner = marker_corner
    for _ in range(4):
        if corner == "BR":
            return rotated
        rotated = cv2.rotate(rotated, cv2.ROTATE_90_CLOCKWISE)
        corner = _CORNER_AFTER_CLOCKWISE_ROTATION[corner]
    return rotated  # unreachable: every corner reaches BR within 4 turns


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


def load_config(config_path: Path) -> dict[str, str]:
    """Parse config.txt's simple KEY=value lines into a dict."""
    config: dict[str, str] = {}
    for line in config_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        config[key.strip().upper()] = value.strip()
    return config


class ConfigError(Exception):
    pass


def resolve_run_config(config_path: Path, folder_override: str | None) -> tuple[Path, int, Path | None]:
    """Resolve FOLDER/INDEX/DESTINATION for a batch run. FOLDER can come from
    a CLI-provided override (folder_override) or config.txt; INDEX and
    DESTINATION always come from config.txt regardless of how FOLDER was
    chosen, per the agreed behavior for combining CLI and config-file usage."""
    if not config_path.is_file():
        raise ConfigError(f"config file not found: {config_path}")
    config = load_config(config_path)

    folder_str = folder_override if folder_override is not None else config.get("FOLDER")
    if not folder_str:
        raise ConfigError("no FOLDER given on the command line or in config.txt")
    folder = Path(folder_str)
    if not folder.is_dir():
        raise ConfigError(f"'{folder}' is not a directory")

    index_str = config.get("INDEX")
    if not index_str:
        raise ConfigError("config.txt is missing INDEX=<number>")
    try:
        index = int(index_str)
    except ValueError:
        raise ConfigError(f"config.txt's INDEX is not an integer: '{index_str}'") from None

    destination_str = config.get("DESTINATION")
    destination = Path(destination_str) if destination_str else None

    return folder, index, destination


def process_image(jpg_path: Path, index: int | None, destination: Path | None) -> Path:
    image = cv2.imread(str(jpg_path))
    if image is None:
        raise FrameNotFoundError(f"could not read image: {jpg_path}")

    corners = find_frame_corners(image)
    warped = warp_to_rectangle(image, corners)

    marker = detect_piece_by_marker(warped)
    if marker.piece is not None:
        piece = marker.piece
    else:
        piece = piece_from_filename(jpg_path.name)

    if piece is None:
        filename_note = "filename has no recognized piece substring either"
        raise PieceNotIdentifiedError(f"{marker.describe_failure()}; {filename_note}")

    target_size = TARGET_SIZE[piece]
    warped = correct_rotation(warped, target_size, marker.corner_name)
    warped = trim_border(warped)
    check_aspect_ratio(warped, jpg_path.name, target_size)

    resized = cv2.resize(warped, target_size, interpolation=cv2.INTER_AREA)
    transparent = remove_white_background(resized)
    transparent = erase_marker(transparent, marker.region)

    if index is None:
        output_path = next_available_output_path(jpg_path.parent, piece)
    else:
        output_path = jpg_path.parent / f"{piece}{index}.png"
    cv2.imwrite(str(output_path), transparent)

    if destination is not None:
        destination.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(destination / output_path.name), transparent)

    return output_path


def run_batch(config_path: Path, folder_override: str | None) -> int:
    """Process every JPG in FOLDER (from config.txt, optionally overridden by
    folder_override), naming each output <piece><INDEX>.png and optionally
    copying it to DESTINATION. This is the shared implementation behind both
    scan_folder.sh and scan_folder.bat, so config parsing and the
    FOLDER/INDEX/DESTINATION rules live in one place rather than being
    duplicated in bash and batch syntax."""
    try:
        folder, index, destination = resolve_run_config(config_path, folder_override)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    jpg_paths = sorted(folder.glob("*.jpg")) + sorted(folder.glob("*.JPG"))
    processed = 0
    skipped_failed = 0
    for jpg_path in jpg_paths:
        try:
            output_path = process_image(jpg_path, index, destination)
        except (FrameNotFoundError, PieceNotIdentifiedError) as exc:
            print(f"[ERR] {jpg_path.name}: {exc}, skipping", file=sys.stderr)
            skipped_failed += 1
            continue
        print(f"[OK] {jpg_path.name} -> {output_path.name}")
        processed += 1

    print(f"\nDone: {processed} processed, {skipped_failed} skipped (failed)")
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--config":
        if len(sys.argv) not in (3, 4):
            print(f"Usage: {sys.argv[0]} --config <config.txt> [folder]", file=sys.stderr)
            return 2
        config_path = Path(sys.argv[2])
        folder_override = sys.argv[3] if len(sys.argv) == 4 else None
        return run_batch(config_path, folder_override)

    if len(sys.argv) not in (2, 3):
        print(f"Usage: {sys.argv[0]} <path/to/image.jpg> [index]", file=sys.stderr)
        return 2

    jpg_path = Path(sys.argv[1])
    index = int(sys.argv[2]) if len(sys.argv) == 3 else None
    try:
        output_path = process_image(jpg_path, index, destination=None)
    except (FrameNotFoundError, PieceNotIdentifiedError) as exc:
        print(f"[ERR] {jpg_path.name}: {exc}, skipping", file=sys.stderr)
        return 1

    print(f"[OK] {jpg_path.name} -> {output_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
