#!/usr/bin/env python3
"""Deterministic audit for the literature-translation Skill (Q2).

Design goals (from past-competition translation failures):
  - Coverage denominator comes from the EXTERNAL declared range in case.json,
    NOT from what the extractor/agent happened to find (self-reported 100% trap).
  - Check term consistency from a real glossary (locked terms, no drift).
  - Check assertion polarity: negation/limitation must be preserved, not just keywords.
  - Check numbers/units/formula markers/citation markers survive translation.
Exit code 0 = pass, 1 = fail. Prints compact JSON (budget friendly).
"""
import argparse
import json
import re
import sys

# Terms that must keep a fixed translation once the glossary locks them.
DEFAULT_TERM_RE = re.compile(r"[A-Za-z][A-Za-z\- ]{2,40}")


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def find_ids(text, pattern):
    """Find all segment ids matching a pattern like S1 Fig, S1 Text, Table S1."""
    return set(re.findall(pattern, text or "", flags=re.I))


def audit(result, case, glossary):
    errors, warnings, stats = [], [], {}

    if not isinstance(result, dict):
        return ["result.json not an object"], [], {}

    # ---- 1. Coverage: denominator from case.json declared range (external) ----
    declared = case.get("segment_ids") or case.get("declared_segments") or []
    if not declared:
        warnings.append("case.json has no segment_ids/declared_segments; cannot compute external coverage")
    else:
        declared_set = {str(x) for x in declared}
        segments = result.get("segments", [])
        translated = set()
        for seg in segments:
            if isinstance(seg, dict):
                sid = seg.get("segment_id")
                if sid and str(seg.get("status", "ok")) in ("ok", "translated", "partial"):
                    translated.add(str(sid))
        missing = sorted(declared_set - translated)
        extra = sorted(translated - declared_set)
        stats["declared_segments"] = len(declared_set)
        stats["translated_segments"] = len(translated)
        stats["coverage"] = round(len(translated & declared_set) / len(declared_set), 4)
        if missing:
            errors.append(f"missing segments from DECLARED range: {missing[:20]} (total {len(missing)})")
        if extra:
            warnings.append(f"translated ids not in declared range: {extra[:10]}")

    # ---- 2. Every segment has source + translation + evidence ----
    for i, seg in enumerate(result.get("segments", []) or []):
        if not isinstance(seg, dict):
            errors.append(f"segments[{i}] not object")
            continue
        if not str(seg.get("source", "")).strip():
            errors.append(f"segments[{i}] empty source")
        if not str(seg.get("translation", "")).strip():
            if seg.get("status") not in ("untranslated", "unreadable"):
                errors.append(f"segments[{i}] empty translation without status=untranslated/unreadable")
        ev = seg.get("evidence")
        if not isinstance(ev, dict) or not ev.get("locator"):
            warnings.append(f"segments[{i}] missing evidence.locator (cannot trace back to source)")

    # ---- 3. Term glossary consistency (script-enforced, not prompt-only) ----
    glossary = glossary or {}
    if isinstance(glossary, dict) and glossary.get("locked") is not True:
        warnings.append("glossary.locked is not true — term lock is implicit, not machine-readable")
    terms = glossary.get("terms", {}) if isinstance(glossary, dict) else {}
    for en, zh in terms.items():
        # every segment whose source contains 'en' must use 'zh' in translation
        for i, seg in enumerate(result.get("segments", []) or []):
            src = str(seg.get("source", ""))
            trans = str(seg.get("translation", ""))
            if re.search(r"\b" + re.escape(en) + r"\b", src, flags=re.I):
                if zh not in trans and seg.get("status") not in ("untranslated", "unreadable"):
                    errors.append(f"segments[{i}] term '{en}' present in source but locked translation '{zh}' missing")

    # ---- 4. Assertion polarity: compare ASSERTIONS, not keywords ----
    # Lesson from the real failure: "不增加 A，但减少 B" -> "增加 A，但不减少 B"
    # kept every keyword (不, 但) but flipped polarity. Keyword presence is NOT a check.
    neg_words = ["not", "no", "never", "none", "neither", "nor", "but", "however", "unless", "without"]
    zh_neg = ["不", "无", "未", "非", "没有", "但", "然而", "除非", "并不"]
    def polarity(text):
        """Crude polarity signature: which negators attach to which content word.
        Returns list of (negator, following_content_word) pairs in order."""
        t = str(text).lower()
        out = []
        for m in re.finditer(r"\b(not|no|never|none|neither|nor|but|however|unless|without)\s+(\w+)", t):
            out.append((m.group(1), m.group(2)))
        # Chinese: capture negator + up to 4 following chars (content)
        for m in re.finditer(r"(不|无|未|非|没有|但|然而|除非)([\u4e00-\u9fff]{1,4})", str(text)):
            out.append((m.group(1), m.group(2)))
        return out
    for i, seg in enumerate(result.get("segments", []) or []):
        if seg.get("status") in ("untranslated", "unreadable"):
            continue
        src = str(seg.get("source", ""))
        trans = str(seg.get("translation", ""))
        src_has_neg = any(re.search(r"\b" + w + r"\b", src.lower()) for w in neg_words)
        # If the segment has an explicit assertion pair, compare polarities directly.
        ap = seg.get("assertion_pair")
        if isinstance(ap, dict):
            src_pol = str(ap.get("source_polarity", "")).lower()
            tgt_pol = str(ap.get("translation_polarity", "")).lower()
            if src_pol in ("negative", "negated", "false") and tgt_pol in ("positive", "affirmative", "true"):
                errors.append(f"segments[{i}] assertion polarity FLIPPED (source negative -> translation positive)")
            if src_pol in ("positive", "affirmative", "true") and tgt_pol in ("negative", "negated", "false"):
                errors.append(f"segments[{i}] assertion polarity FLIPPED (source positive -> translation negative)")
            continue
        # No explicit pair: fall back to sign-count heuristic (negator count must match).
        if src_has_neg:
            src_signs = sum(1 for _ in re.finditer(r"\b(not|no|never|none|neither|nor|but|however|unless|without)\b", src.lower()))
            tgt_signs = sum(1 for k in zh_neg if k in trans)
            if tgt_signs == 0:
                warnings.append(f"segments[{i}] source has {src_signs} negation/limitation marker(s) but translation has none — verify assertion polarity")
            elif tgt_signs < src_signs:
                warnings.append(f"segments[{i}] fewer negation markers in translation ({tgt_signs}) than source ({src_signs}) — verify assertion scope")

    # ---- 5. Numbers / units / formula / citation markers preserved ----
    # FIX (v2): do NOT treat "number + ordinary English word" as a literal token —
    # "3 shows" / "sites" would force agents to mangle translations into mixed English.
    # Only real quantities (with separators/units) and fixed citation markers must survive.
    UNITS = r"(?:eV|keV|MeV|GeV|nm|µm|μm|mm|cm|kg|g|s|ms|K|°C|%|Å|mol|Hz|Pa|T)"
    def tokens(s):
        # real quantities: digit groups with ,/. decimals, optionally a known unit
        nums = set(re.findall(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|" + r"\d+\s*" + UNITS + r"\b", s or ""))
        # fixed markers that must stay verbatim
        cites = set(re.findall(r"\[\d+\]|\(\d{4}\)|Fig\.?\s*\d+|Table\s*\d+|Eq\.?\s*\(?\d+\)?|eq\.?\s*\(?\d+", s or "", flags=re.I))
        return nums, cites
    for i, seg in enumerate(result.get("segments", []) or []):
        sn, sc = tokens(seg.get("source", ""))
        tn, tc = tokens(seg.get("translation", ""))
        lost_nums = sorted(n for n in sn if n not in str(tn))
        lost_cites = sorted(c for c in sc if c not in str(tc))
        if lost_nums:
            errors.append(f"segments[{i}] numbers/units lost in translation: {lost_nums[:8]}")
        if lost_cites:
            errors.append(f"segments[{i}] formula/citation markers lost: {lost_cites[:8]}")
        # table header/row: keep pipe structure and literal identifiers like MC, eV
        src = str(seg.get("source", ""))
        trans = str(seg.get("translation", ""))
        if "|" in src:
            pipes_src = src.count("|")
            pipes_tgt = trans.count("|")
            if pipes_tgt < pipes_src:
                errors.append(f"segments[{i}] table row lost pipe separators ({pipes_tgt} vs {pipes_src})")
            for lit in re.findall(r"\b[A-Z]{2,}\b", src):
                if lit in ("MC", "eV", "SI") and lit not in trans:
                    errors.append(f"segments[{i}] table literal '{lit}' not preserved verbatim")

    # ---- 6. Honesty: uncertain and source declared ----
    if "uncertain" not in result:
        warnings.append("no uncertain list: declare untranslatable/conflicting items")
    if "sources" not in result:
        warnings.append("no sources list: declare input case/material versions actually read")
    if "result.json" not in json.dumps(result, ensure_ascii=False) and "status" not in result:
        errors.append("no status field")

    return errors, warnings, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--case", required=True, help="case.json with declared segment_ids / glossary")
    ap.add_argument("--glossary", default=None, help="optional separate glossary json")
    args = ap.parse_args()
    result = load_json(args.result)
    case = load_json(args.case)
    glossary = load_json(args.glossary) if args.glossary else case.get("glossary", {})
    errors, warnings, stats = audit(result, case, glossary)
    print(json.dumps({
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "warnings": warnings,
        "stats": stats,
    }, ensure_ascii=False, indent=1))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
