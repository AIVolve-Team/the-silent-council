"""The deterministic detector that decides whether a contract PDF needs the visual skill, and the page renderer for it.

No model: rules on the objects of each page. One signal is enough to make a PDF complex, and the inspection
records which signals fired and on which pages:

1. scanned: almost no text layer, or an image covering at least half of the page (SCAN_COVER);
2. image: raster images covering at least MIN_IMAGE_AREA of a page (initials, signatures, stamps), except an image
   repeated at the same place and size on (almost) every page, a logo or a letterhead;
3. signature_field and annotation: AcroForm signature fields, ink, stamp, free-text and note annotations;
4. drawing: many curve segments on a page, a signature drawn as vector paths. Repeated paths do not count, nor do
   closed convex outlines: a rounded rectangle, a circle, an ellipse or a pill, which Chrome and other HTML-to-PDF
   tools draw for every CSS rounded box (border-radius), list bullet and dot, so a report made from HTML does not fire
   on every page;
5. hidden_text: text a person cannot see (invisible render mode, white or near-white on a light background,
   transparent, outside the page or in a tiny font). visible_text() removes it from the text the council reads, so
   a white-on-white instruction does not reach the agents through the text path.

The visual pages (signals 1-4) are the ones the first agent looks at; hidden text alone makes the PDF complex but needs
no image. Plain-text PDFs have no signal and keep today's path. skill_text() builds the visual skill for those pages
from council/data/skill/visual, with only the sections the signals call for (SECTIONS_BY_KIND).

Not seen as hidden, so kept in the text: text covered by an opaque box or image, dark text on a dark fill, text cut away
by a clipping path, and invisible text on a page with a scan-sized image, taken as the scan's OCR even when the image is
blank (that page still fires `scanned`, so the visual mode sees it).

Only pypdfium2 (Apache-2.0/BSD-3), Pillow and, for visible_text, pypdf (BSD-3): the module imports nothing from the
package, so it loads without the engine and torch.
"""

from __future__ import annotations

import ctypes
import io
import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import pypdfium2
import pypdfium2.raw as pdfium_c
from PIL import Image, ImageStat

# Below this many characters a page has no real text layer: a scan, or a page that is only a picture.
MIN_TEXT_CHARS = 20
# 0.1% of the page: handwritten initials (about 0.2% of A4/Letter), a signature or a stamp (1-5%) pass; bullets,
# rules and icons do not. Initials pages must count, or the model cannot compare them and see which page lacks them.
MIN_IMAGE_AREA = 0.001
# One image over half of the page is a scan: scanners, phone apps and "print to PDF" leave margins (half an inch on
# Letter leaves 80% of the page, one inch 63%) and a slight rotation shrinks the box. Such an image is never a
# letterhead, even at the same place on every page, and the invisible text over it is its OCR.
SCAN_COVER = 0.5
# Default longest side of a render: enough for small print and handwriting, within Gemma 4's largest visual budget.
MAX_SIDE = 1536
# Recursion into form XObjects, where some producers wrap scans and stamps.
MAX_DEPTH = 15

# Repeated objects: positions and sizes rounded to 2 points, so the same logo placed by a program matches exactly.
REPEAT_GRID = 2.0
# A logo needs at least 3 pages to be told from a mark: on 1-2 pages the same box can be a signature on each.
MIN_REPEAT_PAGES = 3
# On at least 90% of the pages, or on every page but the cover: letterheads are on every page, while initials that
# miss one page (document A, page 2) are exactly what the reviewer must see, so "half of the pages" is too loose.
REPEAT_SHARE = 0.9

# A drawn signature has dozens to hundreds of curve segments (document D: 66). Closed convex outlines do not count at
# all (below), so the curves left on a page are open strokes and free shapes.
MIN_CURVES = 40
# A closed convex outline turns one way only, once around: a box, round or square, a circle, an ellipse, a pill, or a
# CSS border ring (outer and inner box in one path). Chrome (Skia) draws a 4-pixel list bullet as 16 cubic curves and a
# 14-pixel dot as 32, so the number of curves says nothing; a signature is open strokes, or an outline that turns both
# ways. Turning back by less than this, in radians and in all, is rounding in the producer.
TURN_TOLERANCE = 0.2
# Points closer than this fraction of the outline's size are one point: a control point on its end, float noise.
SAME_POINT = 0.005

