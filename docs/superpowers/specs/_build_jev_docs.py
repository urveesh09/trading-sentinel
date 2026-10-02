"""Build a Word doc and a PDF from the Jev decision layer markdown spec.

The doc is the pitch artifact; the PDF is the printable copy.
Output:
  C:/Users/Urveesh/Desktop/trading-sentinel/docs/superpowers/specs/2026-09-27-jev-decision-layer-design.docx
  C:/Users/Urveesh/Desktop/trading-sentinel/docs/superpowers/specs/2026-09-27-jev-decision-layer-design.pdf
"""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.shared import Pt, Inches, RGBColor
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)

SPEC_PATH = Path(r"C:\Users\Urveesh\Desktop\trading-sentinel\docs\superpowers\specs\2026-09-27-jev-decision-layer-design.md")
OUT_DIR = SPEC_PATH.parent
DOCX_PATH = OUT_DIR / "2026-09-27-jev-decision-layer-design.docx"
PDF_PATH = OUT_DIR / "2026-09-27-jev-decision-layer-design.pdf"


# ---------- markdown parsing (deliberately simple: the spec format is fixed) ----------

def parse_markdown(text: str):
    """Yield ('h1'|'h2'|'h3'|'p'|'code'|'table'|'hr', payload).

    For tables, payload = {"rows": [[cell, ...], ...], "aligns": [int, ...]}.
    For code blocks, payload = str.
    """
    lines = text.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped == "---":
            yield ("hr", None)
            i += 1
            continue
        if stripped.startswith("```"):
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            yield ("code", "\n".join(buf))
            i += 1  # skip closing fence
            continue
        if stripped.startswith("|") and "|" in stripped[1:]:
            # table
            tbl = []
            while i < n and lines[i].lstrip().startswith("|"):
                tbl.append(lines[i])
                i += 1
            # split, drop separator row (the |---|... line)
            rows = []
            for raw in tbl:
                cells = [c.strip() for c in raw.strip().strip("|").split("|")]
                # detect the separator row (---|---|...) and skip
                if all(re.fullmatch(r":?-+:?", c) for c in cells):
                    continue
                rows.append(cells)
            if rows:
                yield ("table", rows)
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            text_ = m.group(2).strip()
            yield (f"h{level}", text_)
            i += 1
            continue
        if stripped.startswith("- "):
            # bullet list — collect contiguous
            items = []
            while i < n and lines[i].lstrip().startswith("- "):
                items.append(lines[i].lstrip()[2:].strip())
                i += 1
            yield ("bullet", items)
            continue
        # numbered list "1. foo"
        if re.match(r"^\d+\.\s+", stripped):
            items = []
            while i < n and re.match(r"^\d+\.\s+", lines[i].lstrip()):
                items.append(re.sub(r"^\d+\.\s+", "", lines[i].lstrip()))
                i += 1
            yield ("numbered", items)
            continue
        # paragraph — collect contiguous non-blank lines that aren't special
        para = []
        while i < n:
            cur = lines[i]
            cs = cur.strip()
            if not cs:
                break
            if cs == "---" or cs.startswith("#") or cs.startswith("```") or cs.startswith("|"):
                break
            if cs.startswith("- ") or re.match(r"^\d+\.\s+", cs):
                break
            para.append(cur)
            i += 1
        if para:
            yield ("p", " ".join(s.strip() for s in para))


# ---------- inline markdown -> runs ----------

def render_inline(s: str) -> str:
    """Convert `code`, **bold**, *italic*, and [text](url) to display-friendly form.

    For Word, we keep these as plain text and let styles handle weight.
    For PDF (reportlab), we use simple <b>/<i>/<font> tags in Paragraph HTML.
    """
    return s


def to_pdf_html(s: str) -> str:
    """Convert markdown inline marks to ReportLab Paragraph HTML markup."""
    s = re.sub(r"`([^`]+)`", r'<font name="Courier" color="#0b3d91">\1</font>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<font color="#0b3d91"><u>\1</u></font>', s)
    return s


# ---------- DOCX ----------

def build_docx(blocks, path: Path):
    doc = Document()
    # set base font
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)
    # set page margins
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.9)
        section.right_margin = Inches(0.9)

    title_seen = False
    for kind, payload in blocks:
        if kind == "h1":
            if not title_seen:
                t = doc.add_heading(payload, level=0)
                t.alignment = 1  # center
                title_seen = True
            else:
                doc.add_heading(payload, level=1)
        elif kind == "h2":
            doc.add_heading(payload, level=2)
        elif kind == "h3":
            doc.add_heading(payload, level=3)
        elif kind == "h4":
            doc.add_heading(payload, level=4)
        elif kind == "p":
            doc.add_paragraph(payload)
        elif kind == "bullet":
            for item in payload:
                doc.add_paragraph(item, style="List Bullet")
        elif kind == "numbered":
            for item in payload:
                doc.add_paragraph(item, style="List Number")
        elif kind == "code":
            p = doc.add_paragraph()
            run = p.add_run(payload)
            run.font.name = "Courier New"
            run.font.size = Pt(9)
            # light grey background
            pPr = p._p.get_or_add_pPr()
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), "F2F2F2")
            pPr.append(shd)
        elif kind == "table":
            tbl = doc.add_table(rows=len(payload), cols=len(payload[0]))
            tbl.style = "Light Grid Accent 1"
            tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
            for r, row in enumerate(payload):
                for c, cell in enumerate(row):
                    tbl.rows[r].cells[c].text = cell
                    if r == 0:
                        for run in tbl.rows[r].cells[c].paragraphs[0].runs:
                            run.bold = True
        elif kind == "hr":
            p = doc.add_paragraph()
            run = p.add_run("─" * 60)
            run.font.color.rgb = RGBColor(0xA0, 0xA0, 0xA0)
            run.font.size = Pt(8)
    doc.save(path)


