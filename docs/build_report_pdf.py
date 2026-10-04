"""Build docs/TECHNICAL_REPORT.pdf (A4, max 6 pages).   python docs/build_report_pdf.py"""
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, Paragraph, Preformatted, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"
pdfmetrics.registerFont(TTFont("DV", FONT_DIR + "DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DV-B", FONT_DIR + "DejaVuSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("DV-I", FONT_DIR + "DejaVuSans-Oblique.ttf"))
pdfmetrics.registerFont(TTFont("DV-BI", FONT_DIR + "DejaVuSans-BoldOblique.ttf"))
pdfmetrics.registerFont(TTFont("DVM", FONT_DIR + "DejaVuSansMono.ttf"))
pdfmetrics.registerFontFamily("DV", normal="DV", bold="DV-B", italic="DV-I", boldItalic="DV-BI")

INK, ACCENT, RULE = colors.HexColor("#1f2933"), colors.HexColor("#1d4e89"), colors.HexColor("#c9d3df")
body = ParagraphStyle("body", fontName="DV", fontSize=8.4, leading=11.2, textColor=INK, alignment=TA_LEFT, spaceAfter=3)
bullet = ParagraphStyle("bullet", parent=body, leftIndent=11, bulletIndent=2, spaceAfter=1.5)
h1 = ParagraphStyle("h1", parent=body, fontName="DV-B", fontSize=15, leading=19, textColor=ACCENT, spaceAfter=2)
h2 = ParagraphStyle("h2", parent=body, fontName="DV-B", fontSize=10.2, leading=13, textColor=ACCENT, spaceBefore=7, spaceAfter=3, keepWithNext=1)
small = ParagraphStyle("small", parent=body, fontSize=7.2, leading=9.2, textColor=colors.HexColor("#52606d"))
cell = ParagraphStyle("cell", parent=body, fontSize=7.4, leading=9.4, spaceAfter=0)
cellb = ParagraphStyle("cellb", parent=cell, fontName="DV-B")
code = ParagraphStyle("code", fontName="DVM", fontSize=6.6, leading=8.2, textColor=INK)

P = lambda t, s=body: Paragraph(t, s)
B = lambda t: Paragraph(t, bullet, bulletText="•")
M = lambda t: f'<font name="DVM" size="7.4">{t}</font>'


def table(rows, widths, header=True):
    data = [[Paragraph(str(c), cellb if (header and i == 0) else cell) for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1 if header else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.4, RULE),
          ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
          ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
    if header:
        st.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5")))
    t.setStyle(TableStyle(st))
    return t


def fig(path, width_mm):
    from PIL import Image as PILImage
    w, h = PILImage.open(path).size
    return Image(path, width=width_mm * mm, height=width_mm * mm * h / w)


def caption(t):
    return Paragraph(t, small)


S = []
S += [P("Technical report: roomscan, a LiDAR-tier room-scanning pipeline", h1),
      P("Applied AI Engineer case study, Round 2. Chinmay Kumar. October 2026. "
        f"Repository README: one command per capture, {M('bash reproduce.sh &lt;raw_zips&gt;')} regenerates every number here.", small)]

S += [P("1. Scope, stated plainly", h2),
      P("This submission delivers the <b>LiDAR tier only</b>: one command turns a Stray Scanner capture into a dimensioned "
        "multi-room plan (JSON plus rendered PNG) with drift correction and a drift ablation. <b>Not delivered:</b> photo and "
        "video tiers, damage detection, concealed-damage rules, scope line items, window detection, tape or laser ground "
        "truth, and the consumer-app head-to-head. Every gate that needs ground truth is therefore unscored. I chose to make "
        "one tier work end to end, measure it honestly and run a real fix loop, instead of writing thin stubs for all tiers "
        "that would produce confident garbage.")]

S += [P("2. Tier design and device matrix", h2),
      table([
          ["Tier", "Hardware", "Input", "Status", "Honest accuracy"],
          ["LiDAR", "iPhone 12 Pro and newer Pro, iPad Pro 2020+", "Stray Scanner: depth 256×192, confidence, ARKit poses, intrinsics",
           "implemented", "Wall faces repeat to ~4 cm (median) between captures. Room dimensions do <b>not</b> repeat to the gate "
           "(median 33 cm, 1 of 10 within it). Absolute accuracy versus tape: unmeasured."],
          ["Video", "any iPhone 15+", "handheld clip", "not implemented", "n/a"],
          ["Photo", "any iPhone 15+", "2–8 stills per room folder", "not implemented", "n/a"]],
          [14, 30, 38, 22, 70]),
      Spacer(1, 3),
      P("<b>Planned design for the missing tiers</b> (for discussion): one shared geometric core (gravity-aligned points in, "
        "plan out) with tier-specific front ends. Video: feed-forward reconstruction (e.g. VGGT or MASt3R-SfM) for poses plus a "
        "metric monocular depth model for scale. Photo: the same per room; rooms stitched by matching each doorway seen from "
        "both sides, then a layout solve under shared-wall and no-overlap constraints, with a protocol that asks for one photo "
        "of every doorway from inside each room. Intervals widened per tier from measured residuals.")]

S += [P("3. Architecture (LiDAR tier)", h2),
      Preformatted(
          "zip ─► capture.py ─► cloud.py ──────► drift.py ───────► plan.py ───────────────────► pipeline.py\n"
          "      read frames    15 s submaps,    floor anchor +     floor, Manhattan yaw,         JSON + PNG\n"
          "      back-project   2 cm voxels      2D ICP per submap  walls, rooms, outlines,\n"
          "                                                         ceiling, openings", code),
      Spacer(1, 3),
      B("<b>Back-projection.</b> Only ARKit confidence-2 depth within 3.5 m is used. The pose convention was verified on the data, "
        "not assumed: with no axis flip the floor is a sharp plane 1.40–1.47 m below the phone (hand height); with the usual ARKit flip no floor exists."),
      B("<b>Floor and Manhattan yaw.</b> Floor = strongest 1 cm height bin in the lower half, refined by the median within ±3 cm. "
        "Yaw = the angle in 0–90° where wall-point histograms are spikiest: 0.25° steps over all points, refined to 0.02°. Assumes right-angled rooms; deterministic by design (§6)."),
      B("<b>Walls.</b> A 2 cm plan cell is wall if points fill at least 50% of its 10 cm height slabs between 0.3 and 1.8 m. "
        "Beds and tables are short and fail; doorways are empty below the lintel, so they appear as gaps."),
      B("<b>Rooms.</b> Interior (anything below 1.8 m, closed, holes filled, plus the walked path) minus walls gives free space. "
        "Eroding it by 0.5 m pinches doorways shut and leaves one seed per room; seeds regrow through free space only, so a "
        "label cannot cross a wall and rooms cannot overlap."),
      B("<b>Outlines.</b> Thin protrusions are removed with a <b>square</b> opening (a disk rounds corners, see §6), then contour, "
        "Douglas-Peucker (15 cm), each edge forced horizontal or vertical, and <b>snapped to the wall face</b>: the densest 5 mm bin "
        "within ±8 cm using only points above 1.1 m, so furniture edges cannot pass as walls. The ±8 cm window is below any "
        "wall thickness, so a snap cannot jump to the next room's face."),
      B("<b>Ceiling.</b> The highest well-supported slab above 2.1 m covering at least 25% of the room's floor area. The coverage test "
        "exists because a scan that never looked up still sees loft and wardrobe tops (the floor-only scan reported fake ceilings "
        "of 1.93–2.25 m before it); it now returns null with a reason."),
      B("<b>Openings.</b> Where two room labels touch, the touching span is a doorway and its length is the width.")]

S += [P("4. Drift handling", h2),
      P("ARKit drifts slowly, and rooms revisited later show doubled walls. Each 15 s submap is corrected in walking order in two steps. "
        "<b>Vertical, plane-anchored:</b> its floor is shifted onto the global floor (corrections up to 9 mm). <b>Horizontal:</b> 2D "
        "point-to-point ICP of its 0.3–1.8 m wall points against all submaps already placed, with the match radius shrinking from "
        "20 cm to 5 cm. A correction is accepted only if at least 30% of points overlap and the move is under 3° and 30 cm; larger "
        "moves indicate a wrong match, not drift, and are rejected. On the 3.6-minute flat scan 11 of 15 submaps were corrected."),
      table([
          ["Ablation, ceiling scan (15 submaps)", "poses as-is", "drift corrected"],
          ["Wall gap between submaps, p90", "5.91 cm", "5.01 cm"],
          ["Wall gap between submaps, median", "1.28 cm", "1.29 cm (unchanged)"],
          ["Stitched footprint", "64.06 m²", "65.23 m²"],
          ["Repeatability vs other capture, median room-dimension gap", "46.8 cm", "33.5 cm"]],
          [90, 40, 44]),
      Spacer(1, 3),
      fig("docs/figures/drift_ablation.png", 170),
      caption("Figure 1. Stitched footprint with drift correction off (left) and on (right), same capture."),
      P("Read with care: the median gap does not move, only the tail. The repeatability drop is partly because uncorrected doubled "
        "walls merge rooms during segmentation. On the other whole-flat scan (4 of 8 submaps corrected) the effect is negligible "
        "(p90 8.61 to 8.53 cm). <b>Limitation:</b> sequential alignment has no global loop closure, so error can accumulate along "
        "a long chain, and point-to-point ICP can slide along corridors. A pose graph over all submap pairs with point-to-line residuals is the next step.")]

S += [P("5. Error budget and calibration", h2),
      P("Per wall: σ² = σ<sub>end1</sub>² + σ<sub>end2</sub>² + (1%·L)². A wall end set by a face snapped to real points has σ = 4 cm; "
        "an end with no wall behind it (the scan simply stopped) has σ = 23 cm; room dimensions taken from the outline extent use σ = 23 cm. "
        "Ceiling: σ² = (4 mm)² + (1%·H)². Area propagates edge by edge (an edge of length L moved by σ changes area by L·σ). Intervals are 95% (±1.96σ). The 23 cm outline value comes from the same formula (21 cm on the corrected data; the wider value is kept)."),
      P("<b>Calibration analysis.</b> σ was chosen so that a 95% interval on the <i>gap</i> between two scans of the same face covers 95% of "
        "matched pairs: σ = p95(gap) / (1.96·√2), on the one repeat pair. The original 5 mm prior covered <b>10%</b> of 31 matched face "
        "pairs; the shipped 4 cm covers <b>94%</b>. <b>This is in-sample</b>: it proves the old prior was wrong, not that the new value holds on "
        "an unseen flat. Ceiling, scale and opening-width intervals are unvalidated priors, and <b>nothing is calibrated against tape</b>, "
        "because no tape ground truth was collected. On clean synthetic data (known two-room flat, 5 mm noise) the pipeline recovers "
        "dimensions to 0.0 cm and the ceiling to 2.60 m, but a 0.90 m door reads 0.86 m.")]

S += [P("6. Fix loop (full text and regenerable runs in fixloop/)", h2),
      P("<b>A determinism bug changed my numbers mid-way.</b> Running the pipeline on a second machine (numpy 1.26 instead of 2.4) moved one room by 36 cm. "
        "Cause: the Manhattan yaw search used a random 200,000-point subsample on a 0.25° grid. 0.24 µm of float noise changed the subsample, flipped a near-tie "
        "(27.50° vs 27.75°, scores within 0.1%) and rotated the whole planning grid. Fixed by searching all points and refining to 0.02°; verified identical rooms on "
        "numpy 1.26 and 2.4 for all three captures (including from the raw zip), and guarded by a test. Part of my first-pass results was tie-break luck, "
        "so I re-ran every step. Corrected results (10 matched dimensions, gate 1 cm or 0.5%):"),
      table([
          ["Step", "median |diff|", "max", "pass"],
          ["Before: old geometry", "40.0 cm", "82.0 cm", "0/10"],
          ["Declared fix: wall-to-wall dimensions", "37.9 cm", "79.0 cm", "0/10"],
          ["Follow-up 2: median-run 'typical' dimensions", "36.0 cm", "80.0 cm", "0/10"],
          ["<b>Follow-up 3: square kernels, snap evidence above 1.1 m</b>", "<b>33.5 cm</b>", "61.3 cm", "<b>1/10</b>"]],
          [104, 26, 24, 20]),
      Spacer(1, 3),
      B("<b>Declared fix</b> (first pass: predicted ≤ 4 cm, got 40.4 cm, 'worse'): on the corrected baseline it is almost neutral. It cannot work because 'opposite walls' is undefined when outlines differ."),
      B("<b>Follow-up 3</b>, found by a synthetic known-geometry test: a disk-shaped opening rounded room corners and put outline edges about 10 cm inside the walls, and a table edge passed as a wall face. "
        "The synthetic error fell from 20 cm to 0. On real data the gain is a modest 40.0 → 33.5 cm (16%)."),
      B("<b>Why the gate still fails:</b> wall faces repeat to a median 4.1 cm between the scans (a floor under the 1 cm gate); only 3 of 10 dimensions have a wall face at both ends in both scans "
        "(the other 7 end where the scan stopped, median gap 50.7 cm); some rooms are segmented differently. <b>Side effect:</b> footprints of the two scans differ by 9.4% (59.40 vs 65.23 m²), up from 5.4%; "
        "no ground truth says which is nearer."),
      B("<b>Prediction accounting:</b> the first two predictions were wrong. Follow-up 3's 'hit' (16.1 cm) was first-pass luck, since the same fix gives 33.5 cm on the corrected pipeline. "
        "Predictions were written in my notes before each run, not committed, so they cannot be timestamped. First-pass numbers stay reproducible with <font name=\"DVM\" size=\"7.4\">--legacy-yaw</font> (numpy 2.x only: that dependence was the bug)."),
      Spacer(1, 2)]

S += [KeepTogether([fig("docs/figures/plan_single_scan_with_ceiling.png", 105),
                    caption("Figure 2. Rendered plan of the ceiling scan, viewed from above: grey = wall points, orange = room outlines with dimensions "
                            "and ceiling height. Rooms cannot overlap by construction; R4 is the merged hall and living area (known failure mode, §7).")]),
      Spacer(1, 4),
      KeepTogether([fig("docs/figures/repeatability_overlay.png", 105),
                    caption("Figure 3. Room outlines of the two repeat captures overlaid after alignment (red: floor-only scan, blue: ceiling scan), "
                            "current code. Core walls coincide to a few cm; remaining differences are partly scanned rooms and rooms segmented differently.")])]

S += [P("7. Known failure modes", h2),
      B("<b>Wide openings merge rooms.</b> An opening wider than ~1 m (living room to corridor) is not pinched shut, so two spaces become one room (R4 in the ceiling scan, 29.4 m²)."),
      B("<b>Furniture in outlines.</b> Wardrobes taller than 1.1 m still pass the wall and snapping tests and can notch an outline."),
      B("<b>Open sides.</b> Balconies and unscanned walls give outlines bounded by where the scan stopped. These get σ = 23 cm and the wall is flagged as not measured."),
      B("<b>Opening widths read narrow</b> (0.86 m for a true 0.90 m on clean data), so the 2 cm opening gate would be missed. Windows are not detected."),
      B("<b>Two captures disagree on footprint by 9.4%</b> (59.40 vs 65.23 m²), partly from unscanned parts of rooms."),
      B("<b>Numerical sensitivity.</b> Discontinuous steps (grid binning, argmax over near-tied scores) can turn tiny float noise into large changes. The yaw search was one case and is fixed; other thresholds (e.g. the 0.5 m erosion that separates rooms) were not stress-tested."),
      B("<b>Mirrors, glass, wet-look surfaces, low light.</b> LiDAR returns through or into mirrors and glass create phantom space; wet-look surfaces can drop returns; low light degrades ARKit tracking "
        "and increases drift. The capture protocol addresses each (pass mirrors at an angle, all lights on), but none was tested."),
      B("<b>Non-Manhattan rooms</b> (angled walls) are forced to 90°.")]


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("DV", 7)
    canvas.setFillColor(colors.HexColor("#7b8794"))
    canvas.drawString(18 * mm, 10 * mm, "roomscan technical report, LiDAR tier")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"{doc.page}")
    canvas.restoreState()


if __name__ == "__main__":
    doc = SimpleDocTemplate("docs/TECHNICAL_REPORT.pdf", pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=15 * mm, bottomMargin=17 * mm, title="roomscan technical report",
                            author="Chinmay Kumar")
    doc.build(S, onFirstPage=footer, onLaterPages=footer)
    print("built docs/TECHNICAL_REPORT.pdf")
