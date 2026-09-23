"""Printed controller packet: per-case decision-tree flowcharts, body map,
turnover cards and sign-off block (docx), and the colour-coded controller
vitals workbook with green/red tracks and the patient-care checklist (xlsx)."""
import re
import textwrap
from collections import deque
from datetime import datetime
from io import BytesIO
from typing import Dict, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle  # noqa: E402
from docx import Document  # noqa: E402
from docx.enum.section import WD_ORIENT  # noqa: E402
from docx.shared import Inches, Pt, RGBColor  # noqa: E402
from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

try:
    from backend.scenario import PATHWAYS, _hhmm
except ImportError:  # running from inside backend/
    from scenario import PATHWAYS, _hhmm

RED = "#B42318"
INK = "#1F2328"


# --- Figures ----------------------------------------------------------------

def _layout(nodes: List[Dict], edges: List[Dict]) -> Dict[str, tuple]:
    """Columns by BFS depth from the first node; rows in visit order."""
    ids = [n["id"] for n in nodes]
    adj: Dict[str, List[str]] = {}
    for e in edges:
        adj.setdefault(e.get("from"), []).append(e.get("to"))
    depth = {ids[0]: 0} if ids else {}
    q = deque(ids[:1])
    while q:
        n = q.popleft()
        for m in adj.get(n, []):
            if m in ids and m not in depth:
                depth[m] = depth[n] + 1
                q.append(m)
    next_col = max(depth.values(), default=-1) + 1
    for i in ids:  # unreachable nodes go in a trailing column
        if i not in depth:
            depth[i] = next_col
    # Order each column by the mean row of its parents (barycenter) so the
    # main spine stays on top and branches sit under the node they leave from.
    preds: Dict[str, List[str]] = {}
    for e in edges:
        if e.get("from") in depth and e.get("to") in depth and depth[e["from"]] < depth[e["to"]]:
            preds.setdefault(e["to"], []).append(e["from"])
    pos: Dict[str, tuple] = {}
    order = {i: k for k, i in enumerate(ids)}
    for c in range(max(depth.values(), default=-1) + 1):
        col = [i for i in ids if depth[i] == c]
        def key(i):
            ps = [pos[p][1] for p in preds.get(i, []) if p in pos]
            return (sum(ps) / len(ps) if ps else 0, order[i])
        for r, i in enumerate(sorted(col, key=key)):
            pos[i] = (c, r)
    return pos


def render_tree_png(leg: Dict) -> BytesIO:
    nodes = (leg.get("tree") or {}).get("nodes") or []
    edges = (leg.get("tree") or {}).get("edges") or []
    buf = BytesIO()
    if not nodes:
        return buf
    pos = _layout(nodes, edges)
    ncols = max(c for c, _ in pos.values()) + 1
    nrows = max(r for _, r in pos.values()) + 1
    cw, rh, bw, bh = 2.3, 1.25, 1.95, 0.95
    fig_w, fig_h = max(4, ncols * cw), max(1.6, nrows * rh)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=110)
    ax.set_xlim(0, ncols * cw)
    ax.set_ylim(-nrows * rh, 0.2)
    ax.axis("off")
    by_id = {n["id"]: n for n in nodes}

    def center(i):
        c, r = pos[i]
        return c * cw + cw / 2, -r * rh - rh / 2

    for n in nodes:
        x, y = center(n["id"])
        fail = bool(n.get("failure"))
        colour = RED if fail else INK
        text = n.get("label", "")
        if n.get("detail") and n.get("type") == "outcome":
            text = f"{text}\n{n['detail']}"
        wrapped = "\n".join(textwrap.wrap(text, 26)[:6])
        if n.get("type") == "branch" and len(text) <= 2:
            ax.add_patch(Circle((x, y), 0.28, fill=False, ec=colour, lw=1.4))
            ax.text(x, y, text, ha="center", va="center", fontsize=8, color=colour)
            continue
        ax.add_patch(FancyBboxPatch((x - bw / 2, y - bh / 2), bw, bh, boxstyle="square,pad=0.02",
                                    fill=True, fc="white", ec=colour,
                                    lw=2.0 if n.get("type") == "outcome" else 1.1))
        ax.text(x, y, wrapped, ha="center", va="center",
                fontsize=8.5 if n.get("type") == "outcome" else 6.6, color=colour,
                fontweight="bold" if n.get("type") == "outcome" else "normal")

    for e in edges:
        a, b = e.get("from"), e.get("to")
        if a not in pos or b not in pos:
            continue
        (x1, y1), (x2, y2) = center(a), center(b)
        fail = bool(by_id.get(b, {}).get("failure")) or bool(by_id.get(a, {}).get("failure"))
        same_col = pos[b][0] == pos[a][0]
        back = pos[b][0] < pos[a][0] or (same_col and pos[b][1] < pos[a][1])
        if same_col and not back:  # straight down within a column
            start, end = (x1, y1 - bh / 2), (x2, y2 + bh / 2)
        elif back:  # loop back: arc under the boxes
            start, end = (x1, y1 - bh / 2), (x2, y2 - bh / 2)
        else:
            start, end = (x1 + bw / 2, y1), (x2 - bw / 2, y2)
        ax.annotate("", xy=end, xytext=start,
                    arrowprops=dict(arrowstyle="-|>", color=RED if fail else INK, lw=0.9,
                                    connectionstyle="arc3,rad=0.35" if back else "arc3,rad=0"))
        cond = (e.get("condition") or "").strip()
        if cond:
            mx, my = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
            ax.text(mx, my + 0.08, "\n".join(textwrap.wrap(cond, 18)[:2]), ha="center", va="bottom",
                    fontsize=5.6, color=RED if fail else "#57606A")
    fig.tight_layout(pad=0.1)
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf


