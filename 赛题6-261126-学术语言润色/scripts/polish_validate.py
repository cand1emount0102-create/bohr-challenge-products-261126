#!/usr/bin/env python3
"""Deterministic checker for the conservative sentence-polish Skill (Q6 v1).

It checks ONLY what can be decided by rules (it cannot judge register or
negation-scope subtleties -- a read-back by the agent/reviewer is still needed):

  1. output_contract fields (denominator from case.json, not self-reported)
  2. case_id matches case.json
  3. sentence 1:1 alignment against case.declared_sentence_ids
  4. protected tokens: quantities/numbers, citation ids, figure/table/equation
     pointers -- verbatim conserved (whitespace inside a quantity normalized)
  5. hedge tier, negation, condition, quantifier, causal/correlational signatures
     conserved per sentence (compare assertions, not keywords)
  6. glossary sweep: variants eliminated except the allowed definition occurrence
  7. Chinese-target guard: no ordinary English content word left in revision
  8. change ledger: controlled type vocabulary, concrete reason, 1:1 with edits

Fidelity whitelist is SHORT and CLOSED. `3 shows` => quantity `3` + ordinary
verb `shows`; the verb is NOT protected and may be edited freely. This is the
Q2-v1 script bug this checker is built to avoid.

Exit 0 = pass, 1 = fail. Prints one compact JSON object.
"""
import argparse
import json
import re
import sys

# ---- controlled vocabularies -------------------------------------------------
CHANGE_TYPES = {
    "grammar", "syntax", "punctuation", "collocation", "word_choice",
    "term_consistency", "register", "conciseness",
}
BANNED_REASONS = {"更流畅", "更自然", "更学术", "改善表达", "优化表达", "improve fluency",
                  "better style", "more natural", "make it better"}

UNIT_RE = re.compile(
    r"\d+(?:[.,]\d+)*\s*(?:°C|℃|kV|eV|mA|MPa|nm|µm|um|mg|mL|ml|kg|ppm|mM|µM|"
    r"%|min|hrs|h|s|V|A|K|Da|g)(?![A-Za-z])"
)
NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")
CITE_RE = re.compile(r"\[\d+(?:[,\s\-]+\d+)*\]|\(\d{4}\)")
FIG_RE = re.compile(
    r"(?:Fig\.?|Figure|Table|Eq\.?|Equation|Sec\.?|Ref\.?)\s*\(?\d+[a-z]?\)?"
    r"|S\d+\s*(?:Fig\.?|Table|Text)", re.I
)

WEAK_HEDGES = {"might", "could", "possibly", "perhaps", "maybe", "unlikely"}
MED_HEDGES = {"may", "can", "suggest", "suggests", "suggested", "appear", "appears",
              "seem", "seems", "tend", "tends", "possible", "likely", "generally",
              "often", "relatively", "approximately", "roughly", "somewhat",
              "indicate", "indicates", "indicated", "probably"}
NEG_WORDS = {"not", "no", "never", "none", "neither", "nor", "without", "cannot",
             "hardly", "barely", "rarely", "n't", "不", "无", "未", "非", "没有", "并不"}
COND_WORDS = {"if", "unless", "although", "though", "whether", "provided", "whenever",
              "once", "given", "under", "虽然", "尽管", "如果", "除非"}
QUANT_WORDS = {"all", "every", "each", "some", "several", "many", "few", "most", "any",
               "both", "either", "always", "never", "usually", "所有", "每个", "一些",
               "若干", "大多数", "总是", "从不"}
CAUSE_WORDS = {"because", "therefore", "thus", "hence", "consequently", "causal",
               "causes", "caused", "cause", "leads", "lead", "due", "导致", "因此", "由于"}
CORR_WORDS = {"associated", "correlated", "correlates", "correlate", "correlation",
              "related", "relate", "linked", "link", "association", "associate",
              "相关", "关联"}

# Latin tokens allowed to remain in a Chinese-target revision: markers, units,
# glossary-style abbreviations and standard academic Latin shorts.
LATIN_ALLOW = {
    "fig", "table", "eq", "ref", "sec", "s1", "s2", "si", "et", "al", "vs", "i",
    "e", "g", "p1", "p2", "go", "go/cgo", "eds", "xrd", "fe-sem", "fe-sem",
    "dna", "rna", "pcr", "ci", "ev", "kv", "ma", "nm", "um", "mg", "ml", "kg",
    "da", "mpa", "min", "h", "s", "v", "a", "k", "ppm", "ph", "n", "co2",
}


