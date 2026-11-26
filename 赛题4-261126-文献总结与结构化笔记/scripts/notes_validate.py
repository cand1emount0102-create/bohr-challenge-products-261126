#!/usr/bin/env python3
"""Strict validator for the section-aligned paper-notes Skill (Q4 v3).

Carries all v2 guards (anchor whitelist, verbatim quote, atomic split,
not-reported, cited marker, section/case_id single source) and adds:
  - knowledge-point anchors must also be in the case whitelist
  - sources must be a structured object with material_files
  - change_records must be a non-empty list documenting real changes
  - robust to None / wrong types / missing fields (never silently skips)
Exit 0 = pass, 1 = fail. Compact JSON output.
"""
import argparse
import json
import sys

DEFAULT_FIELDS = ("research_question", "data", "method_conditions", "main_findings", "limitations")


def g(d, k, default=None):
    return d.get(k, default) if isinstance(d, dict) else default


def is_page_like(loc):
    low = str(loc).strip().lower()
    return (low.startswith("page ") or low.startswith("p.") or low.startswith("p ")
            or (low.isdigit() and len(low) <= 4))


def check_anchor(anchor, field, label, errors, anchor_set, sections):
    if not isinstance(anchor, dict):
        errors.append("%s missing anchor object" % label)
        return
    if not isinstance(g(anchor, "section"), str) or not g(anchor, "section"):
        errors.append("%s anchor.section missing" % label)
    elif sections and g(anchor, "section") not in sections:
        errors.append("%s anchor.section not an original section title" % label)
    loc = g(anchor, "locator")
    if not isinstance(loc, str) or not loc.strip():
        errors.append("%s anchor.locator missing" % label)
    elif anchor_set and loc not in anchor_set:
        errors.append("%s locator %r not in case anchor whitelist" % (label, loc))
    if is_page_like(loc):
        errors.append("%s locator %r looks like an invented PDF page" % (label, loc))