# Body-map anchor points (x offset toward the patient's side, y). Front view:
# patient's right is the viewer's left; back view is mirrored.
_REGION_XY = {
    "head": (0.0, 7.35), "face": (0.0, 7.3), "neck": (0.0, 6.85), "chest": (0.42, 6.15),
    "shoulder": (0.7, 6.45), "axilla": (0.72, 6.0), "abdomen": (0.3, 5.15), "flank": (0.62, 5.25),
    "pelvis": (0.25, 4.45), "groin": (0.3, 4.3), "upper arm": (1.0, 5.95), "arm": (1.0, 5.95),
    "forearm": (1.05, 4.95), "hand": (1.1, 4.05), "thigh": (0.36, 3.45), "knee": (0.36, 2.55),
    "lower leg": (0.36, 1.65), "leg": (0.36, 1.65), "foot": (0.36, 0.55), "scapula": (0.45, 6.2),
    "upper back": (0.4, 6.1), "lower back": (0.3, 5.1), "back": (0.3, 5.6), "buttock": (0.36, 4.3),
}


def _region_xy(region: str) -> tuple:
    r = (region or "").lower()
    for key in sorted(_REGION_XY, key=len, reverse=True):
        if key in r:
            return _REGION_XY[key]
    return (0.0, 5.5)


def _silhouette(ax, cx: float):
    kw = dict(fill=False, ec=INK, lw=1.1)
    ax.add_patch(Circle((cx, 7.35), 0.38, **kw))
    ax.add_patch(Rectangle((cx - 0.13, 6.8), 0.26, 0.2, **kw))
    ax.add_patch(FancyBboxPatch((cx - 0.75, 4.2), 1.5, 2.6, boxstyle="round,pad=0.05", **kw))
    for s in (-1, 1):
        ax.add_patch(FancyBboxPatch((cx + s * 0.92 - 0.17, 3.95), 0.34, 2.75, boxstyle="round,pad=0.04", **kw))
        ax.add_patch(FancyBboxPatch((cx + s * 0.36 - 0.26, 0.35), 0.52, 3.85, boxstyle="round,pad=0.04", **kw))