def s(x):
    return x if isinstance(x, str) else ("" if x is None else str(x))


def norm(x):
    """Whitespace-normalized string for conserved-token comparison."""
    return re.sub(r"\s+", " ", s(x)).strip()


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def words(text):
    return re.findall(r"[A-Za-z]+|[\u4e00-\u9fff]", s(text).lower())


def signature(text, lexicon):
    """Sorted list of markers present (case-insensitive for Latin)."""
    toks = set(words(text))
    hits = set()
    for w in lexicon:
        wl = w.lower()
        if len(wl) == 1 and w in ("不", "无", "未", "非"):
            if w in s(text):
                hits.add(w)
        elif re.match(r"^[A-Za-z]+$", wl):
            if wl in toks:
                hits.add(wl)
        else:
            if wl in s(text).lower():
                hits.add(wl)
    return sorted(hits)


def stem(word):
    """Light lemmatization so inflection is not mistaken for strength change."""
    w = word.lower()
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("sses"):
        return w[:-2]
    if w.endswith("es") and len(w) > 4 and w[:-2].endswith(("ch", "sh", "x", "s")):
        return w[:-2]
    if w.endswith("s") and len(w) > 3 and not w.endswith("ss"):
        return w[:-1]
    if w.endswith("ed") and len(w) > 4:
        return w[:-2]
    if w.endswith("ing") and len(w) > 5:
        return w[:-3]
    return w


def hedges(text):
    """Hedge signature = tier AND stemmed word count per tier.

    v2 fix: v1 compared only W/M tier presence, so a baseline that deleted
    'possible' from 'suggest a possible mechanism' passed the checker. Count
    the actual hedge stems per tier, ignoring pure inflection
    (suggest -> suggests is grammar, not strengthening).
    """
    toks = [stem(t) for t in re.findall(r"[a-z]+", s(text).lower())]
    weak = sorted(t for t in toks if t in WEAK_HEDGES)
    med = sorted(t for t in toks if t in MED_HEDGES)
    return ["W:%d:%s" % (len(weak), ",".join(weak)), "M:%d:%s" % (len(med), ",".join(med))]


def quantity_tokens(text):
    return sorted({norm(m.group(0)).replace(" ", "") for m in UNIT_RE.finditer(s(text))})


def bare_numbers(text):
    return sorted({m.group(0) for m in NUM_RE.finditer(s(text))})


def cites(text):
    return sorted({norm(m.group(0)).replace(" ", "") for m in CITE_RE.finditer(s(text))})


def figs(text):
    return sorted({norm(m.group(0)).lower().replace(" ", "") for m in FIG_RE.finditer(s(text))})


def is_cjk_sentence(text):
    lat = len(re.findall(r"[A-Za-z]", s(text)))
    cjk = len(re.findall(r"[\u4e00-\u9fff]", s(text)))
    return cjk > 0 and cjk >= lat


def latin_residue(text, allowed_extra=None):
    allow = set(LATIN_ALLOW) | {s(x).lower() for x in (allowed_extra or [])}
    runs = re.findall(r"[A-Za-z][A-Za-z\-']*", s(text))
    bad = []
    for run in runs:
        low = run.lower()
        if low in allow:
            continue
        if len(run) <= 6 and run.upper() == run and any(ch.isdigit() for ch in run):
            continue  # all-caps ids like P12
        bad.append(run)
    return bad