# ---------- PDF ----------

def build_pdf(blocks, path: Path):
    doc = SimpleDocTemplate(
        str(path),
        pagesize=LETTER,
        leftMargin=0.9 * inch, rightMargin=0.9 * inch,
        topMargin=0.8 * inch, bottomMargin=0.8 * inch,
        title="Jev Decision Layer — Design Spec",
        author="Hermes + Uru collaborative",
    )
    # register Calibri-equivalent Type 1 font; Calibri isn't in reportlab's
    # built-in font set, so we map to Helvetica which ships with reportlab
    # and is visually close enough for a pitch document.
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFError
    FONT_BODY = "Helvetica"
    FONT_BOLD = "Helvetica-Bold"
    FONT_ITALIC = "Helvetica-Oblique"
    FONT_MONO = "Courier"
    FONT_MONO_BOLD = "Courier-Bold"
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "body", parent=styles["BodyText"],
        fontName=FONT_BODY, fontSize=10.5, leading=14,
        spaceAfter=6, spaceBefore=0,
    )
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName=FONT_BOLD, fontSize=20, leading=24, spaceAfter=10, spaceBefore=10, textColor=colors.HexColor("#1F3A5F"))
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName=FONT_BOLD, fontSize=15, leading=18, spaceAfter=8, spaceBefore=12, textColor=colors.HexColor("#1F3A5F"))
    h3 = ParagraphStyle("h3", parent=styles["Heading3"], fontName=FONT_BOLD, fontSize=12.5, leading=16, spaceAfter=6, spaceBefore=8, textColor=colors.HexColor("#1F3A5F"))
    h4 = ParagraphStyle("h4", parent=styles["Heading4"], fontName=FONT_BOLD, fontSize=11, leading=14, spaceAfter=4, spaceBefore=6, textColor=colors.HexColor("#1F3A5F"))
    code_style = ParagraphStyle("code", parent=body, fontName=FONT_MONO, fontSize=8.5, leading=11, leftIndent=6, rightIndent=6, backColor=colors.HexColor("#F2F2F2"), borderColor=colors.HexColor("#CCCCCC"), borderWidth=0.5, borderPadding=4, spaceBefore=4, spaceAfter=8)
    bullet_style = ParagraphStyle("bullet", parent=body, leftIndent=14, bulletIndent=4, spaceAfter=2)
    num_style = ParagraphStyle("num", parent=body, leftIndent=14, bulletIndent=4, spaceAfter=2)
    th_style = ParagraphStyle("th", parent=body, fontName=FONT_BOLD)
    title_style = ParagraphStyle("title", parent=h1, alignment=1, fontSize=22, textColor=colors.HexColor("#1F3A5F"), spaceAfter=14)

    story = []
    title_seen = False
    for kind, payload in blocks:
        if kind == "h1":
            if not title_seen:
                story.append(Paragraph(payload, title_style))
                title_seen = True
            else:
                story.append(Paragraph(payload, h1))
                story.append(Spacer(1, 2))
        elif kind == "h2":
            story.append(Paragraph(payload, h2))
        elif kind == "h3":
            story.append(Paragraph(payload, h3))
        elif kind == "h4":
            story.append(Paragraph(payload, h4))
        elif kind == "p":
            story.append(Paragraph(to_pdf_html(payload), body))
        elif kind == "bullet":
            for item in payload:
                story.append(Paragraph("• " + to_pdf_html(item), bullet_style))
        elif kind == "numbered":
            for idx, item in enumerate(payload, 1):
                story.append(Paragraph(f"{idx}. " + to_pdf_html(item), num_style))
        elif kind == "code":
            # preserve newlines; reportlab wraps inside Paragraph
            for chunk in payload.split("\n\n"):
                snippet = chunk.replace("\n", "<br/>")
                story.append(Paragraph(snippet, code_style))
        elif kind == "table":
            # convert cells to Paragraphs so HTML markup works
            tdata = []
            for r, row in enumerate(payload):
                trow = []
                for c in row:
                    txt = to_pdf_html(c).replace("|", "│")
                    p = Paragraph(txt, th_style if r == 0 else body)
                    trow.append(p)
                tdata.append(trow)
            col_widths = [6.7 * inch / len(tdata[0])] * len(tdata[0])
            tbl = Table(tdata, colWidths=col_widths, repeatRows=1)
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3A5F")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FC")]),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 6))
        elif kind == "hr":
            story.append(Spacer(1, 4))
            story.append(Paragraph("─" * 70, ParagraphStyle("hr", parent=body, alignment=1, textColor=colors.HexColor("#A0A0A0"), fontSize=8)))
            story.append(Spacer(1, 4))

    doc.build(story)


# ---------- main ----------

def main():
    text = SPEC_PATH.read_text(encoding="utf-8")
    blocks = list(parse_markdown(text))
    build_docx(blocks, DOCX_PATH)
    build_pdf(blocks, PDF_PATH)
    print(f"WROTE {DOCX_PATH}")
    print(f"WROTE {PDF_PATH}")


if __name__ == "__main__":
    main()