def render_body_map_png(wounds: List[Dict], title: str = "") -> BytesIO:
    fig, ax = plt.subplots(figsize=(8.5, 5.2), dpi=110)
    ax.set_xlim(-0.2, 10.5)
    ax.set_ylim(0, 8.3)
    ax.axis("off")
    front_cx, back_cx = 1.9, 5.1
    _silhouette(ax, front_cx)
    _silhouette(ax, back_cx)
    ax.text(front_cx, 8.05, "FRONT", ha="center", fontsize=9, fontweight="bold")
    ax.text(back_cx, 8.05, "BACK", ha="center", fontsize=9, fontweight="bold")
    for cx, lft, rgt in ((front_cx, "RIGHT", "LEFT"), (back_cx, "LEFT", "RIGHT")):
        ax.text(cx - 1.25, 3.7, lft, fontsize=6.5, ha="center")
        ax.text(cx + 1.25, 3.7, rgt, fontsize=6.5, ha="center")
    legend_y = 7.7
    for i, w in enumerate(wounds or [], start=1):
        dx, y = _region_xy(w.get("region", ""))
        surface = (w.get("surface") or "anterior").lower()
        side = (w.get("side") or "").lower()
        back = surface.startswith("post")
        cx = back_cx if back else front_cx
        # patient's right → viewer's left on the front view, viewer's right on the back view
        sign_r = 1 if back else -1
        sides = {"r": [sign_r], "right": [sign_r], "l": [-sign_r], "left": [-sign_r],
                 "bilateral": [-1, 1], "bilat": [-1, 1]}.get(side, [0])
        amput = "amput" in (w.get("type") or "").lower()
        # An amputation is visible from both sides; mirror it onto the other view.
        views = [(cx, sides)]
        if amput:
            other = front_cx if back else back_cx
            views.append((other, [-s for s in sides]))
        for vcx, vsides in views:
            for s in vsides:
                x = vcx + s * dx
                if amput:
                    ax.plot([x - 0.3, x + 0.3], [y, y], color=RED, lw=3)
                else:
                    ax.plot(x, y, marker="*", color=RED, ms=10)
                ax.text(x + 0.12, y + 0.12, str(i), fontsize=7, color=RED, fontweight="bold")
        eff = w.get("effective")
        eff_txt = "" if eff is None else (" — effective" if eff else " — INEFFECTIVE")
        line = f"{i}. {(w.get('side') or '').upper()} {w.get('region', '')} ({surface}): {w.get('type', '')}. " \
               f"Tx: {w.get('intervention') or 'none'}{eff_txt}"
        wrapped = textwrap.wrap(line, 52)
        for j, ln in enumerate(wrapped[:3]):
            ax.text(6.7, legend_y - j * 0.28, ln, fontsize=6.8, color=INK)
        legend_y -= 0.28 * min(len(wrapped), 3) + 0.2
    if title:
        ax.text(5.25, 8.28, title, ha="center", fontsize=9.5)
    fig.tight_layout(pad=0.1)
    buf = BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf


# --- Docx packet ------------------------------------------------------------

def _bp(p: Dict) -> str:
    return f"{p.get('sbp', '')}/{p.get('dbp', '')}" if p.get("sbp") is not None else ""


def _kv_table(doc, rows: List[tuple]):
    t = doc.add_table(rows=len(rows), cols=2)
    t.style = "Table Grid"
    for i, (k, v) in enumerate(rows):
        t.rows[i].cells[0].text = k
        t.rows[i].cells[1].text = str(v if v is not None else "")
        t.rows[i].cells[0].paragraphs[0].runs[0].bold = True
    return t


def _chain_text(ctrl: Dict) -> str:
    return " → ".join(n["name"] for n in (ctrl.get("chain") or {}).get("nodes", []))