def audit(result, case, glossary_override=None):
    errors, warnings, stats = [], [], {}
    if not isinstance(result, dict):
        return ["result.json is not an object"], [], {}

    # 1. Contract fields -- denominator comes from case.json, not the result.
    contract = case.get("output_contract") if isinstance(case, dict) else None
    if isinstance(contract, list) and contract:
        missing = [k for k in contract if k not in result]
        stats["contract_fields"] = len(contract)
        if missing:
            errors.append("missing output_contract fields: " + ", ".join(map(str, missing)))
    else:
        warnings.append("case.json has no output_contract; cannot enforce external field denominator")

    # 2. case_id from the input.
    expected = case.get("case_id") if isinstance(case, dict) else None
    if expected is not None and s(result.get("case_id")) != s(expected):
        errors.append("case_id mismatch: result=%r case=%r" % (result.get("case_id"), expected))

    status = s(result.get("status"))
    if status not in ("ok", "partial", "unreadable", "tool_missing"):
        errors.append("invalid status: %r" % status)

    # 3. Sentence 1:1 alignment with the EXTERNAL declared id list.
    sents = result.get("sentences")
    if not isinstance(sents, list) or not sents:
        errors.append("sentences must be a non-empty list")
        sents = []
    ids = []
    for i, sent in enumerate(sents):
        if not isinstance(sent, dict):
            errors.append("sentences[%d] not object" % i)
            continue
        sid = s(sent.get("id")).strip()
        if not sid:
            errors.append("sentences[%d] empty id" % i)
        ids.append(sid)
        if not s(sent.get("original")).strip():
            errors.append("sentences[%d] empty original" % i)
        if not s(sent.get("revised")).strip():
            errors.append("sentences[%d] empty revised" % i)
    if len(set(ids)) != len(ids):
        errors.append("duplicate sentence ids: %s" % ids)
    declared = case.get("declared_sentence_ids") if isinstance(case, dict) else None
    if isinstance(declared, list) and declared:
        dset = {str(x) for x in declared}
        if set(ids) != dset:
            errors.append("sentence ids != case.declared_sentence_ids: missing=%s extra=%s"
                          % (sorted(dset - set(ids)), sorted(set(ids) - dset)))
        stats["declared_sentences"] = len(dset)
    stats["sentences"] = len(ids)

    # revised_text must contain each revised sentence, in order.
    revised_text = norm(result.get("revised_text"))
    if not revised_text:
        errors.append("revised_text empty")
    cursor = 0
    for i, sent in enumerate(sents):
        if not isinstance(sent, dict):
            continue
        rev = norm(sent.get("revised"))
        if not rev:
            continue
        pos = revised_text.find(rev, cursor)
        if pos < 0:
            errors.append("sentences[%d].revised not found in revised_text in order" % i)
        else:
            cursor = pos + len(rev)

    # Glossary is an external single source; extract it before the sentence sweep.
    gl = glossary_override
    if gl is None and isinstance(case, dict):
        gl = case.get("glossary")
    terms = []
    if isinstance(gl, dict):
        terms = gl.get("terms", []) or []
    elif isinstance(gl, list):
        terms = gl
    allowed_latin = []
    for t in terms:
        if isinstance(t, dict):
            allowed_latin.append(s(t.get("canonical") or t.get("term")))
            allowed_latin += [s(v) for v in (t.get("variants") or [])]

    # 4/5. Per-sentence conservation.
    stats["changes_rows"] = 0
    index = {s(sent.get("id")): sent for sent in sents if isinstance(sent, dict)}
    for i, sent in enumerate(sents):
        if not isinstance(sent, dict):
            continue
        sid = s(sent.get("id")) or "S%d" % i
        orig, rev = s(sent.get("original")), s(sent.get("revised"))
        # --- protected tokens ---
        rev_compact = norm(rev).replace(" ", "")
        for name, fn in (("quantity", quantity_tokens), ("number", bare_numbers),
                         ("citation", cites)):
            missing = [t for t in fn(orig) if t not in rev_compact]
            if missing:
                errors.append("%s: %s lost in revision: %s" % (sid, name, missing[:8]))
        fig_missing = [t for t in figs(orig) if t not in rev_compact.lower()]
        if fig_missing:
            errors.append("%s: figure/table pointer lost in revision: %s" % (sid, fig_missing[:8]))
        # --- assertion signatures ---
        if hedges(orig) != hedges(rev):
            errors.append("%s: hedge tier changed %s -> %s (strengthened or weakened)"
                          % (sid, hedges(orig), hedges(rev)))
        for name, lex in (("negation", NEG_WORDS), ("condition", COND_WORDS),
                          ("quantifier", QUANT_WORDS)):
            if signature(orig, lex) != signature(rev, lex):
                errors.append("%s: %s scope changed %s -> %s"
                              % (sid, name, signature(orig, lex), signature(rev, lex)))
        for name, lex in (("causal", CAUSE_WORDS), ("correlational", CORR_WORDS)):
            if bool(signature(orig, lex)) != bool(signature(rev, lex)):
                errors.append("%s: %s framing changed (causation/correlation swap?)" % (sid, name))
        # --- Chinese-target ordinary-English residue guard ---
        if is_cjk_sentence(orig):
            bad = latin_residue(rev, allowed_latin)
            if bad:
                errors.append("%s: ordinary English words left in Chinese revision: %s"
                              % (sid, bad[:8]))

    # 6. Glossary sweep (external single source: case glossary or override).
    all_revised = " ".join(s(x.get("revised")) for x in sents if isinstance(x, dict))
    all_original = " ".join(s(x.get("original")) for x in sents if isinstance(x, dict))
    for t in terms:
        if not isinstance(t, dict):
            continue
        canonical = s(t.get("canonical") or t.get("term"))
        variants = [s(v) for v in (t.get("variants") or []) if s(v)]
        if not canonical:
            continue
        max_var = int(t.get("max_variant_occurrences", 0) or 0)
        for var in variants:
            if canonical.lower() == var.lower():
                continue
            n = len(re.findall(r"\b" + re.escape(var) + r"\b", all_revised, flags=re.I))
            if n > max_var:
                errors.append("glossary drift: variant %r remains %d time(s) (max %d); canonical %r"
                              % (var, n, max_var, canonical))
        if (canonical.lower() in all_original.lower()
                or any(v.lower() in all_original.lower() for v in variants)):
            if canonical.lower() not in all_revised.lower():
                errors.append("glossary term %r disappeared from revision" % canonical)

    # 8. Change ledger.
    changes = result.get("changes")
    if not isinstance(changes, list):
        errors.append("changes must be a list")
        changes = []
    stats["changes_rows"] = len(changes)
    changed_ids = set()
    covered_ids = set()
    for i, ch in enumerate(changes):
        if not isinstance(ch, dict):
            errors.append("changes[%d] not object" % i)
            continue
        sid = s(ch.get("sentence_id"))
        if sid not in index:
            errors.append("changes[%d] references unknown sentence_id %r" % (i, sid))
            continue
        sent = index[sid]
        ctype = s(ch.get("type"))
        if ctype not in CHANGE_TYPES:
            errors.append("changes[%d] invalid type %r (allowed: %s)"
                          % (i, ctype, sorted(CHANGE_TYPES)))
        reason = norm(ch.get("reason"))
        if len(re.sub(r"\s", "", reason)) < 6 or reason.lower() in BANNED_REASONS:
            errors.append("changes[%d] reason empty or vague: %r" % (i, ch.get("reason")))
        orig_frag, rev_frag = norm(ch.get("original")), norm(ch.get("revised"))
        if not orig_frag or orig_frag not in norm(sent.get("original")):
            errors.append("changes[%d].original not found in sentence %s" % (i, sid))
        if not rev_frag or rev_frag not in norm(sent.get("revised")):
            errors.append("changes[%d].revised not found in sentence %s" % (i, sid))
        if orig_frag == rev_frag and norm(reason):
            errors.append("changes[%d] records no actual edit" % i)
        covered_ids.add(sid)
    for sid, sent in index.items():
        if norm(sent.get("original")) != norm(sent.get("revised")):
            changed_ids.add(sid)
    no_row = sorted(changed_ids - covered_ids)
    if no_row:
        errors.append("changed sentences with no change row: %s" % no_row)
    orphan_row = sorted(covered_ids - changed_ids)
    if orphan_row:
        warnings.append("change rows for sentences that are textually unchanged: %s" % orphan_row)

    # 9. (v2) fact_source_map denominator comes from the TEXT, not self-report.
    fsm = result.get("fact_source_map")
    fsm_text = json.dumps(fsm, ensure_ascii=False) if isinstance(fsm, list) else ""
    required_items = set()
    for sent in sents:
        if not isinstance(sent, dict):
            continue
        rev = s(sent.get("revised"))
        required_items.update(quantity_tokens(rev))
        required_items.update(cites(rev))
        required_items.update(figs(rev))
    for t in terms:
        if isinstance(t, dict):
            required_items.add(s(t.get("canonical") or t.get("term")))
    uncovered = sorted(x for x in required_items
                       if x and x.replace(" ", "").lower() not in fsm_text.replace(" ", "").lower())
    stats["fact_source_required"] = len(required_items)
    if not isinstance(fsm, list) or not fsm:
        errors.append("fact_source_map empty: external token list cannot be mapped")
    elif uncovered:
        errors.append("fact_source_map missing externally-required items: %s" % uncovered[:12])

    # 10. (v2) version_boundary confirmation triggers.
    vb = result.get("version_boundary")
    confirmation_triggers = [w for w in ("always", "never", "unambiguously", "not necessary",
                                         "not all", "not necessarily")
                             if w in all_revised.lower()]
    if not isinstance(vb, dict):
        errors.append("version_boundary must be an object")
    else:
        if len(norm(vb.get("diff_summary"))) < 10:
            errors.append("version_boundary.diff_summary too short/absent")
        if confirmation_triggers and not vb.get("manual_confirm"):
            errors.append("version_boundary.manual_confirm empty while confirmation triggers present: %s"
                          % confirmation_triggers)
        for k in ("manual_confirm", "material_gaps", "anomalies"):
            if k not in vb:
                warnings.append("version_boundary lacks %s" % k)

    # 11. (v3) per-sentence glossary sweep evidence. The sweep is produced by
    # the agent, so read it from result.glossary (not the input case glossary).
    result_glossary = result.get("glossary")
    if isinstance(result_glossary, dict):
        result_glossary = result_glossary.get("terms", [])
    if not isinstance(result_glossary, list):
        result_glossary = []
    sweep_terms = [t for t in result_glossary
                   if isinstance(t, dict) and s(t.get("canonical") or t.get("term"))]
    if sweep_terms:
        any_sweep = False
        for t in sweep_terms:
            sweep = t.get("sweep")
            if not isinstance(sweep, list) or not sweep:
                continue
            any_sweep = True
            swept_ids = {s(row.get("sentence_id")) for row in sweep if isinstance(row, dict)}
            if isinstance(declared, list) and declared and swept_ids != {str(x) for x in declared}:
                errors.append("glossary sweep for %r does not cover declared sentences: %s"
                              % (s(t.get("canonical")), sorted(swept_ids)))
        if not any_sweep:
            errors.append("glossary sweep evidence missing: add glossary[i].sweep per sentence")
        for t in sweep_terms:
            sweep = t.get("sweep") if isinstance(t.get("sweep"), list) else []
            for row in sweep:
                if isinstance(row, dict) and not s(row.get("form")).strip():
                    errors.append("glossary sweep row has empty form for %s" % s(row.get("sentence_id")))

    # 12. (v3) confirmation triggers must be mirrored in uncertain, and the
    # diff_summary must record the register read-back and term-sweep conclusion.
    uncertain = result.get("uncertain")
    if confirmation_triggers and (not isinstance(uncertain, list) or not uncertain):
        errors.append("uncertain empty while confirmation triggers present: %s" % confirmation_triggers)
    if isinstance(uncertain, list):
        for i, item in enumerate(uncertain):
            if not isinstance(item, dict) or not s(item.get("item")).strip() or not s(item.get("reason")).strip():
                errors.append("uncertain[%d] missing item/reason" % i)
    if isinstance(vb, dict):
        summary = norm(vb.get("diff_summary")).lower()
        if "register" not in summary and "语域" not in summary:
            errors.append("version_boundary.diff_summary does not state the register read-back")
        if "sweep" not in summary and "回扫" not in summary:
            errors.append("version_boundary.diff_summary does not state the term-sweep conclusion")

    if "uncertain" not in result:
        warnings.append("no 'uncertain' list; declare gaps/conflicts")
    if "sources" not in result:
        warnings.append("no 'sources' list; declare input files actually read")
    if not isinstance(result.get("sources"), (list, dict)):
        warnings.append("'sources' is not a list/object")

    return errors, warnings, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--case", required=True)
    ap.add_argument("--glossary", default=None)
    args = ap.parse_args()
    try:
        result = load_json(args.result)
        case = load_json(args.case)
        gl = load_json(args.glossary) if args.glossary else None
        errors, warnings, stats = audit(result, case, gl)
    except Exception as exc:  # a checker must never crash on bad input
        errors, warnings, stats = ["checker could not parse input: %s: %s" % (type(exc).__name__, exc)], [], {}
    print(json.dumps({
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "warnings": warnings,
        "stats": stats,
    }, ensure_ascii=False, indent=1))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