def audit(result, case):
    errors, warnings, stats = [], [], {}
    if not isinstance(result, dict):
        return ["result.json is not an object"], [], {}

    required = g(case, "required_fields", list(DEFAULT_FIELDS))
    if not isinstance(required, list):
        return ["case.required_fields is not a list"], [], {}
    anchors = g(case, "anchors", [])
    anchors = anchors if isinstance(anchors, list) else []
    anchor_set = set(str(a) for a in anchors)
    sections = g(case, "sections", [])
    sections = sections if isinstance(sections, list) else []
    material = str(g(case, "material_text", "") or "")
    case_id = g(case, "case_id")

    if case_id is not None and g(result, "case_id") != case_id:
        errors.append("case_id must come from case.json")
    status = g(result, "status")
    if not isinstance(status, str) or not status.strip():
        errors.append("no status field")

    order = g(result, "section_order")
    if sections:
        if not isinstance(order, list):
            errors.append("section_order is not a list")
        elif [str(x) for x in order] != [str(x) for x in sections]:
            errors.append("section_order does not match case.sections (no IMRaD / rename / reorder)")

    card = g(result, "paper_card")
    if not isinstance(card, dict):
        return errors + ["paper_card is not an object"], warnings, stats

    all_notes = []
    for field in required:
        if field not in card:
            errors.append("missing required field: %s" % field)
            continue
        notes = g(card, field, [])
        notes = notes if isinstance(notes, list) else []
        stats["notes_" + field] = len(notes)
        for i, note in enumerate(notes):
            label = "paper_card.%s[%d]" % (field, i)
            if not isinstance(note, dict):
                errors.append("%s not object" % label)
                continue
            all_notes.append((field, note))
            text = g(note, "text")
            if not isinstance(text, str) or not text.strip():
                errors.append("%s missing text" % label)
            check_anchor(g(note, "anchor"), field, label, errors, anchor_set, sections)
            quote = g(note, "quote")
            if not isinstance(quote, str) or not quote.strip():
                errors.append("%s missing quote" % label)
            elif material and quote.strip() not in material:
                errors.append("%s quote is not verbatim in material" % label)
            if g(note, "claim_type") not in ("author", "cited"):
                errors.append("%s claim_type must be author|cited" % label)
    stats["notes_total"] = len(all_notes)

    conds = g(case, "required_conditions", [])
    if isinstance(conds, list):
        blob = " ".join(str(g(n, "text", "")) + " " + str(g(n, "quote", "")) for _, n in all_notes)
        for c in conds:
            if str(c) not in blob:
                errors.append("required method condition %r lost from notes" % c)

    nr = g(case, "required_not_reported")
    if isinstance(nr, dict):
        kw, st = str(g(nr, "keyword", "")), str(g(nr, "status", "not reported"))
        lim_notes = g(card, "limitations", [])
        lim_notes = lim_notes if isinstance(lim_notes, list) else []
        lim_blob = " ".join(str(g(n, "text", "")) + " " + str(g(n, "quote", "")) for n in lim_notes if isinstance(n, dict))
        if kw and (kw.lower() not in lim_blob.lower() or st.lower() not in lim_blob.lower()):
            errors.append("limitations missing not-reported item for %r" % kw)

    marker = g(case, "cited_marker")
    if isinstance(marker, str) and marker:
        for field, n in all_notes:
            if marker in str(g(n, "quote", "")) and g(n, "claim_type") != "cited":
                errors.append("note in %s quotes %r but is not claim_type=cited" % (field, marker))

    cf = g(case, "compound_facts", [])
    if isinstance(cf, list) and cf:
        for field, n in all_notes:
            if sum(1 for f in cf if str(f) in str(g(n, "text", ""))) >= 2:
                errors.append("compound facts bundled in one note in %s; split" % field)

    # knowledge points: required terms + valid anchors + aliases encouraged
    kps = g(result, "knowledge_points", [])
    kps = kps if isinstance(kps, list) else []
    stats["knowledge_points"] = len(kps)
    kp_terms = set()
    for i, k in enumerate(kps):
        if not isinstance(k, dict):
            errors.append("knowledge_points[%d] not object" % i)
            continue
        term = g(k, "term")
        if not isinstance(term, str) or not term.strip():
            errors.append("knowledge_points[%d] missing term" % i)
        else:
            kp_terms.add(term)
        check_anchor(g(k, "anchor"), "knowledge_points", "knowledge_points[%d]" % i, errors, anchor_set, sections)
        if not isinstance(g(k, "note"), str) or not g(k, "note"):
            errors.append("knowledge_points[%d] missing note" % i)
        aliases = g(k, "aliases", [])
        if aliases is not None and not isinstance(aliases, list):
            errors.append("knowledge_points[%d] aliases is not a list" % i)
    terms = g(case, "required_terms", [])
    if isinstance(terms, list):
        for t in terms:
            if str(t) not in kp_terms:
                errors.append("knowledge point missing required term %r" % t)
    alias_count = sum(len(g(k, "aliases", []) or []) for k in kps if isinstance(k, dict))
    stats["aliases"] = alias_count
    if alias_count == 0:
        warnings.append("no aliases/synonyms in knowledge index — hurts retrievability")

    # structured sources and change records
    sources = g(result, "sources")
    if not isinstance(sources, dict):
        errors.append("sources must be a structured object with material_files")
    elif not isinstance(g(sources, "material_files"), list) or not g(sources, "material_files"):
        errors.append("sources.material_files must be a non-empty list")
    cr = g(result, "change_records")
    if not isinstance(cr, list) or not cr:
        errors.append("change_records must be a non-empty list")
    if g(result, "uncertain") is None:
        warnings.append("no uncertain list")
    return errors, warnings, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--case", default=None)
    args = ap.parse_args()
    try:
        with open(args.result, encoding="utf-8") as fh:
            result = json.load(fh)
    except Exception as exc:
        print(json.dumps({"status": "fail", "errors": ["cannot load result: %s" % exc]}, ensure_ascii=False))
        sys.exit(1)
    case = {}
    if args.case:
        try:
            with open(args.case, encoding="utf-8") as fh:
                case = json.load(fh)
        except Exception:
            case = {}
    errors, warnings, stats = audit(result, case)
    print(json.dumps({
        "status": "pass" if not errors else "fail",
        "errors": errors, "warnings": warnings, "stats": stats,
    }, ensure_ascii=False, indent=1))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