def create_controller_packet(cases: List[Dict], schedule: List[Dict], config, fragos: List[Dict]) -> BytesIO:
    doc = Document()
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = sec.page_height, sec.page_width
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, Inches(0.6))
    usable = sec.page_width - sec.left_margin - sec.right_margin

    doc.add_heading(f"{config.exercise_name.upper()} — CONTROLLER PACKET", 0)
    doc.add_paragraph(
        "Decision trees, turnover cards, body maps and critical actions for each casualty, built on the care "
        "chain in force (WARNO + FRAGOs) at the casualty's arrival time. Vitals tracks are in the Controller "
        "Vitals workbook (one sheet per case). Every case has been auto red-teamed and REQUIRES EXPERT REVIEW "
        "AND SIGN-OFF before use.")
    doc.add_paragraph(f"Generated {datetime.now().strftime('%d %b %Y %H%M')}")
    if fragos:
        doc.add_heading("FRAGOs affecting the care chain", level=2)
        for f in fragos:
            doc.add_paragraph(f"FRAGO {f['number']:02d} — D{f['day']} {_hhmm(f['start'])}-{_hhmm(f['end'])}: "
                              f"{f['title']}", style="List Bullet")
    doc.add_page_break()

    rows = [r for r in schedule if "arr_raw" in r]
    for i, case in enumerate(cases):
        ctrl = case.get("controller") or {}
        row = rows[i] if i < len(rows) else {}
        meta = case.get("meta") or {}
        doc.add_heading(f"CASE {i + 1}: {meta.get('title', 'Untitled')}", level=1)
        _kv_table(doc, [
            ("ZAP", (case.get("zmist") or {}).get("zap", "")),
            ("Arrival", f"D{row.get('day', '')} {row.get('time', '')} ({row.get('event', '')})"),
            ("Pathway", f"{ctrl.get('pathway', '')} — {PATHWAYS.get(ctrl.get('pathway', ''), '')}"),
            ("Care chain in force", _chain_text(ctrl)),
            ("FRAGOs in force", ", ".join(f"FRAGO {n:02d}" for n in (ctrl.get("chain") or {}).get("fragos", [])) or "None"),
            ("Triage / disposition", f"{case.get('triage_category', '')} / {case.get('disposition', '')}"),
            ("Vitals", f"Controller Vitals workbook, sheet C{i + 1}"),
        ])
        for note in (ctrl.get("chain") or {}).get("notes", []):
            doc.add_paragraph(note, style="List Bullet")

        rt = ctrl.get("red_team") or {}
        counts = rt.get("counts") or {}
        p = doc.add_paragraph()
        r = p.add_run(f"RED TEAM (auto): {counts.get('high', 0)} high, {counts.get('medium', 0)} medium, "
                      f"{counts.get('low', 0)} low open findings — expert review required.")
        r.bold = True
        if counts.get("high"):
            r.font.color.rgb = RGBColor(0xB4, 0x23, 0x18)
        if ctrl.get("_fallback"):
            doc.add_paragraph("AI generation failed for this case — the controller layer is a template.",
                              style="List Bullet")
        for f in [f for f in rt.get("open", []) if f["severity"] in ("high", "medium")][:12]:
            doc.add_paragraph(f"[{f['severity'].upper()}] {f['issue']} Fix: {f['fix']} ({f['location']})",
                              style="List Bullet")

        doc.add_heading("Injuries / moulage", level=2)
        if ctrl.get("wounds"):
            doc.add_picture(render_body_map_png(ctrl["wounds"], meta.get("title", "")), width=min(usable, Inches(8.5)))
        if ctrl.get("moulage"):
            doc.add_paragraph(ctrl["moulage"])
        if ctrl.get("critical_decisions"):
            doc.add_heading("Critical decisions", level=3)
            for d in ctrl["critical_decisions"]:
                doc.add_paragraph(d, style="List Bullet")

        for leg in ctrl.get("legs") or []:
            doc.add_heading(f"{leg.get('title', leg.get('leg_id'))}" + ("  [FOCUS — played at Role 2]" if leg.get("focus") else ""),
                            level=2)
            hv = leg.get("handover") or {}
            if hv:
                v = hv.get("vitals") or {}
                meds = "; ".join(f"{m.get('drug', '')} {m.get('dose', '')} {m.get('route', '')} @ "
                                 f"{m.get('minutes_prior', '?')} min prior" for m in hv.get("meds") or [])
                _kv_table(doc, [
                    ("Turnover V/S", f"HR {v.get('hr', '')}  BP {_bp(v)}  RR {v.get('rr', '')}  "
                                     f"SpO2 {v.get('spo2', '')}  AVPU {v.get('avpu', '')}"),
                    ("Summary", hv.get("summary", "")),
                    ("Interventions", "; ".join(hv.get("interventions") or [])),
                    ("Meds given", meds),
                ])
            png = render_tree_png(leg)
            if png.getbuffer().nbytes:
                doc.add_paragraph()
                doc.add_picture(png, width=usable)
            if leg.get("considerations"):
                p = doc.add_paragraph()
                rr = p.add_run("*Other important considerations: ")
                rr.bold = True
                rr.font.color.rgb = RGBColor(0xB4, 0x23, 0x18)
                p.add_run("; ".join(leg["considerations"]))

        if ctrl.get("critical_actions"):
            doc.add_heading("Critical actions (drive the green/red tracks)", level=2)
            t = doc.add_table(rows=1, cols=4)
            t.style = "Table Grid"
            for j, h in enumerate(("Action", "Window", "If missed", "Rejoin green")):
                t.rows[0].cells[j].text = h
            for a in ctrl["critical_actions"]:
                c = t.add_row().cells
                c[0].text = a.get("action", "")
                c[1].text = f"{a.get('window_min', '')} min"
                c[2].text = a.get("if_missed", "")
                c[3].text = a.get("rejoin", "")
        if ctrl.get("controller_note"):
            p = doc.add_paragraph()
            p.add_run(ctrl["controller_note"]).italic = True

        doc.add_heading("Expert review / sign-off", level=2)
        rv = ctrl.get("review") or {}
        if rv.get("status") in ("approved", "changes_requested"):
            _kv_table(doc, [("Reviewer", rv.get("reviewer") or ""),
                            ("Decision", "Approved" if rv["status"] == "approved" else "Changes required"),
                            ("Date", (rv.get("decided_at") or "")[:10]), ("Comments", rv.get("note") or "")])
        else:
            _kv_table(doc, [("Reviewer (name / specialty)", ""), ("Decision", "☐ Approved   ☐ Changes required"),
                            ("Date", ""), ("Comments", "\n\n")])
        doc.add_page_break()

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


