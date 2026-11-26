#!/usr/bin/env python3
"""Deterministic PDF text-block and table extraction for the paper-parse Skill.

Design goals (from past-competition lessons):
  - Do the deterministic geometry work in code, not in the weak model's head.
  - Keep every tool return small: emit compact JSON, cap block counts.
  - Never fabricate: missing tools / unreadable PDFs are reported as status, not guessed.
  - Every extracted cell carries page + bbox so it can be traced back to the source.

Usage:
  python pdfextract.py inspect --pdf PATH --output DIR [--max-chars N]
  python pdfextract.py table   --pdf PATH --output DIR --table t0001 [--max-chars N]

Backends tried in order: pdftotext -bbox-layout (poppler) -> PyMuPDF (fitz).
If none is available, writes a status=tool_missing result with a clear reason.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

CAP_DEFAULT = 24000  # hard cap on characters emitted per command (budget conservation)


def _cap(obj, max_chars):
    s = json.dumps(obj, ensure_ascii=False, indent=1)
    if len(s) <= max_chars:
        return s, False
    return s[:max_chars], True


def _page_blocks_pdftotext(pdf):
    """Return list of pages; each page is dict(w,h,words=[{text,x0,y0,x1,y1}])."""
    if not shutil.which("pdftotext"):
        return None, "pdftotext not found"
    xml_path = pdf + ".bbox.xml"
    try:
        subprocess.run(
            ["pdftotext", "-bbox-layout", pdf, xml_path],
            check=True, capture_output=True, timeout=180,
        )
    except Exception as exc:  # noqa: BLE001
        return None, f"pdftotext failed: {exc}"
    try:
        tree = ET.parse(xml_path)
    except Exception as exc:  # noqa: BLE001
        return None, f"bbox xml parse failed: {exc}"
    root = tree.getroot()
    pages = []
    for page in root.iter():
        if page.tag.split("}")[-1] != "page":
            continue
        w = float(page.attrib.get("width", 0))
        h = float(page.attrib.get("height", 0))
        words = []
        for el in page.iter():
            tag = el.tag.split("}")[-1]
            if tag != "word":
                continue
            txt = (el.text or "").strip()
            if not txt:
                continue
            words.append({
                "text": txt,
                "x0": float(el.attrib.get("xMin", 0)),
                "y0": float(el.attrib.get("yMin", 0)),
                "x1": float(el.attrib.get("xMax", 0)),
                "y1": float(el.attrib.get("yMax", 0)),
            })
        pages.append({"w": w, "h": h, "words": words})
    try:
        os.remove(xml_path)
    except OSError:
        pass
    return pages, None


def _page_blocks_fitz(pdf):
    try:
        import fitz  # type: ignore
    except ImportError:
        return None, "PyMuPDF (fitz) not installed"
    try:
        doc = fitz.open(pdf)
    except Exception as exc:  # noqa: BLE001
        return None, f"fitz open failed: {exc}"
    pages = []
    for pno, page in enumerate(doc):
        words = []
        for x0, y0, x1, y1, word, *_ in page.get_text("words"):
            words.append({
                "text": word, "x0": float(x0), "y0": float(y0),
                "x1": float(x1), "y1": float(y1),
            })
        pages.append({"w": float(page.rect.width), "h": float(page.rect.height), "words": words})
    return pages, None


def _group_lines(words, tol=2.0):
    """Group words into visual lines by vertical overlap."""
    lines = []
    for w in sorted(words, key=lambda d: d["y0"]):
        center = (w["y0"] + w["y1"]) / 2
        placed = False
        for line in lines:
            if abs(line["cy"] - center) <= max(tol, line["h"] * 0.6):
                line["words"].append(w)
                xs = [q["x0"] for q in line["words"]] + [line["x0"]]
                x1s = [q["x1"] for q in line["words"]] + [line["x1"]]
                ys = [q["y0"] for q in line["words"]] + [line["y0"]]
                y1s = [q["y1"] for q in line["words"]] + [line["y1"]]
                line["x0"], line["x1"] = min(xs), max(x1s)
                line["y0"], line["y1"] = min(ys), max(y1s)
                line["cy"] = (line["y0"] + line["y1"]) / 2
                line["h"] = line["y1"] - line["y0"]
                placed = True
                break
        if not placed:
            lines.append({
                "words": [w], "x0": w["x0"], "x1": w["x1"],
                "y0": w["y0"], "y1": w["y1"],
                "cy": center, "h": w["y1"] - w["y0"],
            })
    for line in lines:
        line["words"].sort(key=lambda d: d["x0"])
        line["text"] = " ".join(q["text"] for q in line["words"])
        del line["words"]
        del line["cy"]
        del line["h"]
    return lines


def _inject_pages(pdf, output):
    pages, err = _page_blocks_pdftotext(pdf)
    if pages is None:
        pages, err = _page_blocks_fitz(pdf)
    if pages is None:
        result = {
            "status": "tool_missing",
            "case_id": os.path.basename(pdf),
            "reason": err,
            "hint": "Install poppler-utils (pdftotext) or PyMuPDF in the runtime; no text was fabricated.",
        }
        _write_result(output, "inspect", result, CAP_DEFAULT)
        return result
    result = {
        "status": "ok",
        "case_id": os.path.basename(pdf),
        "backend": "pdftotext-bbox" if shutil.which("pdftotext") else "fitz",
        "n_pages": len(pages),
        "pages": [],
    }
    for i, page in enumerate(pages, 1):
        lines = _group_lines(page["words"])
        result["pages"].append({
            "page": i, "w": round(page["w"], 1), "h": round(page["h"], 1),
            "n_words": len(page["words"]), "lines": lines,
        })
    _write_result(output, "inspect", result, CAP_DEFAULT)
    return result


def _detect_tables(pages, table_hint=None):
    """Detect grid-like regions from line geometry: rows sharing x-columns."""
    tables = []
    for page in pages:
        lines = page.get("lines", [])
        if not lines:
            continue
        # columns candidates: x positions that recur across many lines
        starts = {}
        for ln in lines:
            key = round(ln["x0"] / 5) * 5
            starts[key] = starts.get(key, 0) + 1
        col_xs = sorted(k for k, n in starts.items() if n >= 3)
        if len(col_xs) < 2:
            continue
        # group consecutive lines that share >=2 column starts into a table block
        group = []
        groups = []
        for ln in lines:
            key = round(ln["x0"] / 5) * 5
            if key in col_xs:
                group.append(ln)
            else:
                if len(group) >= 2:
                    groups.append(group)
                group = []
        if len(group) >= 2:
            groups.append(group)
        for g in groups:
            tables.append({
                "table_id": f"t{len(tables)+1:04d}",
                "page": page["page"],
                "bbox": [
                    round(min(q["x0"] for q in g), 1),
                    round(min(q["y0"] for q in g), 1),
                    round(max(q["x1"] for q in g), 1),
                    round(max(q["y1"] for q in g), 1),
                ],
                "n_rows": len(g),
                "rows": [
                    {
                        "y": round(q["y0"], 1),
                        "cells": [
                            {"text": q["text"], "x0": round(q["x0"], 1), "x1": round(q["x1"], 1)}
                        ],
                    }
                    for q in g
                ],
            })
    return tables


def _write_result(output, kind, result, cap):
    os.makedirs(output, exist_ok=True)
    path = os.path.join(output, f"{kind}.json")
    text, truncated = _cap(result, cap)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"WROTE {path} ({len(text)} chars, truncated={truncated})")
    print(text[:4000])


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("inspect")
    p1.add_argument("--pdf", required=True)
    p1.add_argument("--output", required=True)
    p1.add_argument("--max-chars", type=int, default=CAP_DEFAULT)
    p2 = sub.add_parser("table")
    p2.add_argument("--pdf", required=True)
    p2.add_argument("--output", required=True)
    p2.add_argument("--table", default=None)
    p2.add_argument("--max-chars", type=int, default=CAP_DEFAULT)
    args = ap.parse_args()

    if not os.path.isfile(args.pdf):
        print(json.dumps({"status": "input_missing", "path": args.pdf}, ensure_ascii=False))
        sys.exit(2)

    if args.cmd == "inspect":
        result = _inject_pages(args.pdf, args.output)
        pages = result.get("pages", [])
        tables = _detect_tables(pages)
        out = {
            "status": result.get("status"),
            "case_id": result.get("case_id"),
            "backend": result.get("backend"),
            "n_pages": result.get("n_pages", 0),
            "n_tables_detected": len(tables),
            "tables": [{"table_id": t["table_id"], "page": t["page"],
                        "bbox": t["bbox"], "n_rows": t["n_rows"]} for t in tables],
            "reason": result.get("reason"),
        }
        _write_result(args.output, "inspect_summary", out, args.max_chars)
    else:
        pages, err = _page_blocks_pdftotext(args.pdf)
        if pages is None:
            pages, err = _page_blocks_fitz(args.pdf)
        if pages is None:
            _write_result(args.output, "table", {
                "status": "tool_missing", "reason": err,
                "hint": "Install poppler-utils or PyMuPDF; no table data was fabricated.",
            }, args.max_chars)
            return
        lines_by_page = []
        for i, page in enumerate(pages, 1):
            lines_by_page.append({"page": i, "lines": _group_lines(page["words"])})
        tables = _detect_tables(lines_by_page)
        if args.table:
            tables = [t for t in tables if t["table_id"] == args.table]
            if not tables:
                _write_result(args.output, "table", {
                    "status": "table_not_found", "table_id": args.table,
                    "available": [t["table_id"] for t in _detect_tables(lines_by_page)],
                }, args.max_chars)
                return
        _write_result(args.output, "table", {
            "status": "ok", "case_id": os.path.basename(args.pdf),
            "tables": tables,
        }, args.max_chars)


if __name__ == "__main__":
    main()
