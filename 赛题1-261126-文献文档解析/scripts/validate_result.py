#!/usr/bin/env python3
"""Strict validator for the paper-parse Skill's result.json (v2).

Checks structural integrity, evidence binding, and honesty constraints:
  - stable block_id references (no bare array indices)
  - inferred fields are declared
  - 'not reported' is an answer, not an uncertain item
  - specific block types
Exit code 0 = pass, 1 = fail. Prints a compact report (budget friendly).
"""
import argparse
import json
import os
import sys

VALID_TYPES = {
    "paragraph", "figure_caption", "table_caption", "formula",
    "footnote", "reference", "section_title", "heading",
    "table_header_level1", "table_header_level2", "table_body",
}


def check(result, manifest=None):
    errors = []
    warnings = []
    stats = {}

    if not isinstance(result, dict):
        return ["result.json is not a JSON object"], [], {}

    for key in ("case_id", "status", "blocks"):
        if key not in result:
            errors.append(f"missing required field: {key}")
    status = result.get("status")
    if status not in ("ok", "partial", "unreadable", "tool_missing"):
        errors.append(f"invalid status: {status!r}")

    blocks = result.get("blocks", [])
    if not isinstance(blocks, list):
        errors.append("blocks is not a list")
        blocks = []
    stats["n_blocks"] = len(blocks)

    # collect stable ids
    ids = set()
    id_to_block = {}
    for i, b in enumerate(blocks):
        if not isinstance(b, dict):
            errors.append(f"block[{i}] not an object")
            continue
        bid = b.get("block_id")
        if not bid:
            errors.append(f"block[{i}] missing block_id (v2 requires stable ids)")
        else:
            if bid in ids:
                errors.append(f"duplicate block_id: {bid}")
            ids.add(bid)
            id_to_block[bid] = b
        if not str(b.get("text", "")).strip():
            errors.append(f"block[{i}] empty text")
        btype = b.get("type")
        if btype not in VALID_TYPES:
            errors.append(f"block[{i}] invalid/Too-generic type: {btype!r}; use one of {sorted(VALID_TYPES)}")
        ev = b.get("evidence")
        if not isinstance(ev, dict):
            errors.append(f"block[{i}] missing evidence object")
            continue
        if "page" not in ev or not isinstance(ev["page"], int) or ev["page"] < 1:
            errors.append(f"block[{i}] evidence.page invalid")
        bbox = ev.get("bbox")
        if not (isinstance(bbox, list) and len(bbox) == 4):
            errors.append(f"block[{i}] evidence.bbox malformed")

    # answers reference blocks by stable id, not index
    answer = result.get("answer", {})
    if isinstance(answer, dict):
        for q, payload in answer.items():
            ev = payload.get("evidence", {}) if isinstance(payload, dict) else {}
            if "block_index" in ev:
                errors.append(f"answer[{q}].evidence uses block_index (array order fragile); use block_id")
            bid = ev.get("block_id")
            if bid and bid not in ids:
                errors.append(f"answer[{q}].evidence.block_id {bid!r} not found in blocks")
            col = ev.get("column")
            if col not in ("left", "right", "full"):
                errors.append(f"answer[{q}].evidence.column missing/invalid: {col!r}; use left/right/full")
            # answer.value must be self-contained: if it is just a number, likely incomplete
            val = payload.get("value") if isinstance(payload, dict) else None
            if isinstance(val, str) and val != "not reported" and len(val) < 8:
                warnings.append(f"answer[{q}].value is very short ({len(val)} chars); check completeness (value+unit+CI+method)")
            if isinstance(payload, dict) and payload.get("value") == "not reported":
                pass  # correct: not reported lives in answer

    # uncertain semantics: 'not reported' must not be listed as uncertain
    uncertain = result.get("uncertain", [])
    if not isinstance(uncertain, list):
        errors.append("uncertain is not a list")
    else:
        for i, u in enumerate(uncertain):
            if isinstance(u, dict):
                blob = json.dumps(u, ensure_ascii=False)
                if "not reported" in blob.lower():
                    errors.append(f"uncertain[{i}] contains 'not reported' — that is a certain conclusion, not uncertainty")
    if not uncertain:
        warnings.append("no uncertain items; if text layer lost digits/conflicts, declare them")

    # inferred structural fields must be declared
    def scan_inferred(obj, path=""):
        if isinstance(obj, dict):
            if obj.get("inferred") is True:
                stats.setdefault("inferred_fields", []).append(path)
            for k, v in obj.items():
                scan_inferred(v, f"{path}.{k}" if path else k)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                scan_inferred(v, f"{path}[{i}]")
    scan_inferred(result)
    if stats.get("inferred_fields") and not uncertain:
        errors.append("inferred fields present but uncertain list empty — declare the inferences")

    # tables: spans must be explicitly inferred or source-provided
    for ti, t in enumerate(result.get("tables", []) or []):
        if not isinstance(t, dict):
            continue
        if "spans" in t and t["spans"]:
            has_flag = any(
                (s.get("inferred") is True) if isinstance(s, dict) else False
                for s in t["spans"]
            )
            if not has_flag and not uncertain:
                errors.append(f"tables[{ti}].spans present without inferred flag or uncertain entry")

    if "sources" not in result:
        warnings.append("no 'sources' list: declare which files were actually read")

    # external denominator
    if manifest and isinstance(manifest, dict):
        expected = manifest.get("expected_blocks")
        if isinstance(expected, int) and expected > 0:
            stats["expected_blocks"] = expected
            stats["coverage"] = round(len(blocks) / expected, 4)
            if len(blocks) < expected:
                errors.append(f"coverage shortfall: {len(blocks)}/{expected}")

    # duplicate long text
    seen = {}
    for i, b in enumerate(blocks):
        t = str(b.get("text", "")).strip()
        if len(t) >= 40:
            if t in seen:
                errors.append(f"block[{i}] duplicates block[{seen[t]}] verbatim")
            else:
                seen[t] = i
    return errors, warnings, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--manifest", default=None)
    args = ap.parse_args()
    with open(args.result, encoding="utf-8") as fh:
        result = json.load(fh)
    manifest = None
    if args.manifest and os.path.isfile(args.manifest):
        with open(args.manifest, encoding="utf-8") as fh:
            manifest = json.load(fh)
    errors, warnings, stats = check(result, manifest)
    print(json.dumps({
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "warnings": warnings,
        "stats": stats,
    }, ensure_ascii=False, indent=1))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