# --- Controller vitals workbook -------------------------------------------

_YELLOW = PatternFill("solid", fgColor="FFE699")
_GREEN = PatternFill("solid", fgColor="C6E0B4")
_REDF = PatternFill("solid", fgColor="F4B6B0")
_HEAD = PatternFill("solid", fgColor="D9D9D9")
_THIN = Side(style="thin", color="808080")
_BOX = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

_CARE_ITEMS = [("Hemorrhage", True), ("Airway", True), ("Suction", False), ("Adjuncts", False),
               ("ETT/Cric", False), ("C-Spine", False), ("Breathing", True), ("O2", False), ("BVM", False),
               ("Vent", False), ("ND/Chest Tube", False), ("Circulation", True), ("I/O", False), ("PIV", False),
               ("Fluid Warmer", False), ("Resuscitation", False), ("Pelvic Binder", False), ("Disability", True),
               ("Exposure", True), ("Log Roll", False), ("Inspect Posterior", False), ("Hypothermia Tx", False),
               ("Full V/S", True), ("Labs", False), ("US", False), ("Imaging", False), ("Pain", False),
               ("Abx", False), ("HPI", False), ("Secondary Survey", True)]
_MEDS = ["Whole Blood", "PRBC", "FFP", "PLT", "Cryo", "Calcium", "Antibiotics", "Antifungal", "T-Dap", "TIG",
         "TXA", "TXA (2nd dose)", "Pain", "Sedation", "Antiseizure"]
_VENT = ["Mode", "FiO2", "VT", "Rate", "PEEP", "PS", "I:E"]
_ROWS = [("BP", _bp), ("HR", lambda p: p.get("hr")), ("RR", lambda p: p.get("rr")),
         ("SpO2", lambda p: p.get("spo2")), ("Temp", lambda p: p.get("temp_f")),
         ("ETCO2", lambda p: p.get("etco2")), ("AVPU", lambda p: p.get("avpu")),
         ("GCS", lambda p: f"E{p.get('gcs_e')},V{p.get('gcs_v')},M{p.get('gcs_m')}" if p.get("gcs_e") else ""),
         ("Pupils", lambda p: p.get("pupils"))]


def _sheet_name(i: int, title: str, used: set) -> str:
    base = re.sub(r"[\[\]:*?/\\]", "", f"C{i} {title}")[:31].strip()
    name, k = base, 2
    while name in used:
        name = f"{base[:28]}~{k}"
        k += 1
    used.add(name)
    return name


def _cell(ws, r, c, v, bold=False, fill=None, box=True, wrap=False, color=None):
    cell = ws.cell(row=r, column=c, value=v)
    if bold or color:
        cell.font = Font(bold=bold, color=color)
    if fill:
        cell.fill = fill
    if box:
        cell.border = _BOX
    cell.alignment = Alignment(wrap_text=wrap, vertical="top", horizontal="center" if not wrap else "left")
    return cell


