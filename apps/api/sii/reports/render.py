"""Deterministic PDF/CSV rendering of a bounded immutable evidence snapshot.

No user HTML, remote resources, images or fonts are evaluated. CSV text is protected
against spreadsheet formula execution; JSON cells preserve complete raw provenance.
"""

import csv
import io
from datetime import datetime
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .snapshot import canonical


def rows(data):
    """One explicitly typed row per source/derived record; metadata includes scope/cutoff."""
    sections = {
        "readings",
        "coverage",
        "rules",
        "activations",
        "policies",
        "incident_history_through_cutoff",
    }
    yield "metadata", {key: value for key, value in data.items() if key not in sections}
    for section in sorted(sections):
        for item in data[section]:
            yield section, item


def render_csv(data):
    """RFC-style quoted UTF-8 CSV; JSON values cannot become executable spreadsheet formulas."""
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["record_type", "canonical_json"])
    for kind, value in rows(data):
        writer.writerow([kind, canonical(value).decode()])
    return stream.getvalue().encode("utf-8-sig")


def render_pdf(data):
    """Readable summary plus complete raw appendix, with repeat headers and stable metadata."""
    output = io.BytesIO()
    styles = getSampleStyleSheet()
    styles["BodyText"].fontSize = 8
    styles["BodyText"].leading = 11
    da = data["locale"] == "da"
    zone = ZoneInfo(data["configuration"]["timezone"])
    story = [
        Paragraph("SAMSEL - " + ("Evidensrapport" if da else "Evidence report"), styles["Title"])
    ]

    def paragraph(text, style="BodyText"):
        """Escape all caller text before ReportLab's restricted paragraph markup parser."""
        return Paragraph(escape(str(text)), styles[style])

    for text in [
        "SYNTHETIC / TEST - "
        + ("Ingen vurdering af fødevaresikkerhed." if da else "No food-safety verdict."),
        data["configuration"].get("organisation_name", "")
        + " / "
        + data["configuration"]["site_name"]
        + " / "
        + data["configuration"].get("zone_name", "All zones"),
        f"{datetime.fromisoformat(data['start_inclusive']).astimezone(zone).isoformat()} <= time < "
        f"{datetime.fromisoformat(data['end_exclusive']).astimezone(zone).isoformat()}",
        "Timezone: " + data["configuration"]["timezone"],
        "Receipt cutoff: " + data["receipt_cutoff"],
        data["provenance"],
    ]:
        story.append(paragraph(text))
    story.extend(
        [Spacer(1, 12), paragraph("Dækning og huller" if da else "Coverage and gaps", "Heading2")]
    )
    table = [["Sensor", "Expected slots", "Qualified slots", "Qualified %"]]
    for row in data["coverage"]:
        table.append(
            [
                paragraph(row["sensor"]),
                row["expected_slots_estimate"],
                row["qualified_slots"],
                "Unknown" if row["qualified_percent"] is None else str(row["qualified_percent"]),
            ]
        )
    grid = Table(table, colWidths=[225, 80, 80, 75], repeatRows=1, hAlign="LEFT")
    grid.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.extend([grid, paragraph("Complete raw evidence / Fuld rå evidens", "Heading2")])
    for kind, value in rows(data):
        block = [paragraph(kind, "Heading3")]
        # Split nested JSON into bounded paragraphs so one giant metadata cell cannot
        # exceed a page. The CSV carries the canonical machine-readable representation.
        text = canonical(value).decode()
        for offset in range(0, len(text), 700):
            block.append(paragraph(text[offset : offset + 700]))
        # Keep a short evidence record on one page; oversized metadata may still split safely.
        story.append(KeepTogether(block))

    def footer(canvas, document):
        """Print stable page numbering without adding wall-clock timestamps."""
        canvas.setFont("Helvetica", 8)
        canvas.drawString(42, 24, f"SAMSEL | SYNTHETIC | {document.page}")

    def stable_canvas(*args, **kwargs):
        """Deterministic retry bytes allow immutable object recovery after worker crashes."""
        kwargs["invariant"] = 1
        return Canvas(*args, **kwargs)

    SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=42,
        rightMargin=42,
        topMargin=36,
        bottomMargin=40,
        title="SAMSEL evidence report",
    ).build(story, onFirstPage=footer, onLaterPages=footer, canvasmaker=stable_canvas)
    return output.getvalue()
