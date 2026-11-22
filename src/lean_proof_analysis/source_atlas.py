#!/usr/bin/env python3
"""Read-only, *heuristic* source-level Lean 4 navigation atlas.

Standard library only. Does not elaborate Lean, check proofs, or infer semantic
mathematical equivalence. All cross-declaration links are lexical candidates.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from statistics import median
import csv
import hashlib
import html
import json
import math
from pathlib import Path
import re
import sys

DECL = re.compile(r"(?m)^[ \t]*(?:(?:private|protected|noncomputable|unsafe|partial|local|scoped)\s+)*(theorem|lemma|def|abbrev|axiom|opaque|instance|example|structure|inductive|class)\s+([\w₀-₉'.!?]+)?")
SCOPE = re.compile(r"(?m)^[ \t]*(namespace|section|end)\b(?:[ \t]+([^\s]+))?")
IMPORT = re.compile(r"(?m)^import[ \t]+([^\n]+)")
IDENT = re.compile(r"[\w₀-₉]+(?:\.[\w₀-₉]+)*", re.UNICODE)
SIM_TOKEN = re.compile(r"[\w₀-₉]+(?:\.[\w₀-₉]+)*|[=≠≤≥<>→↔∀∃¬∧∨∈∉⊆⊂∪∩+-]", re.UNICODE)
MODIFIERS = {"theorem", "lemma", "def", "abbrev", "axiom", "opaque", "instance", "example", "structure", "inductive", "class"}
TACTICS = {"simp", "simpa", "rw", "rwa", "rewrite", "exact", "apply", "refine", "intro", "intros", "rcases", "cases", "obtain", "constructor", "linarith", "nlinarith", "omega", "ring", "norm_num", "positivity", "aesop", "tauto", "by_contra", "by_cases", "have", "let", "calc", "unfold", "change", "subst", "fun_prop", "assumption", "trivial", "decide", "first", "repeat", "induction", "simp_all", "norm_cast", "field_simp", "linear_combination"}
STOP = {"by", "theorem", "lemma", "def", "Prop", "Type", "fun", "forall", "have", "this", "h", "at", "with", "from", "match", "let", "if", "then", "else", "True", "False", "Nat", "0", "1", "2", "3", "4", "5", "s", "n", "x", "N", "h1", "h0", "hz"}
BORDER = re.compile(r"(?m)^[ \t]*(?:namespace|section|end|open|variable|variables|set_option|noncomputable[ \t]+section|import)\b")


def masked(text: str) -> str:
    """Keep lengths/newlines, mask Lean line/block comments (nested) and strings."""
    a = list(text)
    i, depth, quote, line_comment = 0, 0, False, False
    while i < len(a):
        c = text[i]
        d = text[i:i+2]
        if line_comment:
            if c == "\n":
                line_comment = False
            else:
                a[i] = " "
            i += 1
            continue
        if depth:
            if d == "/-":
                a[i] = a[i+1] = " "
                depth += 1
                i += 2
                continue
            if d == "-/":
                a[i] = a[i+1] = " "
                depth -= 1
                i += 2
                continue
            if c != "\n":
                a[i] = " "
            i += 1
            continue
        if quote:
            if c == "\\" and i+1 < len(a):
                a[i] = a[i+1] = " "
                i += 2
                continue
            if c == '"':
                quote = False
            a[i] = " "
            i += 1
            continue
        if d == "--":
            a[i] = a[i+1] = " "
            line_comment = True
            i += 2
            continue
        if d == "/-":
            a[i] = a[i+1] = " "
            depth = 1
            i += 2
            continue
        if c == '"':
            a[i] = " "
            quote = True
        i += 1
    return "".join(a)


def without_comments(text: str) -> str:
    """Mask nested Lean comments but RETAIN string literals and their values.

    Lexical scanning (`masked`) deliberately removes strings, whereas
    comparison must preserve them: `def x := "a"` differs from `def y := "b"`.
    This remains a heuristic, not a full Lean lexer.
    """
    out = list(text)
    i, depth, quote = 0, 0, False
    while i < len(text):
        two = text[i:i + 2]
        if quote:
            if text[i] == "\\" and i + 1 < len(text):
                i += 2
                continue
            if text[i] == '"':
                quote = False
            i += 1
            continue
        if depth:
            if two == "/-":
                depth += 1
                out[i] = out[i + 1] = " "
                i += 2
                continue
            if two == "-/":
                depth -= 1
                out[i] = out[i + 1] = " "
                i += 2
                continue
            if text[i] != "\n":
                out[i] = " "
            i += 1
            continue
        if two == "--":
            while i < len(text) and text[i] != "\n":
                out[i] = " "
                i += 1
            continue
        if two == "/-":
            depth = 1
            out[i] = out[i + 1] = " "
            i += 2
            continue
        if text[i] == '"':
            quote = True
        i += 1
    return "".join(out)


def git_blob_sha(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def similarity_terms(s: str) -> Counter:
    # Numerals, quantifiers and relational operators distinguish proposition
    # forms; ignoring them would spuriously identify `x = 0` and `x ≠ 0`.
    keep_num={"0","1","2","3","4","5"}
    terms=[t for t in SIM_TOKEN.findall(s) if t not in STOP or t in keep_num]
    # Ordered local context supplements binary symbol matching.
    terms += ["pair:"+a+"|"+b for a,b in zip(terms,terms[1:])]
    return Counter(terms)


def normalized_expression(s: str) -> str:
    # Tokenization removes only whitespace. This is a heuristic fingerprint,
    # NOT alpha equivalence, definitional equality or term elaboration.
    return " ".join(re.findall(r"[\w₀-₉]+|[^\s]", s, flags=re.UNICODE))


def find_def_separator(s: str) -> int:
    depths = [0, 0, 0]
    opening = {"(": 0, "[": 1, "{": 2}
    closing = {")": 0, "]": 1, "}": 2}
    for i,c in enumerate(s[:-1]):
        if c in opening:
            depths[opening[c]] += 1
        elif c in closing:
            depths[closing[c]] = max(0, depths[closing[c]]-1)
        elif c == ":" and s[i+1] == "=" and sum(depths) == 0:
            return i
    return -1


def scope_at(scope_changes, offset):
    stack = []
    for kind, name, pos in scope_changes:
        if pos >= offset:
            break
        if kind in ("namespace", "section"):
            stack.append((kind, name))
        else:
            if stack:
                if name:
                    for idx in range(len(stack)-1, -1, -1):
                        if stack[idx][1] == name:
                            stack = stack[:idx]
                            break
                    else:
                        stack.pop()
                else:
                    stack.pop()
    return ".".join([name for kind,name in stack if kind == "namespace" and name])


@dataclass
class D:
    id: str
    name: str
    short_name: str
    kind: str
    path: str
    line: int
    end_line: int
    statement: str
    body: str
    tactics: list[str]
    source_url: str
    statement_fp: str


def scan_file(full_path: Path, root: Path, base_url: str):
    raw = full_path.read_bytes()
    src = raw.decode("utf-8")
    clean = masked(src)
    comparison_src = without_comments(src)
    path = full_path.relative_to(root).as_posix()
    offs = [0] + [i+1 for i,c in enumerate(clean) if c == "\n"]
    lineof = lambda p: bisect_right(offs,p)
    scopes = [(m.group(1),m.group(2) or "",m.start()) for m in SCOPE.finditer(clean)]
    anchors = sorted(set([m.start() for m in DECL.finditer(clean)] + [m.start() for m in BORDER.finditer(clean)] + [len(clean)]))
    out=[]
    for m in DECL.finditer(clean):
        kind, name = m.group(1), m.group(2)
        if not name:
            name = f"anonymous_{lineof(m.start())}"
        ns = scope_at(scopes,m.start())
        # A dotted identifier may still be relative in Lean; this is navigational.
        fq = name if "." in name else (ns+"."+name if ns else name)
        idx=bisect_right(anchors,m.start())
        end = anchors[idx] if idx < len(anchors) else len(src)
        # Extract by original character offsets, then eliminate comments and
        # strings for signatures and dependency scans.
        tail = comparison_src[m.end():end]
        pivot=find_def_separator(tail)
        stmt = tail[:pivot] if pivot >= 0 else tail
        body = tail[pivot+2:] if pivot >= 0 else ""
        body_tokens=IDENT.findall(body)
        out.append(D(
            id=f"{path}:{lineof(m.start())}:{fq}",name=fq,short_name=name.split(".")[-1],kind=kind,
            path=path,line=lineof(m.start()),end_line=max(lineof(m.start()),lineof(max(m.start(),end-1))),
            statement=" ".join(stmt.split()),body=" ".join(body.split()),
            tactics=sorted(set(body_tokens)&TACTICS),
            source_url=f"{base_url}/{path}#L{lineof(m.start())}",
            statement_fp=hashlib.sha256(normalized_expression(stmt + (" := " + body if kind in {"def","abbrev","opaque"} else "")).encode()).hexdigest()[:16],
        ))
    imps=[]
    for m in IMPORT.finditer(clean):
        imps.extend(m.group(1).split())
    return out,imps, {"path":path,"sha256":hashlib.sha256(raw).hexdigest(),"git_blob_sha1":git_blob_sha(raw),"bytes":len(raw),"lines":len(src.splitlines()),"imports":len(imps),"declarations":len(out)}


def match_deps(ds: list[D]):
    by_name=defaultdict(list)
    by_short=defaultdict(list)
    for d in ds:
        by_name[d.name].append(d)
        by_short[d.short_name].append(d)
    edges=set()
    for d in ds:
        # We search theorem types and bodies separately; these are name-based
        # hints, not a Lean elaborated expression dependency DAG.
        for role,part in [("statement",d.statement),("body",d.body)]:
            for term in set(IDENT.findall(masked(part))):
                if term in STOP:
                    continue
                candidates=by_name.get(term,[])
                resolution="qualified" if "." in term else "exact-name"
                if not candidates and "." in term:
                    parts=term.split(".")
                    # Handles `.2.1` projections, not arbitrary subfield paths.
                    while len(parts)>1 and parts[-1].isdigit():
                        parts.pop()
                    base=".".join(parts)
                    candidates=by_name.get(base,[])
                    resolution="projection-base"
                    if not candidates:
                        suffix=base.split(".")[-1]
                        candidates=by_short.get(suffix,[])
                        resolution="unique-short-name"
                if not candidates:
                    candidates=by_short.get(term,[])
                    resolution="unique-short-name"
                if len(candidates)==1 and candidates[0].id!=d.id:
                    edges.add((d.id,candidates[0].id,role,resolution,term))
    return sorted(edges)


def comparison_text(d: D) -> str:
    if d.kind in {"def", "abbrev", "opaque"}:
        return d.statement + " := " + d.body
    return d.statement


def similarities(ds: list[D], max_pairs:int=100_000, min_score:float=.78):
    """TF-IDF cosine and exact syntactic fingerprints (no semantic equivalence)."""
    vocab=[]
    df=Counter()
    for d in ds:
        # Theorems/definitions of different kinds can still be compared.
        # For `def ... : Prop := formula`, the mathematical statement is
        # the right-hand side, NOT merely the `Prop` type annotation.
        c=similarity_terms(comparison_text(d))
        vocab.append(c)
        df.update(c.keys())
    n=len(ds)
    vectors=[]
    norms=[]
    index=defaultdict(list)
    for i,c in enumerate(vocab):
        v={k:tf*(math.log((n+1)/(df[k]+1))+1) for k,tf in c.items()}
        norm=math.sqrt(sum(x*x for x in v.values())) or 1
        vectors.append(v)
        norms.append(norm)
        for k in v:
            if df[k] <= max(8,min(1000,n//3)):
                index[k].append(i)
    pairs=set()
    exact=defaultdict(list)
    fingerprints=[]
    for i,d in enumerate(ds):
        fp=hashlib.sha256(normalized_expression(comparison_text(d)).encode()).hexdigest()[:16]
        fingerprints.append(fp)
        exact[fp].append(i)
    for ids in exact.values():
        if len(pairs) >= max_pairs:
            break
        if len(ids)>1:
            for pos,a in enumerate(ids):
                for b in ids[pos+1:]:
                    if len(pairs) >= max_pairs:
                        break
                    pairs.add((a,b))
                if len(pairs) >= max_pairs:
                    break
    for ids in index.values():
        # Deterministic upper bound: no pairwise n^2 scan on huge datasets.
        if len(ids)>2000:
            continue
        for pos,a in enumerate(ids):
            for b in ids[pos+1:]:
                if len(pairs) >= max_pairs:break
                pairs.add((a,b))
            if len(pairs) >= max_pairs:break
        if len(pairs) >= max_pairs:break
    results=[]
    for a,b in sorted(pairs):
        x,y=ds[a],ds[b]
        vx,vy=vectors[a],vectors[b]
        shared=set(vx)&set(vy)
        cos=sum(vx[t]*vy[t] for t in shared)/(norms[a]*norms[b])
        shared_tactics=sorted(set(x.tactics)&set(y.tactics))
        syntactic=fingerprints[a]==fingerprints[b] and bool(comparison_text(x).strip())
        if cos>=min_score or syntactic or len(shared_tactics)>=2:
            results.append({"from":x.id,"to":y.id,"tfidf_cosine":round(cos,4),
                "same_syntax_fingerprint":syntactic,"shared_tactics":shared_tactics,
                "shared_symbols":sorted(shared,key=lambda t:-(df[t] and (math.log((n+1)/(df[t]+1))+1)))[:12],
                "interpretation":"syntactic-candidate-only"})
    results.sort(key=lambda r:(not r["same_syntax_fingerprint"],-r["tfidf_cosine"],-len(r["shared_tactics"]),r["from"],r["to"]))
    return results, {"potential_pairs_examined":len(pairs),"pair_cap":max_pairs,"cap_reached":len(pairs)>=max_pairs}




def graph_summaries(ds: list[D], links: list[tuple], entry_names: list[str] | None = None):
    """Graph metrics on candidate name matches, NOT an elaborated proof graph."""
    by_id={d.id:d for d in ds}
    adjacency=defaultdict(set)
    for src,dst,*_ in links:
        adjacency[src].add(dst)
    n=len(ds)
    # Simple PageRank with 15 fixed iterations, edges from consumer to dependency.
    ranks={d.id:1/n for d in ds}
    for _ in range(15):
        next_rank={d.id:0.15/n for d in ds}
        dangling=sum(ranks[k] for k in ranks if not adjacency[k])/n
        for k in next_rank:
            next_rank[k]+=0.85*dangling
        for src,targets in adjacency.items():
            for dst in targets:
                next_rank[dst]+=0.85*ranks[src]/len(targets)
        ranks=next_rank
    # Generic entry points: caller-provided names or first available theorems.
    if entry_names:
        wanted=set(entry_names)
        root_ids=[d.id for d in ds if d.name in wanted or d.short_name in wanted]
    else:
        root_ids=[d.id for d in ds if d.kind in ('theorem','lemma')][:5]
    routes=[]
    for rid in root_ids:
        seen={rid}
        frontier=[(rid,0)]
        result=[]
        while frontier:
            node,depth=frontier.pop(0)
            result.append({'id':node,'name':by_id[node].name,'depth':depth,'url':by_id[node].source_url})
            if depth>=6:continue
            for nxt in sorted(adjacency[node]):
                if nxt not in seen:
                    seen.add(nxt);frontier.append((nxt,depth+1))
        routes.append({'root':rid,'nodes':result,'limited_to_imported_sample':True})
    sizes=[len(comparison_text(d)) for d in ds]
    center=median(sizes) if sizes else 0
    mad=median(abs(x-center) for x in sizes) if sizes else 0
    outliers=[]
    for d,size in zip(ds,sizes):
        z=0 if mad==0 else 0.6745*(size-center)/mad
        if z>3.5:outliers.append({'id':d.id,'source_url':d.source_url,'characters':size,'robust_z':round(z,2)})
    return {'page_rank_top':[
        {'name':by_id[i].name,'id':i,'score':round(ranks[i],6),'source_url':by_id[i].source_url}
        for i in sorted(ranks,key=lambda k:(-ranks[k],k))[:15]],
        'routes_from_main':routes, 'long_statement_outliers':outliers,
        'statement_length_median':center,'statement_length_MAD':mad,
        'notes':['PageRank follows lexical candidate links, not formal proof dependency.',
                 'Outliers are long statements, not suspicious proofs.',
                 'Routes stop at unavailable source files.']}

def public_record(d:D):
    # Public reports are navigation metadata, not a reproduction of the
    # unlicensed original Lean corpus. Full source stays at pinned URLs.
    result=asdict(d)
    result["statement"]=result["statement"][:180]
    result["body"]=result["body"][:70]
    return result


def write_csv(path,items,fields):
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader();w.writerows(items)


def analyze(root:Path, out:Path, repo:str, commit:str, expected:dict|None=None, max_pairs:int=100000, min_score:float=.78, entry_names:list[str]|None=None, source_prefix:str=""):
    root=root.resolve();out.mkdir(parents=True,exist_ok=True)
    files=sorted(x for x in root.rglob("*.lean") if ".lake" not in x.parts and ".git" not in x.parts)
    if not files:raise ValueError("No Lean .lean files under input root")
    if max_pairs < 0:
        raise ValueError("max_pairs must be >= 0")
    if not 0 <= min_score <= 1:
        raise ValueError("min_score must be in [0, 1]")
    if expected is not None:
        observed={f.relative_to(root).as_posix() for f in files}
        missing=set(expected)-observed
        extra=observed-set(expected)
        if missing or extra:
            raise ValueError(f"SOURCE MANIFEST INCOMPLETE: missing={sorted(missing)} extra={sorted(extra)}")
    if len(files)>5000:raise ValueError("Pilot mode supports at most 5000 files; use a smaller subtree. Full-archive streaming analysis is not implemented.")
    ds=[]; module_imports={};provenance=[]
    if source_prefix and (source_prefix.startswith("/") or ".." in Path(source_prefix).parts):
        raise ValueError("Unsafe source_prefix")
    source_prefix = source_prefix.strip("/")
    base=f"https://github.com/{repo}/blob/{commit}"
    if source_prefix:
        base += "/" + source_prefix
    for file in files:
        dd,imports,info=scan_file(file,root,base)
        if expected is not None:
            if info["path"] not in expected:
                raise ValueError(f"SOURCE NOT IN MANIFEST: {info['path']}")
            if expected[info["path"]] != info["git_blob_sha1"]:
                raise ValueError(f"SOURCE HASH MISMATCH: {info['path']}: actual={info['git_blob_sha1']}, expected={expected[info['path']]}")
        ds.extend(dd);provenance.append(info)
        module_imports[info["path"]]=imports
    ds.sort(key=lambda d:(d.path,d.line,d.id))
    if not ds:raise ValueError("No supported declarations found in Lean source input")
    edges=match_deps(ds)
    sims,sim_meta=similarities(ds,max_pairs=max_pairs,min_score=min_score)
    graph=graph_summaries(ds,edges,entry_names=entry_names)
    type_counts=Counter(d.kind for d in ds)
    tf=Counter(t for d in ds for t in d.tactics)
    incoming=Counter(dst for _,dst,*_ in edges)
    outgoing=Counter(src for src,*_ in edges)
    module_paths={f.removesuffix(".lean").removeprefix("src/").replace("/","."):f for f in module_imports}
    module_edges=[]
    for f,imps in module_imports.items():
        for m in imps:
            if m in module_paths:
                module_edges.append({"from":f,"to":module_paths[m],"evidence":"explicit-import"})
    duplicates={n:[d.id for d in ds if d.name==n] for n,count in Counter(d.name for d in ds).items() if count>1}
    report={"schema":"lean-atlas-v0.1","mode":"source-only-unelaborated","not_proof_check":True,
        "provenance":{"repository":repo,"commit":commit,"files":provenance,"source_hashes_checked":expected is not None,"manifest_complete":expected is not None},
        "summary":{"files":len(files),"lines":sum(x["lines"] for x in provenance),"declarations":len(ds),
                   "kinds":dict(type_counts),"explicit_import_edges_in_sample":len(module_edges),
                   "candidate_declaration_links":len(edges),"candidate_similar_pairs":len(sims),
                   "similarity_search":sim_meta,"duplicate_full_names":duplicates,
                   "declarations_with_tactic":dict(tf.most_common(30))},
        "declarations":[public_record(d)|{"referenced_by_in_sample":incoming[d.id],"references_in_sample":outgoing[d.id]} for d in ds],
        "candidate_links":[dict(zip(["from","to","role","resolution","evidence_token"],e)) for e in edges],
        "import_links":module_edges,"similarity_candidates":sims,
        "graph_navigation":graph}
    (out/"analysis.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    write_csv(out/"index.csv", [public_record(d)|{"referenced_by":incoming[d.id],"references":outgoing[d.id]} for d in ds],
              ["id","name","kind","path","line","end_line","source_url","statement","body","statement_fp","referenced_by","references"])
    write_csv(out/"candidate_links.csv",report["candidate_links"],["from","to","role","resolution","evidence_token"])
    write_csv(out/"similarity.csv", [{k:(";".join(v) if isinstance(v,list) else v) for k,v in row.items()} for row in sims],
              ["from","to","tfidf_cosine","same_syntax_fingerprint","shared_tactics","shared_symbols","interpretation"])
    write_csv(out/"imports.csv",module_edges,["from","to","evidence"])
    # DOT is useful without graphviz; quote identifiers via JSON escaping.
    dot=["digraph LeanAtlas {", "  rankdir=LR;", "  node [shape=box, fontsize=10];"]
    for d in ds:
        node_label = d.short_name + "\n" + d.path
        dot.append(f"  {json.dumps(d.id,ensure_ascii=False)} [label={json.dumps(node_label,ensure_ascii=False)}];")
    for src,dst,role,res,token in edges:
        dot.append(f"  {json.dumps(src,ensure_ascii=False)} -> {json.dumps(dst,ensure_ascii=False)} [label={json.dumps(role,ensure_ascii=False)}];")
    dot.append("}")
    (out/"candidate_deps.dot").write_text("\n".join(dot)+"\n",encoding="utf-8")
    ranked=sorted(ds,key=lambda d:(-incoming[d.id],d.path,d.line))
    lines=["# Lean source-level navigation report", "", "> **Not a proof check.** Dependencies and similarities are lexical candidates, not Lean-elaborated facts or mathematical equivalences.",
          "",f"- Repository: `{repo}`",f"- Pinned commit: `{commit}`",f"- Files analyzed: **{len(files)}**",f"- Lines analyzed: **{sum(x['lines'] for x in provenance):,}**",f"- Declarations found: **{len(ds)}**",
          f"- In-sample import edges: **{len(module_edges)}**",f"- Candidate declaration links: **{len(edges)}**",f"- Similarity candidates: **{len(sims)}**", "",
          "## Most referenced declarations in this sample", "", "| Declaration | References from within sample | Source |", "|---|---:|---|"]
    for d in ranked[:20]:
        lines.append(f"| `{d.name}` | {incoming[d.id]} | [source]({d.source_url}) |")
    lines += ["","## Similarity candidates (not claims of equivalence)","", "| Pair | TF-IDF cosine | Same source syntax | Shared tactics |", "|---|---:|---|---|"]
    by_id={d.id:d for d in ds}
    for p in sims[:30]:
        x,y=by_id[p["from"]],by_id[p["to"]]
        lines.append(f"| [{x.name}]({x.source_url}) / [{y.name}]({y.source_url}) | {p['tfidf_cosine']:.3f} | {'yes' if p['same_syntax_fingerprint'] else 'no'} | {', '.join(p['shared_tactics']) or '-'} |")
    lines += ["","## File provenance", "", "| Input | Git blob SHA-1 |", "|---|---|"]
    for p in provenance:
        lines.append(f"| `{p['path']}` | `{p['git_blob_sha1']}` |")
    lines += ["", "## Reading guide", "", "1. Begin at the selected entry points; follow the candidate name references.",
              "2. Use `candidate_links.csv` to trace only names present in the current sample; unresolved references may exist outside the sample.",
              "3. Read `similarity.csv` as suggestions for side-by-side source comparison; no mathematical relationship is asserted.",
              "4. For authoritative dependencies, run a Lean environment/elaboration-based extractor on the pinned source; this tool does not do that.",""]
    (out/"REPORT.md").write_text("\n".join(lines),encoding="utf-8")
    # Human-first minimal index: groups that share exact normalized source syntax,
    # plus the entry points from Main. No summary is invented by a language model.
    groups=defaultdict(list)
    for d in ds:
        fp=hashlib.sha256(normalized_expression(comparison_text(d)).encode()).hexdigest()
        groups[fp].append(d)
    repeated=sorted((v for v in groups.values() if len(v)>=2),key=lambda g:(-len(g),g[0].name))
    overview=["# Minimal review index — source-level pilot", "",
        "> This is a map for a human reader, not an assertion of theorem equivalence or proof correctness.", "",
        f"Pinned upstream: `{repo}` at `{commit}`. Sample: **{len(files)} files**, **{len(ds)} declarations**.", "",
        "## Selected theorem entry points", ""]
    for route in graph["routes_from_main"]:
        root_decl=by_id[route["root"]]
        overview.append(f"- [{root_decl.name}]({root_decl.source_url}) — {len(route['nodes'])} named declarations reachable within the sample (including itself)")
    overview += ["", "## Repeated normalized source syntax (not a Lean equivalence claim)", ""]
    for group in repeated[:12]:
        overview.append(f"**{len(group)} declarations share a syntax fingerprint:**")
        for d in group:
            overview.append(f"- [`{d.name}`]({d.source_url})")
    overview += ["", "## Suggested navigation", "",
        "1. Open one of the selected entry theorems and follow candidate references in `REPORT.md`.",
        "2. Compare the repeated source-syntax group against pinned Lean source.",
        "3. Consult `candidate_links.csv` and `similarity.csv` for additional comparison candidates.",
        "4. Record a human explanation only after reading the original definitions and proofs.", ""]
    (out/"OVERVIEW.md").write_text("\n".join(overview),encoding="utf-8")
    return report


def main():
    ap=argparse.ArgumentParser(description="Lean 4 source navigator (not a proof checker)")
    ap.add_argument("input",type=Path,help="Root directory containing Lean .lean files")
    ap.add_argument("--out",type=Path,default=Path("reports/latest"))
    ap.add_argument("--repo",default="leanprover-community/riemann-hypothesis")
    ap.add_argument("--commit",required=True,help="Immutable Git commit SHA of source")
    ap.add_argument("--expected-manifest",type=Path,help="JSON mapping relative .lean paths to Git blob SHA-1 values")
    ap.add_argument("--max-pairs",type=int,default=100_000)
    ap.add_argument("--min-similarity",type=float,default=.78)
    ap.add_argument("--entry",action="append",default=[],help="Entry theorem name; repeatable")
    ap.add_argument("--source-prefix",default="",help="Input directory's path inside the GitHub repo")
    args=ap.parse_args()
    try:
        expected=json.loads(args.expected_manifest.read_text(encoding="utf-8")) if args.expected_manifest else None
        result=analyze(args.input,args.out,args.repo,args.commit,expected,max_pairs=args.max_pairs,min_score=args.min_similarity,entry_names=args.entry,source_prefix=args.source_prefix)
    except (OSError,ValueError) as e:
        ap.exit(2,f"Error: {e}\n")
    print(json.dumps(result["summary"],ensure_ascii=False,indent=2))
    print(f"Generated: {args.out.resolve()}")

if __name__=="__main__":main()