def _vitals_table(ws, top: int, label: str, pts: List[Dict], first_fill, rest_fill) -> int:
    _cell(ws, top, 1, "Time", bold=True, fill=_HEAD)
    for j, p in enumerate(pts):
        _cell(ws, top, 2 + j, label if j == 0 else p.get("t"), bold=True, fill=_HEAD)
    for i, (name, fn) in enumerate(_ROWS, start=1):
        _cell(ws, top + i, 1, name, bold=True)
        for j, p in enumerate(pts):
            v = fn(p)
            _cell(ws, top + i, 2 + j, "" if v is None else v, fill=first_fill if j == 0 else rest_fill)
    return top + len(_ROWS) + 1


def create_controller_vitals(cases: List[Dict], schedule: List[Dict], config) -> BytesIO:
    wb = Workbook()
    idx = wb.active
    idx.title = "Index"
    for j, h in enumerate(("Case", "Title", "ZAP", "Arrival", "Pathway", "Care chain", "Red team (H/M/L)",
                           "Reviewer", "Decision", "Date"), start=1):
        _cell(idx, 1, j, h, bold=True, fill=_HEAD)
    findings_ws = wb.create_sheet("Red Team")
    for j, h in enumerate(("Case", "Severity", "Category", "Location", "Issue", "Fix", "Source",
                           "Reviewer disposition"), start=1):
        _cell(findings_ws, 1, j, h, bold=True, fill=_HEAD)
    frow = 2
    rows = [r for r in schedule if "arr_raw" in r]
    used = {"Index", "Red Team"}
    for i, case in enumerate(cases, start=1):
        ctrl = case.get("controller") or {}
        row = rows[i - 1] if i - 1 < len(rows) else {}
        title = (case.get("meta") or {}).get("title", "Untitled")
        counts = (ctrl.get("red_team") or {}).get("counts") or {}
        for j, v in enumerate((f"Case {i}", title, (case.get("zmist") or {}).get("zap", ""),
                               f"D{row.get('day', '')} {row.get('time', '')}", ctrl.get("pathway", ""),
                               _chain_text(ctrl),
                               f"{counts.get('high', 0)}/{counts.get('medium', 0)}/{counts.get('low', 0)}",
                               "", "", ""), start=1):
            _cell(idx, i + 1, j, v, wrap=j in (2, 6))
        for f in (ctrl.get("red_team") or {}).get("open", []):
            fill = _REDF if f["severity"] == "high" else _YELLOW if f["severity"] == "medium" else None
            for j, v in enumerate((f"Case {i}", f["severity"], f["category"], f["location"], f["issue"],
                                   f["fix"], f["source"], ""), start=1):
                _cell(findings_ws, frow, j, v, fill=fill if j == 2 else None, wrap=j in (4, 5, 6))
            frow += 1

        ws = wb.create_sheet(_sheet_name(i, title, used))
        ws.column_dimensions["A"].width = 12
        for c in range(2, 16):
            ws.column_dimensions[get_column_letter(c)].width = 10.5
        r = 1
        _cell(ws, r, 1, title, bold=True, box=False).font = Font(bold=True, size=14)
        r += 1
        z = case.get("zmist") or {}
        focus = next((l for l in ctrl.get("legs") or [] if l.get("focus")), {})
        first = (ctrl.get("legs") or [{}])[0]
        pd_ = case.get("patient_data") or {}
        for label, text in (("MOI", z.get("mechanism", "")),
                            ("POI", (first.get("handover") or {}).get("summary", "") or z.get("signs", "")),
                            ("Moulage", ctrl.get("moulage", "")),
                            ("Prior care", "; ".join((focus.get("handover") or {}).get("interventions") or [])
                             or z.get("treatment", "")),
                            ("Care chain", _chain_text(ctrl)),
                            ("Pathway", f"{ctrl.get('pathway', '')} — {PATHWAYS.get(ctrl.get('pathway', ''), '')}")):
            _cell(ws, r, 1, label, bold=True, box=False)
            c = _cell(ws, r, 2, text, box=False, wrap=True)
            ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=14)
            ws.row_dimensions[r].height = 15 * max(1, min(4, len(str(text)) // 120 + 1))
            r += 1
        _cell(ws, r, 1, "Critical Decisions", bold=True, box=False)
        r += 1
        for d in ctrl.get("critical_decisions") or []:
            _cell(ws, r, 1, d, box=False, wrap=False)
            r += 1
        r += 1
        _cell(ws, r, 1, pd_.get("demographics", ""), bold=True, box=False)
        _cell(ws, r, 5, f"ZAP: {z.get('zap', '')}", bold=True, box=False)
        _cell(ws, r, 8, pd_.get("allergies", ""), bold=True, box=False)
        r += 1
        tracks = ctrl.get("vitals_tracks") or {}
        table_top = r
        r = _vitals_table(ws, r, "Initial", tracks.get("green") or [], _YELLOW, _GREEN)
        note = ctrl.get("controller_note", "")
        c = _cell(ws, r, 1, note, bold=True, box=False, wrap=True)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=14)
        ws.row_dimensions[r].height = 30
        r += 2
        if tracks.get("red"):
            _cell(ws, r, 1, "Declining condition if critical intervention missed", bold=True, box=False, color="B42318")
            r += 1
            r = _vitals_table(ws, r, "Deterioration", tracks["red"], _YELLOW, _REDF)
        r += 1
        if ctrl.get("critical_actions"):
            for j, h in enumerate(("Critical action", "", "", "", "Window", "If missed", "", "", "", "Rejoin"), start=1):
                if h:
                    _cell(ws, r, j, h, bold=True, fill=_HEAD)
            r += 1
            for a in ctrl["critical_actions"]:
                _cell(ws, r, 1, a.get("action", ""), wrap=True)
                ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
                _cell(ws, r, 5, f"{a.get('window_min', '')} min")
                _cell(ws, r, 6, a.get("if_missed", ""), wrap=True)
                ws.merge_cells(start_row=r, start_column=6, end_row=r, end_column=9)
                _cell(ws, r, 10, a.get("rejoin", ""), wrap=True)
                ws.merge_cells(start_row=r, start_column=10, end_row=r, end_column=14)
                ws.row_dimensions[r].height = 30
                r += 1

        # Right-hand panel: patient care checklist, meds, vent settings (+ burns only when relevant)
        pc = 17
        for col, w in ((pc, 18), (pc + 1, 7), (pc + 2, 7), (pc + 4, 16), (pc + 5, 7), (pc + 6, 7), (pc + 7, 7)):
            ws.column_dimensions[get_column_letter(col)].width = w
        rr = table_top
        for j, h in enumerate(("Patient Care", "Done", "Time"), start=pc):
            _cell(ws, rr, j, h, bold=True, fill=_HEAD)
        for k, (item, header) in enumerate(_CARE_ITEMS, start=1):
            _cell(ws, rr + k, pc, item, bold=header)
            _cell(ws, rr + k, pc + 1, "")
            _cell(ws, rr + k, pc + 2, "")
        mc = pc + 4
        for j, h in enumerate(("Medication", "Dose", "Route", "Time"), start=mc):
            _cell(ws, rr, j, h, bold=True, fill=_HEAD)
        for k, m in enumerate(_MEDS, start=1):
            _cell(ws, rr + k, mc, m)
            for j in range(1, 4):
                _cell(ws, rr + k, mc + j, "")
        vr = rr + len(_MEDS) + 2
        _cell(ws, vr, mc, "Vent Settings", bold=True, fill=_HEAD)
        _cell(ws, vr, mc + 1, "", fill=_HEAD)
        for k, v in enumerate(_VENT, start=1):
            _cell(ws, vr + k, mc, v)
            _cell(ws, vr + k, mc + 1, "")
        if ctrl.get("burns"):
            br = vr + len(_VENT) + 2
            _cell(ws, br, mc, "Burns %TBSA", bold=True, fill=_HEAD)
            _cell(ws, br + 1, mc, str(ctrl["burns"]), wrap=True)
    for col, w in ((1, 8), (2, 34), (3, 8), (4, 10), (5, 16), (6, 50), (7, 14), (8, 20), (9, 14), (10, 10)):
        idx.column_dimensions[get_column_letter(col)].width = w
    for col, w in ((1, 8), (2, 9), (3, 14), (4, 26), (5, 60), (6, 50), (7, 8), (8, 24)):
        findings_ws.column_dimensions[get_column_letter(col)].width = w
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