# Light text (luminance from 0 to 255) is checked against what lies behind it; dark text on a light page is normal.
NEAR_WHITE = 200
# Less than this luminance difference from its background and a person does not read the text: white on white is 0,
# a light-gray watermark on white (200 on 255) still passes.
MIN_CONTRAST = 40
# Fill alpha below 10% is transparent text.
MIN_ALPHA = 26
# Under 2 points, text is a dot to the eye: real fine print is 5 points or more.
MIN_FONT_SIZE = 2.0
# Scale of the background render for the contrast check: 72 dpi resolves a 9-point line.
CONTRAST_SCALE = 1.0
# Longest detail recorded for a signal.
MAX_DETAIL = 60

SIGNAL_KINDS = ("scanned", "image", "signature_field", "annotation", "drawing", "hidden_text")
# The kinds that need the page as an image; hidden text is handled in the text.
VISUAL_KINDS = frozenset(SIGNAL_KINDS) - {"hidden_text"}

# The sections of the visual skill, in the order they appear in it, and those each signal calls for: the first expert
# reads only what can be on its pages, so a short skill leaves more of the context to the contract.
SECTIONS = ("signatures", "stamps", "handwriting", "tables", "scans")
SECTIONS_BY_KIND = {
    "signature_field": ("signatures",),
    "drawing": ("signatures", "handwriting"),  # vector curves: a drawn signature or handwriting
    "annotation": ("signatures", "handwriting", "stamps"),  # ink, stamp, free-text and note annotations
    "image": ("signatures", "stamps", "handwriting", "tables"),  # a raster image can be any mark, or a table
    "scanned": SECTIONS,  # a scan holds everything, and its clauses exist only in the image
    "hidden_text": (),  # removed from the text, never shown as an image
}
SKILL_DIR = Path(__file__).resolve().parents[2] / "data" / "skill" / "visual"

_INVISIBLE_MODES = (pdfium_c.FPDF_TEXTRENDERMODE_INVISIBLE, pdfium_c.FPDF_TEXTRENDERMODE_CLIP)
_STROKE_MODES = (pdfium_c.FPDF_TEXTRENDERMODE_STROKE, pdfium_c.FPDF_TEXTRENDERMODE_STROKE_CLIP)
_FILL_STROKE_MODES = (pdfium_c.FPDF_TEXTRENDERMODE_FILL_STROKE, pdfium_c.FPDF_TEXTRENDERMODE_FILL_STROKE_CLIP)
_ANNOTATIONS = {
    pdfium_c.FPDF_ANNOT_INK: "ink annotation",
    pdfium_c.FPDF_ANNOT_STAMP: "stamp annotation",
    pdfium_c.FPDF_ANNOT_FREETEXT: "free-text annotation",
    pdfium_c.FPDF_ANNOT_TEXT: "note annotation",
}


@dataclass(frozen=True)
class Signal:
    """One reason why a page makes the PDF complex."""

    page: int  # 1-based
    kind: str  # one of SIGNAL_KINDS
    detail: str  # short English, for the case record and the rapporteur


@dataclass
class PageInfo:
    """What the inspector sees on one page."""

    number: int  # 1-based
    chars: int  # characters in the text layer, hidden text included
    images: int  # raster image objects, including those nested in form XObjects and repeated ones
    image_area: float  # fraction of the page covered by images that are not repeated, overlaps summed, clipped to 1
    scanned: bool
    repeated_images: int = 0  # images ignored as logos or letterheads
    curves: int = 0  # Bezier segments in paths that are neither repeated nor closed convex outlines
    boxes: int = 0  # paths of closed convex outlines with curves (rounded boxes, circles, bullets), never counted

    @property
    def visual(self) -> bool:
        return self.scanned or self.image_area >= MIN_IMAGE_AREA


