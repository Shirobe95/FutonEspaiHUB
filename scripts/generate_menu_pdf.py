from __future__ import annotations

import re
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "MENU_LATERAL_ERP.md"
TARGET = ROOT / "docs" / "MENU_LATERAL_ERP.pdf"

PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN_X = 48
MARGIN_TOP = 56
MARGIN_BOTTOM = 48
LINE_HEIGHT = 13


def escape_pdf_text(text: str) -> bytes:
    text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return text.encode("latin-1", errors="replace")


def normalize(text: str) -> str:
    return (
        text.replace("–", "-")
        .replace("—", "-")
        .replace("“", '"')
        .replace("”", '"')
        .replace("’", "'")
    )


def font_for_line(line: str) -> tuple[int, str, int]:
    if line.startswith("# "):
        return 18, line[2:].strip(), 22
    if line.startswith("## "):
        return 15, line[3:].strip(), 19
    if line.startswith("### "):
        return 12, line[4:].strip(), 16
    if line.startswith("- "):
        return 10, "  " + line.strip(), LINE_HEIGHT
    return 10, line.strip(), LINE_HEIGHT


def wrap_line(text: str, size: int) -> list[str]:
    if not text:
        return [""]
    width = 92 if size <= 10 else 72 if size <= 12 else 58
    return textwrap.wrap(text, width=width, break_long_words=False) or [text]


def build_pages(markdown: str) -> list[list[tuple[int, int, str]]]:
    pages: list[list[tuple[int, int, str]]] = [[]]
    y = PAGE_HEIGHT - MARGIN_TOP
    in_code = False

    for raw in markdown.splitlines():
        line = normalize(raw.rstrip())
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            size, text, step = 9, line, 12
        elif not line:
            y -= 7
            continue
        else:
            size, text, step = font_for_line(line)

        if line.startswith("## "):
            y -= 6

        wrapped = wrap_line(text, size)
        for index, part in enumerate(wrapped):
            if y < MARGIN_BOTTOM:
                pages.append([])
                y = PAGE_HEIGHT - MARGIN_TOP
            x = MARGIN_X + (14 if index and line.startswith("- ") else 0)
            pages[-1].append((size, x, y, part))
            y -= step if index == 0 else LINE_HEIGHT

        if line.startswith("# "):
            y -= 6
        elif line.startswith("## "):
            y -= 4

    return pages


def page_stream(lines: list[tuple[int, int, int, str]], page_number: int, total_pages: int) -> bytes:
    commands: list[bytes] = []
    for size, x, y, text in lines:
        commands.append(b"BT")
        commands.append(f"/F1 {size} Tf".encode("ascii"))
        commands.append(f"{x} {y} Td".encode("ascii"))
        commands.append(b"(" + escape_pdf_text(text) + b") Tj")
        commands.append(b"ET")

    footer = f"FutonHUB UI-ERP - Menu lateral - pagina {page_number}/{total_pages}"
    commands.append(b"BT")
    commands.append(b"/F1 8 Tf")
    commands.append(f"{MARGIN_X} 28 Td".encode("ascii"))
    commands.append(b"(" + escape_pdf_text(footer) + b") Tj")
    commands.append(b"ET")
    return b"\n".join(commands)


def write_pdf(pages: list[list[tuple[int, int, int, str]]]) -> None:
    objects: list[bytes] = []
    total = len(pages)
    font_obj_id = 3 + total * 2

    page_ids = []
    content_ids = []
    for i in range(total):
        page_ids.append(3 + i * 2)
        content_ids.append(4 + i * 2)

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = b" ".join(f"{page_id} 0 R".encode("ascii") for page_id in page_ids)
    objects.append(b"<< /Type /Pages /Kids [" + kids + f"] /Count {total} >>".encode("ascii"))

    for i, lines in enumerate(pages):
        page_obj = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 {font_obj_id} 0 R >> >> "
            f"/Contents {content_ids[i]} 0 R >>"
        )
        stream = page_stream(lines, i + 1, total)
        content_obj = b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"
        objects.append(page_obj.encode("ascii"))
        objects.append(content_obj)

    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    output = bytearray()
    output.extend(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for obj_id, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{obj_id} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")

    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    )

    TARGET.write_bytes(output)


def main() -> None:
    markdown = SOURCE.read_text(encoding="utf-8")
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    pages = build_pages(markdown)
    write_pdf(pages)
    print(TARGET)


if __name__ == "__main__":
    main()
