#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nanopublication assertion-result validator (v1).

Deterministic, standard library only. Checks that every assertion is atomic,
carries a verbatim minimal evidence quote bound to a REAL location, uses only
header-provided source metadata, and has content-derived stable identifiers.

Usage:
  python assertion_validate.py --result result.json --case case.json
  python assertion_validate.py --result result.json --case case.json --fill-ids
"""
import argparse
import hashlib
import json
import re
import sys

# Controlled relation vocabulary (mirrors references/interface.md v1).
RELATIONS = {
    "improves", "reduces", "supplies", "anchors", "causes",
    "transfers_to", "suggests", "achieves", "enables",
    "associated_with", "reports", "measured_at",
}
MODALITIES = {"asserted", "may", "suggests", "can", "likely"}
POLARITIES = {"positive", "negative"}
STATUSES = {"ok", "partial", "unreadable", "tool_missing"}
META_FIELDS = ["source_id", "paper_title", "authors", "year", "version", "doi"]
ASSERTION_STRING_FIELDS = ["subject", "relation", "object", "condition", "modality", "polarity"]
ASSERTION_REQUIRED = ASSERTION_STRING_FIELDS + [
    "evidence", "source_metadata", "confidence_basis", "identity_key", "assertion_id"
]

# A coordinating conjunction immediately followed by a real predicate verb is
# the signature of an un-split composite assertion / an over-wide quote.
# Narrow, verb-gated on purpose: do NOT flag "和/and" inside ordinary noun phrases
# (the Q2 failure was a regex that flagged "3 shows" as a fidelity token).
COMPOUND_RE = re.compile(
    r"\b(and|or)\s+(reduces?|improves?|shows?|demonstrates?|suggests?|"
    r"increases?|decreases?|causes?|anchors?|supplies?|supply|enables?|"
    r"transfers?|transfer)\b",
    re.IGNORECASE,
)
PAGE_RE = re.compile(r"\b(page|p)\.?\s*#?\s*\d+\b", re.IGNORECASE)
ID_RE = re.compile(r"^asrt-[0-9a-f]{12}$")


def content_key(a):
    """Canonical dedup key: content only, never an array index."""
    return "|".join(str(a.get(k, "")) for k in ["source_id"] + ASSERTION_STRING_FIELDS)


def assertion_id(a):
    """Stable content-derived id. Single source of truth = this function."""
    seed = "nanopub-v1||" + content_key(a)
    return "asrt-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--case", required=True)
    ap.add_argument("--fill-ids", action="store_true",
                    help="compute assertion_id/identity_key from content and write back before validating")
    args = ap.parse_args()

    errors = []
    checked = 0

    def err(code, msg):
        errors.append({"code": code, "message": msg})

    # --- Load with explicit failure; never silently skip bad types. ---
    try:
        with open(args.case, encoding="utf-8") as f:
            case = json.load(f)
    except Exception as e:
        print(json.dumps({"valid": False, "errors": [{"code": "CASE_LOAD", "message": str(e)}]}, ensure_ascii=False))
        return 2
    try:
        with open(args.result, encoding="utf-8") as f:
            result = json.load(f)
    except Exception as e:
        print(json.dumps({"valid": False, "errors": [{"code": "RESULT_LOAD", "message": str(e)}]}, ensure_ascii=False))
        return 2

    if not isinstance(case, dict):
        err("CASE_TYPE", "case.json must be an object")
        _emit(errors, checked)
        return 1
    if not isinstance(result, dict):
        err("RESULT_TYPE", "result.json must be an object")
        _emit(errors, checked)
        return 1

    material = case.get("material")
    header = case.get("source_header")
    if not isinstance(material, dict):
        err("MATERIAL", "case.material must be an object of location -> text")
        material = {}
    if not isinstance(header, dict):
        err("HEADER", "case.source_header must be an object")
        header = {}

    # Top-level fields
    if result.get("case_id") != case.get("case_id"):
        err("CASE_ID", "result.case_id must equal case.case_id (got %r)" % result.get("case_id"))
    if result.get("status") not in STATUSES:
        err("STATUS", "result.status must be one of %s" % sorted(STATUSES))

    assertions = result.get("assertions")
    if not isinstance(assertions, list):
        err("ASSERTIONS", "result.assertions must be an array")
        assertions = []
    if not assertions:
        err("ASSERTIONS_EMPTY", "result.assertions must not be empty")

    for top in ["uncertain", "sources", "change_records"]:
        if not isinstance(result.get(top), list):
            err("FIELD_TYPE", "result.%s must be an array" % top)

    seen_keys = {}
    for i, a in enumerate(assertions):
        checked += 1
        tag = "assertions[%d]" % i
        if not isinstance(a, dict):
            err("ASSERTION_TYPE", "%s must be an object" % tag)
            continue

        # Required fields + types. In --fill-ids mode the two id fields are
        # supplied by this script, so their absence is not an error here.
        for k in ASSERTION_REQUIRED:
            if k not in a and not (args.fill_ids and k in ("identity_key", "assertion_id")):
                err("MISSING_FIELD", "%s missing %s" % (tag, k))
        for k in ASSERTION_STRING_FIELDS:
            if k in a and not isinstance(a[k], str):
                err("FIELD_TYPE", "%s.%s must be a string" % (tag, k))

        relation = a.get("relation")
        if relation not in RELATIONS:
            err("RELATION", "%s.relation %r not in controlled vocabulary" % (tag, relation))
        if a.get("modality") not in MODALITIES:
            err("MODALITY", "%s.modality %r invalid" % (tag, a.get("modality")))
        if a.get("polarity") not in POLARITIES:
            err("POLARITY", "%s.polarity %r invalid" % (tag, a.get("polarity")))

        # Atomicity: one predicate per assertion
        composite_text = "%s %s" % (a.get("subject", ""), a.get("object", ""))
        if COMPOUND_RE.search(composite_text):
            err("COMPOUND", "%s looks composite (and/or + predicate) — split it" % tag)

        # Evidence: verbatim quote bound to the claimed real location
        ev = a.get("evidence")
        if not isinstance(ev, dict):
            err("EVIDENCE", "%s.evidence must be an object" % tag)
        else:
            quote = ev.get("quote")
            loc = ev.get("location")
            if not isinstance(quote, str) or not quote:
                err("EVIDENCE_QUOTE", "%s.evidence.quote must be a non-empty string" % tag)
            if not isinstance(loc, str) or not loc:
                err("EVIDENCE_LOC", "%s.evidence.location must be a non-empty string" % tag)
            else:
                if PAGE_RE.search(loc):
                    err("FABRICATED_PAGE", "%s.evidence.location %r looks like a PDF page, not a real id" % (tag, loc))
                if loc not in material:
                    err("LOC_UNKNOWN", "%s.evidence.location %r not declared in case material" % (tag, loc))
                elif isinstance(quote, str) and quote:
                    if quote not in material[loc]:
                        err("QUOTE_NOT_VERBATIM", "%s quote is not a verbatim substring of %s" % (tag, loc))
                    if COMPOUND_RE.search(quote):
                        err("EVIDENCE_TOO_WIDE", "%s quote spans a composite/over-wide fragment" % tag)
                    # v2: minimal-SUFFICIENT — a 2-3 word fragment cannot
                    # independently support the断言 and drops the subject.
                    if len(quote.split()) < 4:
                        err("EVIDENCE_TOO_SHORT",
                            "%s quote has %d words; too short to independently support the claim" % (tag, len(quote.split())))

        # Source metadata: only header values, nothing invented
        sm = a.get("source_metadata")
        if not isinstance(sm, dict):
            err("SOURCE_META", "%s.source_metadata must be an object" % tag)
        else:
            for f in META_FIELDS:
                if f not in sm:
                    err("SOURCE_META_MISSING", "%s.source_metadata missing %s" % (tag, f))
                elif sm[f] != header.get(f):
                    err("SOURCE_META_FABRICATED",
                        "%s.source_metadata.%s = %r but header says %r" % (tag, f, sm[f], header.get(f)))

        # v3: evidence mode (direct vs indirect inference)
        if isinstance(ev, dict) and "mode" in ev and ev["mode"] not in ("direct", "indirect"):
            err("EVIDENCE_MODE", "%s.evidence.mode must be direct|indirect" % tag)

        # v3: relation_raw is optional but must be a string when present
        if "relation_raw" in a and not isinstance(a["relation_raw"], str):
            err("RELATION_RAW", "%s.relation_raw must be a string" % tag)

        # v3: structured confidence basis
        cb = a.get("confidence_basis")
        if not isinstance(cb, dict):
            err("CONFIDENCE_BASIS", "%s.confidence_basis must be an object {kind,why}" % tag)
        else:
            if cb.get("kind") not in ("direct", "inferred", "modal"):
                err("CONFIDENCE_KIND", "%s.confidence_basis.kind must be direct|inferred|modal" % tag)
            if not isinstance(cb.get("why"), str) or not cb["why"].strip():
                err("CONFIDENCE_WHY", "%s.confidence_basis.why must be a non-empty string" % tag)

        # Stable, content-derived identifiers — canonical value comes from this script only
        a_with_source = dict(a)
        if isinstance(sm, dict):
            a_with_source["source_id"] = sm.get("source_id", "")
        canonical_key = content_key(a_with_source)
        canonical_id = assertion_id(a_with_source)
        if args.fill_ids:
            a["identity_key"] = canonical_key
            a["assertion_id"] = canonical_id
        else:
            if a.get("identity_key") != canonical_key:
                err("IDENTITY_KEY", "%s.identity_key is not the canonical content key" % tag)
            if not isinstance(a.get("assertion_id"), str) or not ID_RE.match(a.get("assertion_id", "")):
                err("ASSERTION_ID", "%s.assertion_id must look like asrt-<12hex> (stable, not an index)" % tag)
            elif a.get("assertion_id") != canonical_id:
                err("ASSERTION_ID", "%s.assertion_id does not match content-derived id" % tag)

        k = a.get("identity_key")
        if isinstance(k, str):
            if k in seen_keys:
                err("DUPLICATE", "%s duplicates identity_key of %s" % (tag, seen_keys[k]))
            else:
                seen_keys[k] = tag

    # v2: coverage denominator comes from the case, not from the agent's claim.
    # Every declared material location must either be covered by an assertion
    # or be explicitly acknowledged in uncertain (e.g. a deduplicated sentence).
    covered = set()
    for a in assertions:
        if isinstance(a, dict) and isinstance(a.get("evidence"), dict):
            loc = a["evidence"].get("location")
            if isinstance(loc, str):
                covered.add(loc)
    uncertain_blob = json.dumps(result.get("uncertain", []), ensure_ascii=False)
    for loc in material:
        if loc not in covered and loc not in uncertain_blob:
            err("UNCOVERED_LOCATION",
                "material location %r has no assertion and is not listed in uncertain" % loc)

    if args.fill_ids and not errors:
        with open(args.result, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    _emit(errors, checked)
    return 0 if not errors else 1


def _emit(errors, checked):
    print(json.dumps({
        "valid": not errors,
        "checked_assertions": checked,
        "error_count": len(errors),
        "errors": errors[:40],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
