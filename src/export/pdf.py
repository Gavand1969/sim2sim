"""
PDF report builders for Pro-tier export feature.
Uses ReportLab Platypus to produce branded PDF documents.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak
)

# ── Brand colours ──────────────────────────────────────────────────────────────
NAVY = colors.HexColor("#1F3864")
LIGHT_GREY = colors.HexColor("#F2F2F2")
WHITE = colors.white


# ── Style factory ──────────────────────────────────────────────────────────────

def _make_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "sim2sim_title",
            fontName="Helvetica-Bold",
            fontSize=18,
            textColor=NAVY,
            spaceAfter=4,
            alignment=TA_LEFT,
        ),
        "subtitle": ParagraphStyle(
            "sim2sim_subtitle",
            fontName="Helvetica",
            fontSize=9,
            textColor=colors.grey,
            spaceAfter=16,
            alignment=TA_LEFT,
        ),
        "section": ParagraphStyle(
            "sim2sim_section",
            fontName="Helvetica-Bold",
            fontSize=14,
            textColor=NAVY,
            spaceBefore=14,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "sim2sim_body",
            fontName="Helvetica",
            fontSize=10,
            textColor=colors.black,
            spaceAfter=6,
        ),
        "note": ParagraphStyle(
            "sim2sim_note",
            fontName="Helvetica-Oblique",
            fontSize=9,
            textColor=colors.grey,
            spaceAfter=4,
        ),
    }


_TABLE_STYLE = TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
    ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, 0), 10),
    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
    ("FONTSIZE", (0, 1), (-1, -1), 10),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
    ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
])


def _format_value(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


def _footer_canvas(canvas, doc):
    """Draw footer on every page: page number + site URL."""
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    footer_text = f"Page {doc.page}   |   sim2sim.app"
    canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, footer_text)
    canvas.restoreState()


def _build_doc(model_name: str, sections: list) -> bytes:
    """Render a document with header + given section flowables."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2.5 * cm, bottomMargin=2.5 * cm,
        title=f"Sim2Sim — {model_name}",
        author="sim2sim.app",
    )
    styles = _make_styles()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    story = [
        Paragraph(f"Sim2Sim — {model_name}", styles["title"]),
        Paragraph(f"Generated {timestamp}", styles["subtitle"]),
    ]
    story.extend(sections)

    doc.build(story, onFirstPage=_footer_canvas, onLaterPages=_footer_canvas)
    return buf.getvalue()


def _params_section(params: dict, styles: dict) -> list:
    """Build an Inputs section flowable list."""
    rows = [["Parameter", "Value"]]
    for k, v in params.items():
        if v is None:
            continue
        rows.append([str(k), _format_value(v)])
    table = Table(rows, colWidths=[8 * cm, 9 * cm])
    table.setStyle(_TABLE_STYLE)
    return [Paragraph("Inputs", styles["section"]), table, Spacer(1, 0.4 * cm)]


def _results_section(result: dict, styles: dict, skip_lists: bool = True) -> list:
    """Build a Results section flowable list."""
    rows = [["Metric", "Value"]]
    for k, v in result.items():
        if v is None:
            continue
        if skip_lists and isinstance(v, list):
            continue
        rows.append([str(k), _format_value(v)])
    table = Table(rows, colWidths=[8 * cm, 9 * cm])
    table.setStyle(_TABLE_STYLE)
    return [Paragraph("Results", styles["section"]), table, Spacer(1, 0.4 * cm)]


def _notes_section(result: dict, styles: dict) -> list:
    """Build a Notes section if notes present."""
    notes = result.get("notes")
    if not notes:
        return []
    return [
        Paragraph("Notes", styles["section"]),
        Paragraph(str(notes), styles["note"]),
        Spacer(1, 0.4 * cm),
    ]


# ── Public builders ────────────────────────────────────────────────────────────

def build_queuing_pdf(result: dict, params: dict) -> bytes:
    """Build a branded PDF for queuing analysis results."""
    model_name = f"Queuing Analysis ({result.get('model', 'Queue')})"
    styles = _make_styles()
    sections = (
        _params_section(params, styles)
        + _results_section(result, styles, skip_lists=True)
        + _notes_section(result, styles)
    )
    return _build_doc(model_name, sections)


def build_inventory_pdf(result: dict, params: dict, model_kind: str) -> bytes:
    """Build a branded PDF for inventory model results."""
    label_map = {
        "eoq": "EOQ — Economic Order Quantity",
        "eoq_backorder": "EOQ with Backorders",
        "epq": "EPQ — Economic Production Quantity",
        "newsvendor": "Newsvendor Model",
        "reorder_point": "Reorder Point Model",
        "base_stock": "Base Stock Model",
    }
    model_name = f"Inventory — {label_map.get(model_kind, model_kind.upper())}"
    styles = _make_styles()
    sections = (
        _params_section(params, styles)
        + _results_section(result, styles, skip_lists=True)
        + _notes_section(result, styles)
    )
    return _build_doc(model_name, sections)


def build_lp_pdf(result: dict, params: dict) -> bytes:
    """Build a branded PDF for LP optimization results."""
    model_name = "Linear Programming — Optimization"
    styles = _make_styles()

    # Solution summary table
    sol_rows = [["Item", "Value"]]
    sol_rows.append(["Status", result.get("status", "")])
    sol_rows.append(["Optimal Value", _format_value(result.get("optimal_value"))])
    sol_table = Table(sol_rows, colWidths=[8 * cm, 9 * cm])
    sol_table.setStyle(_TABLE_STYLE)

    # Variables table
    variables = result.get("variables", {})
    reduced_costs = result.get("reduced_costs", {})
    var_rows = [["Variable", "Value", "Reduced Cost"]]
    for name, value in variables.items():
        var_rows.append([name, _format_value(value), _format_value(reduced_costs.get(name))])
    var_table = Table(var_rows, colWidths=[5 * cm, 6 * cm, 6 * cm])
    var_table.setStyle(_TABLE_STYLE)

    # Constraints table
    shadow_prices = result.get("shadow_prices", {})
    slacks = result.get("slacks", {})
    binding_constraints = result.get("binding_constraints", [])
    con_rows = [["Constraint", "Shadow Price", "Slack", "Binding"]]
    for name in shadow_prices:
        con_rows.append([
            name,
            _format_value(shadow_prices.get(name)),
            _format_value(slacks.get(name)),
            "Y" if name in binding_constraints else "N",
        ])
    con_table = Table(con_rows, colWidths=[5 * cm, 4 * cm, 4 * cm, 4 * cm])
    con_table.setStyle(_TABLE_STYLE)

    sections = (
        _params_section(params, styles)
        + [
            Paragraph("Solution", styles["section"]),
            sol_table,
            Spacer(1, 0.4 * cm),
            Paragraph("Variables", styles["section"]),
            var_table,
            Spacer(1, 0.4 * cm),
            Paragraph("Constraints", styles["section"]),
            con_table,
            Spacer(1, 0.4 * cm),
        ]
        + _notes_section(result, styles)
    )
    return _build_doc(model_name, sections)