@dataclass
class PdfInspection:
    """The inspection of a whole PDF."""

    pages: list[PageInfo] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)

    @property
    def visual_pages(self) -> list[int]:
        """The 1-based numbers of the pages the skill should look at."""
        return sorted({s.page for s in self.signals if s.kind in VISUAL_KINDS})

    @property
    def hidden_pages(self) -> list[int]:
        """The 1-based numbers of the pages with hidden text, which visible_text removes."""
        return sorted({s.page for s in self.signals if s.kind == "hidden_text"})

    @property
    def complex(self) -> bool:
        """True when at least one signal fired. Hidden text alone gives a complex PDF without visual pages."""
        return bool(self.signals)

    def as_dict(self) -> dict:
        """JSON-ready, for the case record."""
        return {
            "complex": self.complex,
            "visual_pages": self.visual_pages,
            "signals": [{"page": s.page, "kind": s.kind, "detail": s.detail} for s in self.signals],
        }


# --- Geometry ---


def _page_bounds(obj) -> tuple[float, float, float, float]:
    """The bounds of a page object in page coordinates (left, bottom, right, top)."""
    get = getattr(obj, "get_bounds", None) or obj.get_pos  # get_pos is the pypdfium2 4.x name
    left, bottom, right, top = get()
    # Objects inside a form XObject are located in the form's space: bring the corners up through each container.
    container = obj.container
    while container is not None:
        matrix = container.get_matrix()
        xs, ys = zip(*(matrix.on_point(x, y) for x in (left, right) for y in (bottom, top)))
        left, bottom, right, top = min(xs), min(ys), max(xs), max(ys)
        container = container.container
    return left, bottom, right, top


def _scale(matrix) -> float:
    """The linear scale of a matrix: 1 for a translation, 0.1 for a tenfold shrink."""
    return math.sqrt(abs(matrix.a * matrix.d - matrix.b * matrix.c))


def _key(bounds: tuple[float, float, float, float]) -> tuple[int, ...]:
    """Rounded position and size: the identity of a logo across pages."""
    left, bottom, right, top = bounds
    return tuple(round(v / REPEAT_GRID) for v in (left, bottom, right - left, top - bottom))


def _repeated(keys_per_page: list[set], pages: int) -> set:
    """The keys found on (almost) every page: logos, letterheads and their vector twins."""
    counts = Counter(k for keys in keys_per_page for k in keys)
    out = set()
    for key, count in counts.items():
        if count < MIN_REPEAT_PAGES:
            continue
        missing = [i for i, keys in enumerate(keys_per_page) if key not in keys]
        if count >= REPEAT_SHARE * pages or missing == [0]:
            out.add(key)
    return out


def _address(handle) -> int | None:
    return ctypes.cast(handle, ctypes.c_void_p).value


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


# --- Hidden text ---


