#!/usr/bin/env python3
"""Strict validator for the literature knowledge-graph Skill (Q3).

Checks (from real failure cases):
  - every node/edge has independent source_id + paragraph_id + short quote
  - edges only when experimental conditions match explicitly (no "condition搬家")
  - merges require an identity key; same-name-different-identity must not merge
  - no cross-paper synthesis of conditions/samples/numbers
  - JATS paragraph ids, NOT invented PDF page numbers
  - validator itself handles None / wrong types / missing fields without crashing
Exit code 0 = pass, 1 = fail. Compact JSON output (budget friendly).
"""
import argparse
import json
import sys


def g(d, k, default=None):
    return d.get(k, default) if isinstance(d, dict) else default


def audit(result, case):
    errors, warnings, stats = [], [], {}
    if not isinstance(result, dict):
        return ["result.json is not an object"], [], {}

    nodes = g(result, "nodes", []) or []
    edges = g(result, "edges", []) or []
    if not isinstance(nodes, list):
        return ["nodes is not a list"], [], {}
    if not isinstance(edges, list):
        return ["edges is not a list"], [], {}
    stats["nodes"] = len(nodes)
    stats["edges"] = len(edges)
    # v2: atomicity check — composite labels swallow real objects and kill recall
    import re as _re
    composite = 0
    for n in nodes:
        label = str(g(n, "label", "")) if isinstance(n, dict) else ""
        ions = _re.findall(r"Ca|Zn|Sr|Mg|Fe", label, flags=_re.I)
        temps = _re.findall(r"\d+\s*°?C|\d+\s*K\b", label)
        volts = _re.findall(r"\d+\s*kV", label, flags=_re.I)
        if len(set(ions)) >= 2 or len(temps) >= 2 or len(volts) >= 2:
            composite += 1
    stats["composite_labels"] = composite
    if composite:
        warnings.append(f"{composite} node label(s) bundle multiple atoms (ions/temps/volts); split into atomic nodes for recall")

    # independent source binding for nodes
    node_ids = set()
    node_by_id = {}
    for i, n in enumerate(nodes):
        if not isinstance(n, dict):
            errors.append(f"nodes[{i}] not object")
            continue
        nid = g(n, "id")
        if not isinstance(nid, str) or not nid:
            errors.append(f"nodes[{i}] missing id")
            continue
        if nid in node_ids:
            errors.append(f"duplicate node id: {nid}")
        node_ids.add(nid)
        node_by_id[nid] = n
        src = g(n, "source")
        if not isinstance(src, dict):
            errors.append(f"node {nid} missing source object")
            continue
        sid = g(src, "source_id")
        pid = g(src, "paragraph_id")
        quote = g(src, "quote")
        if not isinstance(sid, str) or not sid:
            errors.append(f"node {nid} source.source_id missing")
        if not isinstance(pid, str) or not pid:
            errors.append(f"node {nid} source.paragraph_id missing (JATS id, not PDF page)")
        else:
            if pid.lower().startswith("page ") or (pid.isdigit() and len(pid) <= 3):
                errors.append(f"node {nid} paragraph_id '{pid}' looks like an invented PDF page, not a JATS id")
        if not isinstance(quote, str) or not quote.strip():
            errors.append(f"node {nid} source.quote missing (must be a short verbatim excerpt)")
        # identity key for merge tracking
        if g(n, "merged_from") and not g(n, "identity_key"):
            errors.append(f"node {nid} has merged_from but no identity_key (merge basis not recorded)")

    # edges: evidence + condition match + no cross-paper synthesis
    for i, e in enumerate(edges):
        if not isinstance(e, dict):
            errors.append(f"edges[{i}] not object")
            continue
        s, t = g(e, "source"), g(e, "target")
        if s not in node_ids or t not in node_ids:
            errors.append(f"edges[{i}] references unknown node: {s} -> {t}")
        rel = g(e, "relation")
        if not isinstance(rel, str) or not rel.strip():
            errors.append(f"edges[{i}] missing relation type")
        ev = g(e, "evidence")
        if not isinstance(ev, dict):
            errors.append(f"edges[{i}] missing evidence object")
            continue
        if not g(ev, "source_id") or not g(ev, "paragraph_id") or not g(ev, "quote"):
            errors.append(f"edges[{i}] evidence incomplete (need source_id/paragraph_id/quote)")
        cond = g(e, "condition_match")
        # edges asserting same sample/condition across sources need explicit basis
        if g(e, "cross_paper") is True:
            if cond not in ("explicit_same", "matched"):
                warnings.append(f"edges[{i}] cross_paper edge without explicit condition match — verify no condition搬家")
            if not g(e, "basis_quote"):
                errors.append(f"edges[{i}] cross_paper edge requires basis_quote (原文依据)")
        if cond == "assumed" or cond == "implied":
            warnings.append(f"edges[{i}] edge based on assumed/implied condition — should be unresolved instead")

    # queries: at least 3 executed with results and evidence
    queries = g(result, "queries", []) or []
    stats["queries"] = len(queries)
    if len(queries) < 3:
        errors.append(f"need at least 3 executed queries, got {len(queries)}")
    for i, q in enumerate(queries):
        if not isinstance(q, dict):
            continue
        if not g(q, "query"):
            errors.append(f"queries[{i}] missing query text")
        if g(q, "result") is None:
            errors.append(f"queries[{i}] missing result")
        if not g(q, "spec"):
            warnings.append(f"queries[{i}] missing spec — result may not be computed by real traversal")
        qev = g(q, "evidence")
        if isinstance(qev, str):
            errors.append(f"queries[{i}].evidence is a string; use structured {{source_id,paragraph_id,quote}}")
        elif isinstance(qev, list):
            for j, e in enumerate(qev):
                if isinstance(e, str) or not (g(e, "source_id") and g(e, "paragraph_id")):
                    errors.append(f"queries[{i}].evidence[{j}] not structured source binding")
        elif qev is None:
            warnings.append(f"queries[{i}] missing evidence")

    # honesty
    if g(result, "uncertain") is None:
        warnings.append("no uncertain list: record unresolved relations/conflicts")
    sources = g(result, "sources")
    if sources is None:
        warnings.append("no sources list: declare corpus files actually read")
    elif isinstance(sources, (list, dict)):
        blob = json.dumps(sources, ensure_ascii=False)
        if "10." not in blob or "DOI" not in blob:
            warnings.append("sources does not record paper DOI/authors mapping (root DOI belongs to primary only)")
    if not g(result, "status"):
        errors.append("no status field")

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
        print(json.dumps({"status": "fail", "errors": [f"cannot load result: {exc}"]}, ensure_ascii=False))
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