def _utf16(call, *args) -> str:
    """Calls a pdfium getter that fills a UTF-16LE buffer, sized by a first call."""
    size = call(*args, None, 0)
    if size <= 2:
        return ""
    buffer = (ctypes.c_ushort * (size // 2))()
    call(*args, buffer, size)
    return bytes(buffer).decode("utf-16-le", "replace").rstrip("\x00")


def _color(obj, getter) -> tuple[int, int, int, int] | None:
    r, g, b, a = (ctypes.c_uint() for _ in range(4))
    if not getter(obj, ctypes.byref(r), ctypes.byref(g), ctypes.byref(b), ctypes.byref(a)):
        return None  # a pattern or a colour space pdfium does not convert: assume visible
    return r.value, g.value, b.value, a.value


def _luminance(r: float, g: float, b: float) -> float:
    return 0.299 * r + 0.587 * g + 0.114 * b


def _hidden_text(page, textpage, ocr_layer: bool) -> list[tuple[object, str, str]]:
    """The text objects a person cannot see, as (object, reason, text).

    ocr_layer: the page is a scan, so its invisible text is the OCR of the image (OCRmyPDF and scanners write it in
    render mode 3), which a person does read on the image: it stays."""
    box_left, box_bottom, box_right, box_top = page.get_bbox()
    found, light = [], []
    objects = list(page.get_objects(filter=(pdfium_c.FPDF_PAGEOBJ_TEXT,), max_depth=MAX_DEPTH))
    for obj in objects:
        left, bottom, right, top = _page_bounds(obj)
        mode = pdfium_c.FPDFTextObj_GetTextRenderMode(obj)
        size = ctypes.c_float()
        pdfium_c.FPDFTextObj_GetFontSize(obj, ctypes.byref(size))
        # The font size is in text space: the object's matrix and those of its form XObjects scale it on the page.
        effective = size.value * _scale(obj.get_matrix())
        container = obj.container
        while container is not None:
            effective *= _scale(container.get_matrix())
            container = container.container
        stroke = mode in _STROKE_MODES
        color = _color(obj, pdfium_c.FPDFPageObj_GetStrokeColor if stroke else pdfium_c.FPDFPageObj_GetFillColor)
        if mode in _FILL_STROKE_MODES:
            # Outlined text (white fill, dark outline) is read by its outline: the darker of the two colours counts.
            outline = _color(obj, pdfium_c.FPDFPageObj_GetStrokeColor)
            if color is None or (outline is not None and _luminance(*outline[:3]) < _luminance(*color[:3])):
                color = outline
        reason = None
        if mode in _INVISIBLE_MODES:
            reason = None if ocr_layer else "invisible text"
        elif right <= box_left or left >= box_right or top <= box_bottom or bottom >= box_top:
            reason = "text outside the page"
        elif effective < MIN_FONT_SIZE:
            reason = "tiny text"
        elif color is not None and color[3] < MIN_ALPHA:
            reason = "transparent text"
        elif color is not None and _luminance(*color[:3]) >= NEAR_WHITE:
            light.append((obj, color, (left, bottom, right, top)))
        if reason:
            found.append((obj, reason))
    if light:
        found += _low_contrast(page, objects, light)
    texts = [(obj, reason, _utf16(pdfium_c.FPDFTextObj_GetText, obj, textpage)) for obj, reason in found]
    return [t for t in texts if t[2].strip()]  # white spaces hide nothing


def _low_contrast(page, objects, light) -> list[tuple[object, str]]:
    """The light text objects whose background is about as light: white on white. White on a dark band is visible."""
    # The background without any text, so the glyphs do not tint the region they are measured on.
    for obj in objects:
        pdfium_c.FPDFPageObj_SetIsActive(obj, False)
    try:
        bitmap = page.render(scale=CONTRAST_SCALE)
        image = bitmap.to_pil().convert("L")
        convert = bitmap.get_posconv(page)
    finally:
        for obj in objects:
            pdfium_c.FPDFPageObj_SetIsActive(obj, True)
    out = []
    for obj, color, (left, bottom, right, top) in light:
        corners = [convert.to_bitmap(x, y) for x in (left, right) for y in (bottom, top)]
        xs, ys = [p[0] for p in corners], [p[1] for p in corners]
        region = (
            max(math.floor(min(xs)), 0),
            max(math.floor(min(ys)), 0),
            min(math.ceil(max(xs)), image.width),
            min(math.ceil(max(ys)), image.height),
        )
        if region[2] <= region[0] or region[3] <= region[1]:
            continue
        background = ImageStat.Stat(image.crop(region)).mean[0]
        if abs(_luminance(*color[:3]) - background) < MIN_CONTRAST:
            out.append((obj, "white text" if min(color[:3]) >= 250 else "near-white text"))
    bitmap.close()
    return out


# --- Pages ---


def _images(page) -> list[tuple[tuple, float]]:
    """The raster images of a page as (key, fraction of the page covered)."""
    box_left, box_bottom, box_right, box_top = page.get_bbox()
    page_area = max((box_right - box_left) * (box_top - box_bottom), 1e-9)
    out = []
    for obj in page.get_objects(filter=(pdfium_c.FPDF_PAGEOBJ_IMAGE,), max_depth=MAX_DEPTH):
        left, bottom, right, top = _page_bounds(obj)
        width = min(right, box_right) - max(left, box_left)
        height = min(top, box_top) - max(bottom, box_bottom)
        area = width * height / page_area if width > 0 and height > 0 else 0.0
        out.append((_key((left, bottom, right, top)), area))
    return out


def _convex_outline(points: list[tuple[float, float]], closed: bool) -> bool:
    """A closed subpath that turns one way only, once around (TURN_TOLERANCE): a box, round or square, a circle."""
    xs, ys = [x for x, _ in points], [y for _, y in points]
    near = max(SAME_POINT * max(max(xs) - min(xs), max(ys) - min(ys)), 1e-3)
    if not closed and math.dist(points[0], points[-1]) > near:  # a circle often ends on its start without a close
        return False
    ring: list[tuple[float, float]] = []
    for p in points:
        if not ring or math.dist(p, ring[-1]) > near:
            ring.append(p)
    while len(ring) > 2 and math.dist(ring[0], ring[-1]) <= near:
        ring.pop()
    if len(ring) < 3:
        return False
    # The turn at every corner of the control polygon, the closing edge included: a convex outline's turns add up to
    # one full turn, all on one side.
    left = right = 0.0
    for (ax, ay), (bx, by), (cx, cy) in zip(ring[-2:] + ring[:-2], ring[-1:] + ring[:-1], ring):
        ux, uy, vx, vy = bx - ax, by - ay, cx - bx, cy - by
        turn = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        if turn > 0:
            left += turn
        else:
            right -= turn
    return min(left, right) <= TURN_TOLERANCE and abs(abs(left - right) - 2 * math.pi) <= TURN_TOLERANCE


def _curves(obj) -> tuple[int, bool]:
    """The Bezier segments of a path object and whether they all lie in closed convex outlines (a box)."""
    subpaths: list[list[tuple[float, float]]] = []
    closed: list[bool] = []
    bezier: list[int] = []
    x, y = ctypes.c_float(), ctypes.c_float()
    for i in range(pdfium_c.FPDFPath_CountSegments(obj)):
        segment = pdfium_c.FPDFPath_GetPathSegment(obj, i)
        kind = pdfium_c.FPDFPathSegment_GetType(segment)
        # Points in the path's own space: an affine matrix keeps a convex outline convex on the page.
        pdfium_c.FPDFPathSegment_GetPoint(segment, ctypes.byref(x), ctypes.byref(y))
        if kind == pdfium_c.FPDF_SEGMENT_MOVETO or not subpaths:
            subpaths.append([])
            closed.append(False)
            bezier.append(0)
        subpaths[-1].append((x.value, y.value))
        closed[-1] = closed[-1] or bool(pdfium_c.FPDFPathSegment_GetClose(segment))
        bezier[-1] += kind == pdfium_c.FPDF_SEGMENT_BEZIERTO
    # pdfium lists the two control points and the end of a cubic curve as three BEZIERTO points.
    curves = sum(bezier) // 3
    # Straight subpaths (rules, table lines) have no curve to count: only the curved ones must be outlines.
    box = curves > 0 and all(_convex_outline(p, c) for p, c, b in zip(subpaths, closed, bezier) if b)
    return curves, box


def _paths(page) -> list[tuple[tuple, int, bool]]:
    """The paths with curves on a page as (key, Bezier segments, closed box)."""
    out = []
    for obj in page.get_objects(filter=(pdfium_c.FPDF_PAGEOBJ_PATH,), max_depth=MAX_DEPTH):
        curves, box = _curves(obj)
        if curves:
            out.append((_key(_page_bounds(obj)), curves, box))
    return out


def _annotations(pdf, page) -> list[tuple[str, str]]:
    """Signature fields and the annotations a person adds by hand, as (kind, label)."""
    out = []
    for index in range(pdfium_c.FPDFPage_GetAnnotCount(page)):
        annot = pdfium_c.FPDFPage_GetAnnot(page, index)
        if not annot:
            continue
        try:
            subtype = pdfium_c.FPDFAnnot_GetSubtype(annot)
            if subtype == pdfium_c.FPDF_ANNOT_WIDGET:
                if pdfium_c.FPDFAnnot_GetFormFieldType(pdf.formenv, annot) == pdfium_c.FPDF_FORMFIELD_SIGNATURE:
                    out.append(("signature_field", "signature field, " + _signature_state(annot)))
            elif subtype in _ANNOTATIONS:
                label = _ANNOTATIONS[subtype]
                contents = _utf16(pdfium_c.FPDFAnnot_GetStringValue, annot, b"Contents")
                out.append(("annotation", f"{label}: '{contents}'" if contents.strip() else label))
        finally:
            pdfium_c.FPDFPage_CloseAnnot(annot)
    return out


def _signature_state(annot) -> str:
    """Signed when the field (or its parent, for a widget kid) holds a signature value."""
    if pdfium_c.FPDFAnnot_HasKey(annot, b"V"):
        return "signed"
    parent = pdfium_c.FPDFAnnot_GetLinkedAnnot(annot, b"Parent")
    if parent:
        try:
            if pdfium_c.FPDFAnnot_HasKey(parent, b"V"):
                return "signed"
        finally:
            pdfium_c.FPDFPage_CloseAnnot(parent)
    return "empty"


def _labels(kind: str, labels: list[str], number: int) -> list[Signal]:
    """One signal per distinct label, counted: "3 ink annotations" rather than three signals."""
    out = []
    for label, count in Counter(labels).items():
        text = label if count == 1 else f"{count} x {label}"
        out.append(Signal(number, kind, _clip(text, MAX_DETAIL)))
    return out


def _open(data: bytes):
    pdf = pypdfium2.PdfDocument(data)
    pdf.init_forms()  # before any page is loaded: pdfium needs the form environment to type the widgets
    return pdf


def inspect_pdf(data: bytes) -> PdfInspection:
    """Inspect every page of a PDF given as bytes."""
    pdf = _open(data)
    try:
        raw = []
        for index in range(len(pdf)):
            page = pdf[index]
            try:
                textpage = page.get_textpage()
                try:
                    chars = textpage.count_chars()
                    images = _images(page)
                    cover = max((a for _, a in images), default=0.0)
                    hidden = _hidden_text(page, textpage, ocr_layer=cover >= SCAN_COVER)
                finally:
                    textpage.close()
                raw.append((chars, images, cover, _paths(page), _annotations(pdf, page), hidden))
            finally:
                page.close()
    finally:
        pdf.close()

    count = len(raw)
    # A scan has a page-sized image at the same place on every page: that is the scan, not a letterhead.
    repeated_images = _repeated([{k for k, a in r[1] if a < SCAN_COVER} for r in raw], count)
    repeated_paths = _repeated([{k for k, _, _ in r[3]} for r in raw], count)
    inspection = PdfInspection()
    for number, (chars, images, cover, paths, marks, hidden) in enumerate(raw, start=1):
        kept = [a for k, a in images if k not in repeated_images or a >= SCAN_COVER]
        area = min(sum(kept), 1.0)
        curves = sum(n for k, n, box in paths if not box and k not in repeated_paths)
        scanned = cover >= SCAN_COVER or (chars < MIN_TEXT_CHARS and area >= MIN_IMAGE_AREA)
        inspection.pages.append(
            PageInfo(
                number=number,
                chars=chars,
                images=len(images),
                image_area=area,
                scanned=scanned,
                repeated_images=len(images) - len(kept),
                curves=curves,
                boxes=sum(1 for _, _, box in paths if box),
            )
        )
        if scanned:
            # The scan holds whatever images the page has: one signal, not two.
            what = "no text layer" if chars < MIN_TEXT_CHARS else f"{chars} text characters"
            inspection.signals.append(Signal(number, "scanned", f"{what}, images cover {area:.0%} of the page"))
        elif area >= MIN_IMAGE_AREA:
            many = f"{len(kept)} raster images" if len(kept) > 1 else "raster image"
            inspection.signals.append(Signal(number, "image", f"{many} {area:.1%} of the page"))
        for kind in ("signature_field", "annotation"):
            inspection.signals += _labels(kind, [label for k, label in marks if k == kind], number)
        if curves >= MIN_CURVES:
            inspection.signals.append(Signal(number, "drawing", f"{curves} curve segments"))
        # The length, never the words: the hidden text is what must not reach an agent, and the signals go into the
        # case and back to Evolus's agent in the response.
        by_reason: Counter = Counter()
        for _, reason, text in hidden:
            by_reason[reason] += len(" ".join(text.split()))
        for reason, chars in by_reason.items():
            inspection.signals.append(Signal(number, "hidden_text", f"{reason}, {chars} characters"))
    return inspection


# --- Text for the council ---


def _text_without(textpage, hidden: set) -> str:
    """The page's text from pdfium's text layer, minus the characters of the hidden objects. Lines left empty by the
    removal go; the others keep pdfium's reading order."""
    lines: list[list[str]] = [[]]
    dropped = [False]
    for index in range(textpage.count_chars()):
        obj = pdfium_c.FPDFText_GetTextObject(textpage, index)
        if obj and _address(obj) in hidden:
            dropped[-1] = True
            continue
        code = pdfium_c.FPDFText_GetUnicode(textpage, index)
        if code == 0x0A:
            lines.append([])
            dropped.append(False)
        elif code == 0x02:
            lines[-1].append("-")  # pdfium's mark for a hyphen at the end of a line
        elif code >= 0x20 or code == 0x09:
            lines[-1].append(chr(code))
    kept = []
    for chars, was_dropped in zip(lines, dropped):
        line = "".join(chars)
        if was_dropped:
            line = line.strip()
            if not line:
                continue
        kept.append(line)
    # pdfium returns UTF-16 halves for characters beyond the BMP: pair them again.
    return "\n".join(kept).encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")


def visible_text(data: bytes) -> str:
    """The PDF's text without hidden text, page by page joined with "\\n".

    A page without hidden text gives exactly what pypdf's extract_text gives, the extractor the service already uses,
    so a clean PDF reads as today. A page with hidden text is read from pdfium's text layer with the characters of the
    hidden objects left out: pdfium tells which object each character comes from, pypdf does not, and removing the
    objects and saving the page again breaks pypdf's text when they sit inside form XObjects."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pdf = _open(data)
    try:
        texts = []
        for index in range(len(pdf)):
            page = pdf[index]
            try:
                textpage = page.get_textpage()
                try:
                    cover = max((a for _, a in _images(page)), default=0.0)
                    hidden = {_address(obj.raw) for obj, _, _ in _hidden_text(page, textpage, cover >= SCAN_COVER)}
                    if hidden:
                        texts.append(_text_without(textpage, hidden))
                    else:
                        texts.append(reader.pages[index].extract_text() or "")
                finally:
                    textpage.close()
            finally:
                page.close()
        return "\n".join(texts)
    finally:
        pdf.close()


def render_pages(data: bytes, pages: list[int], *, max_side: int = MAX_SIDE) -> list[Image.Image]:
    """Render the given 1-based pages as RGB images whose longest side is about max_side pixels."""
    pdf = pypdfium2.PdfDocument(data)
    try:
        images = []
        for number in pages:
            if not 1 <= number <= len(pdf):
                raise ValueError(f"page {number} out of range 1..{len(pdf)}")
            page = pdf[number - 1]
            try:
                width, height = page.get_size()
                bitmap = page.render(scale=max_side / max(width, height))
                # convert copies the pixels, so the image outlives the bitmap and the document.
                images.append(bitmap.to_pil().convert("RGB"))
                bitmap.close()
            finally:
                page.close()
        return images
    finally:
        pdf.close()


# --- The visual skill ---


def skill_sections(signals: Iterable) -> list[str]:
    """The skill sections the signals call for, in SECTIONS order; empty when no signal needs an image.

    signals: Signal objects, their as_dict() records or bare kinds."""
    wanted = set()
    for signal in signals:
        kind = signal if isinstance(signal, str) else signal["kind"] if isinstance(signal, dict) else signal.kind
        wanted.update(SECTIONS_BY_KIND.get(kind, ()))
    return [s for s in SECTIONS if s in wanted]


def skill_text(signals_or_sections: Iterable) -> str:
    """The visual skill for the first expert: the intro, the bullets of the chosen sections under "What to look for"
    and how to report. Takes signals (as skill_sections does) or section names; SECTIONS gives the whole skill.

    With no section at all (pages sent without a visual signal) every section is loaded: the report refers to the
    list, and a skill without one would leave the model nothing to look for."""
    items = list(signals_or_sections)
    if items and all(isinstance(i, str) and i in SECTIONS for i in items):
        chosen = [s for s in SECTIONS if s in items]
    else:
        chosen = skill_sections(items)
    chosen = chosen or list(SECTIONS)

    def read(name: str) -> str:
        return (SKILL_DIR / f"{name}.md").read_text(encoding="utf-8").strip()

    bullets = "\n".join(read(s) for s in chosen)
    return f"{read('intro')}\n\n## What to look for\n\n{bullets}\n\n{read('report')}"
