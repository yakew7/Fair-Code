"""Render a ProfileResult to terminal text, JSON, or a standalone HTML report.

`report.py` is the only module that formats results, so terminal/JSON/HTML stay
in sync. Terminal output follows the existing audit aesthetic (``"=" * 60``
section banners, percentage formatting) so it feels native to the project.
"""

from __future__ import annotations

import html
import json

WIDTH = 62
DISPLAY_GROUPS = 12  # cap rows shown per dimension; full data stays in the result


def to_json(result: dict, indent: int = 2, provenance: dict | None = None) -> str:
    """Serialise a profile or compare result.

    `provenance`, when supplied, is attached as a top-level "provenance" key
    (SPEC section 10) so an exported report says which file, which faircode
    version, and which resolved thresholds produced it. It is attached here
    rather than inside profile() on purpose: the Python engine and the JS port
    are compared with `==` in tests/test_js_parity.py, so a local file name
    cannot live in the engine result. The web export mirrors the same field
    names at the same boundary.

    The result dict is not mutated - callers still print the terminal or HTML
    rendering from the same object afterwards.
    """
    if provenance is None:
        return json.dumps(result, indent=indent)
    return json.dumps(dict(result, provenance=provenance), indent=indent)


def _bar(share: float, width: int = 24) -> str:
    filled = round(share * width)
    return "█" * filled + "·" * (width - filled)


def to_terminal(result: dict) -> str:
    lines: list[str] = []
    add = lines.append

    add("=" * WIDTH)
    add("FAIR CODE - DATASET REPRESENTATION PROFILE")
    add("=" * WIDTH)
    add("")
    add(f"  Rows: {result['n_rows']:,}    Columns: {result['n_cols']}")
    if result["overall_score"] is None:
        add("  Representation score: not measured")
    else:
        add(f"  Representation score: {result['overall_score']}/100  "
            f"(Grade {result['grade']})")
    add("")

    if not result["dimensions"]:
        add(f"  {result['note']}")
        add("=" * WIDTH)
        return "\n".join(lines)

    for d in result["dimensions"]:
        add("-" * WIDTH)
        title = f"{d['name']}  [{d['kind']}]"
        add(f"{title}    score {d['dimension_score']}/100")
        add("-" * WIDTH)
        shown = d["groups"][:DISPLAY_GROUPS]
        for g in shown:
            mark = "  <- under-represented" if g["label"] in d["under_represented"] else ""
            warning = ("  ⚠ small group (metric may be unreliable)" if g.get("small_group") else "")
            ci = ""
            if g.get("ci_low") is not None and g.get("ci_high") is not None:
                ci = f"  [95% CI {g['ci_low'] * 100:.1f}-{g['ci_high'] * 100:.1f}%]"
            add(f"  {g['label'][:18]:<18} {_bar(g['share'])} "
                f"{g['share'] * 100:5.1f}%  (n={g['count']:,}){ci}{mark}{warning}")
        if len(d["groups"]) > DISPLAY_GROUPS:
            add(f"  … and {len(d['groups']) - DISPLAY_GROUPS} more groups")
        meta = []
        if d["imbalance_ratio"] is not None:
            meta.append(f"imbalance {d['imbalance_ratio']:.1f}x")
        elif d["n_groups"] > 1:
            meta.append("imbalance inf (empty subgroup)")
        if d["missing_pct"] > 0:
            meta.append(f"missing {d['missing_pct'] * 100:.1f}%")
        if d["skewness"] is not None:
            meta.append(f"skew {d['skewness']:+.2f}")
        if meta:
            add(f"  ({'  '.join(meta)})")
        if d.get("reference"):
            add(f"  reference (deviation {d['reference']['deviation'] * 100:.1f}%):")
            for g in d["reference"]["groups"][:DISPLAY_GROUPS]:
                add(f"    {g['label'][:16]:<16} exp {g['expected'] * 100:5.1f}%  "
                    f"act {g['actual'] * 100:5.1f}%  ({g['delta'] * 100:+5.1f} pp)")
        add("")

    if result["flags"]:
        add("=" * WIDTH)
        add("FLAGS")
        add("=" * WIDTH)
        for f in result["flags"]:
            add(f"  ! {f}")
        add("")

    if result.get("proxy_hints"):
        add("=" * WIDTH)
        add("PROXY HINTS  (chi-squared association, informational)")
        add("=" * WIDTH)
        for h in result["proxy_hints"]:
            add(f"  ~ {h['a']} ↔ {h['b']}  "
                f"(χ² p={h['p_value']:.4g}, Cramér's V={h['cramers_v']:.2f})")
        add("")

    add("=" * WIDTH)
    return "\n".join(lines)


def _delta(n: int | None) -> str:
    return "not available" if n is None else f"{n:+d}"


def _dataset_score_line(dataset: dict) -> str:
    if dataset["overall_score"] is None:
        return f"{dataset['n_rows']:,} rows · score not measured"
    return (f"{dataset['n_rows']:,} rows · score {dataset['overall_score']}/100 "
            f"(Grade {dataset['grade']})")


def compare_to_terminal(cmp: dict) -> str:
    """Render a compare() result (SPEC section 8) as terminal text."""
    lines: list[str] = []
    add = lines.append
    a, b = cmp["a"], cmp["b"]

    add("=" * WIDTH)
    add("FAIR CODE - REPRESENTATION DRIFT  (A → B)")
    add("=" * WIDTH)
    add("")
    add(f"  A  {a['name']}")
    add(f"     {_dataset_score_line(a)}")
    add(f"  B  {b['name']}")
    add(f"     {_dataset_score_line(b)}")
    delta_suffix = "" if cmp["score_delta"] is None else " points"
    add(f"  Overall score change: {_delta(cmp['score_delta'])}{delta_suffix}")
    add("")

    if not cmp["dimensions"]:
        add("  No shared demographic dimensions to compare.")
    for cd in cmp["dimensions"]:
        add("-" * WIDTH)
        add(f"{cd['name']}  [{cd['kind']}]    PSI {cd['psi']:.3f}  "
            f"({cd['drift_level']} drift)")
        add(f"  score {cd['dimension_score_a']} → {cd['dimension_score_b']} "
            f"({_delta(cd['dimension_score_delta'])})    TVD {cd['tvd']:.3f}")
        add("-" * WIDTH)
        for g in cd["groups"][:DISPLAY_GROUPS]:
            tag = {"appeared": "  (appeared)", "disappeared": "  (disappeared)",
                   "shifted": ""}[g["status"]]
            add(f"  {g['label'][:18]:<18} {g['share_a'] * 100:5.1f}% → "
                f"{g['share_b'] * 100:5.1f}%  ({g['share_delta'] * 100:+5.1f} pp){tag}")
        if len(cd["groups"]) > DISPLAY_GROUPS:
            add(f"  … and {len(cd['groups']) - DISPLAY_GROUPS} more groups")
        add("")

    if cmp["added_dimensions"]:
        add(f"  Only in B: {', '.join(cmp['added_dimensions'])}")
    if cmp["removed_dimensions"]:
        add(f"  Only in A: {', '.join(cmp['removed_dimensions'])}")
    if cmp["added_dimensions"] or cmp["removed_dimensions"]:
        add("")

    for key, label in (("proxy_hints_a", "A"), ("proxy_hints_b", "B")):
        if cmp.get(key):
            add("=" * WIDTH)
            add(f"PROXY HINTS - {label}  (chi-squared association, informational)")
            add("=" * WIDTH)
            for h in cmp[key]:
                add(f"  ~ {h['a']} ↔ {h['b']}  "
                    f"(χ² p={h['p_value']:.4g}, Cramér's V={h['cramers_v']:.2f})")
            add("")

    if cmp["flags"]:
        add("=" * WIDTH)
        add("DRIFT FLAGS")
        add("=" * WIDTH)
        for f in cmp["flags"]:
            add(f"  ! {f}")
        add("")

    add("=" * WIDTH)
    return "\n".join(lines)


def to_html(result: dict) -> str:
    """A self-contained HTML report echoing the 'Audit Ledger' palette."""
    def esc(s) -> str:
        return html.escape(str(s))

    dim_blocks = []
    for d in result["dimensions"]:
        rows = []
        for g in d["groups"][:DISPLAY_GROUPS]:
            classes = []
            if g["label"] in d["under_represented"]:
                classes.append("under")
            if g.get("small_group"):
                classes.append("small-group")
            ci = ""
            if g.get("ci_low") is not None and g.get("ci_high") is not None:
                ci = f'{g["ci_low"] * 100:.1f}–{g["ci_high"] * 100:.1f}%'
            rows.append(
                f'<tr class="{" ".join(classes)}"><td>{esc(g["label"])}</td>'
                f'<td class="num">{g["share"] * 100:.1f}%</td>'
                f'<td class="num ci">{ci}</td>'
                f'<td class="num">{g["count"]:,}</td>'
                f'<td class="bar"><span style="width:{g["share"] * 100:.1f}%"></span></td></tr>'
            )
        reference_html = ""
        if d.get("reference"):
            ref = d["reference"]
            ref_rows = "".join(
                f'<tr><td>{esc(g["label"])}</td>'
                f'<td class="num">{g["expected"] * 100:.1f}%</td>'
                f'<td class="num">{g["actual"] * 100:.1f}%</td>'
                f'<td class="num">{g["delta"] * 100:+.1f} pp</td></tr>'
                for g in ref["groups"][:DISPLAY_GROUPS]
            )
            reference_html = (
                f'<div class="reference"><h3>Reference '
                f'<span class="kind">deviation {ref["deviation"] * 100:.1f}%</span></h3>'
                f'<table><caption>Expected vs. actual share - {esc(d["name"])}</caption>'
                f'<tr><th scope="col"></th><th scope="col" class="num">Expected</th>'
                f'<th scope="col" class="num">Actual</th><th scope="col" class="num">Delta</th></tr>'
                f'{ref_rows}</table></div>'
            )

        meta_parts = []
        if d["imbalance_ratio"] is not None:
            meta_parts.append(f"imbalance {d['imbalance_ratio']:.1f}x")
        elif d["n_groups"] > 1:
            meta_parts.append("imbalance inf (empty subgroup)")
        if d["missing_pct"] > 0:
            meta_parts.append(f"missing {d['missing_pct'] * 100:.1f}%")
        if d["skewness"] is not None:
            meta_parts.append(f"skew {d['skewness']:+.2f}")
        meta_html = (
            f' <span class="meta">({esc("  ".join(meta_parts))})</span>'
            if meta_parts else ""
        )

        dim_blocks.append(
            f'<section class="dim"><h2>{esc(d["name"])} '
            f'<span class="kind">{esc(d["kind"])}</span> '
            f'<span class="score">{d["dimension_score"]}/100</span>{meta_html}</h2>'
            f'<table><caption>Group breakdown - {esc(d["name"])}</caption>'
            f'<thead><tr><th scope="col">Group</th><th scope="col" class="num">Share</th>'
            f'<th scope="col" class="num">95% CI</th><th scope="col" class="num">Count</th>'
            f'<th scope="col" class="bar"></th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>{reference_html}</section>'
        )

    flag_html = ""
    if result["flags"]:
        items = "".join(f"<li>{esc(f)}</li>" for f in result["flags"])
        flag_html = f'<section class="flags"><h2>Flags</h2><ul>{items}</ul></section>'

    proxy_html = ""
    if result.get("proxy_hints"):
        items = "".join(
            f'<li>{esc(h["a"])} ↔ {esc(h["b"])} '
            f'(χ² p={h["p_value"]:.4g}, Cramér\'s V={h["cramers_v"]:.2f})</li>'
            for h in result["proxy_hints"]
        )
        proxy_html = (
            '<section class="flags"><h2>Proxy Hints '
            '<span class="kind">chi-squared association, informational</span></h2>'
            f'<ul>{items}</ul></section>'
        )

    if result["overall_score"] is None:
        score_html = "<strong>Not measured</strong> (no demographic columns detected)"
    else:
        score_html = (f"<strong>{result['overall_score']}/100</strong> "
                      f"(Grade {result['grade']})")

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Fair Code - Dataset Profile</title>
<style>
 :root {{ --bg:#f4f1e8; --surface:#ebe7d9; --border:#d9d3c0; --accent:#a63a22;
          --accent3:#2f6b4f; --text:#36321f; --muted:#7d7459; }}
 body {{ font-family:'Helvetica Neue',sans-serif; background:var(--bg); color:var(--text);
         max-width:820px; margin:0 auto; padding:48px 24px; }}
 h1 {{ font-family:Georgia,serif; }}
 .score {{ color:var(--accent3); font-size:.7em; font-weight:600; }}
 .kind {{ color:var(--muted); font-size:.6em; text-transform:uppercase; letter-spacing:.08em; }}
 .meta {{ color:var(--muted); font-size:.6em; }}
 .dim {{ background:var(--surface); border:1px solid var(--border); border-radius:8px;
         padding:16px 20px; margin:16px 0; }}
 table {{ width:100%; border-collapse:collapse; }}
 caption {{ text-align:left; font-size:11px; color:var(--muted); text-transform:uppercase;
            letter-spacing:.04em; margin-bottom:4px; }}
 th {{ padding:4px 8px; font-size:14px; font-weight:600; text-align:left;
       border-bottom:2px solid var(--border); }}
 th.num {{ text-align:right; }}
 td {{ padding:4px 8px; font-size:14px; border-bottom:1px solid var(--border); }}
 td.num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
 td.ci {{ color:var(--muted); font-size:12px; }}
 td.bar {{ width:40%; }}
 td.bar span {{ display:block; height:10px; background:var(--accent3); border-radius:3px; }}
 tr.under td.bar span {{ background:var(--accent); }}
 tr.under td:first-child::after {{ content:' (under-represented)'; color:var(--accent); font-size:11px; }}
 tr.small-group td:first-child::before {{content:'⚠ small group ';color:var(--accent);}}
 .reference {{ margin-top:10px; padding-top:10px; border-top:1px dashed var(--border); }}
 .reference h3 {{ font-size:.75em; margin:0 0 6px; }}
 .reference th {{ text-align:right; font-size:11px; color:var(--muted); font-weight:normal; }}
 .reference th:first-child {{ text-align:left; }}
 .flags ul {{ list-style:none; padding:0; }}
 .flags li {{ background:#fbeae3; border-left:3px solid var(--accent); padding:8px 12px; margin:6px 0; border-radius:0 4px 4px 0; }}
 .head {{ border-bottom:2px solid var(--accent); padding-bottom:12px; }}
 .print-btn {{ position:fixed; top:16px; right:16px; background:var(--accent); color:#fff;
               border:0; border-radius:6px; padding:8px 14px; font-size:13px; cursor:pointer;
               font-family:inherit; }}
 @media print {{ .print-btn {{ display:none; }} body {{ padding:24px; max-width:none; }} }}
</style></head><body>
<button class="print-btn" onclick="window.print()">🖨 Print / Save as PDF</button>
<div class="head"><h1>Dataset Representation Profile</h1>
<p>{result['n_rows']:,} rows · {result['n_cols']} columns · Score {score_html}</p></div>
{"".join(dim_blocks)}
{flag_html}
{proxy_html}
<p style="color:var(--muted);font-size:12px;margin-top:32px">
Generated by <a href="https://github.com/yakew7/Fair-Code">Fair Code</a> - diagnostic only.</p>
</body></html>"""
def compare_to_html(cmp: dict) -> str:
    """A self-contained HTML report displaying representation drift between datasets A and B."""

    def esc(s) -> str:
        return html.escape(str(s))

    def signed(val: float | int, dp: int = 1) -> str:
        prefix = "+" if val > 0 else ""
        return f"{prefix}{val:.{dp}f}"

    # Summary Header
    a, b = cmp["a"], cmp["b"]
    score_delta = cmp["score_delta"]
    delta_class = ("flat" if score_delta is None else
                   "up" if score_delta > 0 else "down" if score_delta < 0 else "flat")
    arrow = "?" if score_delta is None else "=" if score_delta == 0 else "→"

    def score_summary(dataset: dict) -> tuple[str, str]:
        if dataset["overall_score"] is None:
            return "N/A", f'{esc(dataset["name"])} ({dataset["n_rows"]:,} rows, not measured)'
        return (str(dataset["overall_score"]),
                f'{esc(dataset["name"])} ({dataset["n_rows"]:,} rows, Grade {dataset["grade"]})')

    score_a, label_a = score_summary(a)
    score_b, label_b = score_summary(b)
    delta_label = ("score change not available" if score_delta is None
                   else f"score {signed(score_delta, 0)} pts")

    summary_html = (
        '<div class="drift-summary">'
        f'<div class="drift-score"><span class="n">{score_a}</span><span class="l">{label_a}</span></div>'
        f'<div class="drift-arrow" aria-hidden="true">{arrow}</div>'
        f'<div class="drift-score"><span class="n">{score_b}</span><span class="l">{label_b}</span></div>'
        f'<div class="drift-delta {delta_class}">{delta_label}</div>'
        '</div>'
    )

    # Dimension Cards
    cards_html = []
    if not cmp["dimensions"]:
        cards_html.append(
            '<p class="section-note">No demographic dimension is present in both datasets to compare.</p>'
        )
    else:
        for cd in cmp["dimensions"]:
            max_share = max(
                (max(g["share_a"], g["share_b"]) for g in cd["groups"]), default=1.0
            )
            if max_share <= 0:
                max_share = 1.0

            rows = []
            for g in cd["groups"][:DISPLAY_GROUPS]:
                cls = (
                    " gone"
                    if g["status"] == "disappeared"
                    else (" new" if g["status"] == "appeared" else "")
                )
                wa = (g["share_a"] / max_share) * 100
                wb = (g["share_b"] / max_share) * 100
                delta_pp = g["share_delta"] * 100
                d_cls = "up" if delta_pp > 0 else ("down" if delta_pp < 0 else "")

                tag = (
                    f' <span class="tag">{esc(g["status"])}</span>'
                    if g["status"] in ("appeared", "disappeared")
                    else ""
                )

                rows.append(
                    f'<tr class="drift-row{cls}">'
                    f'<td class="label">{esc(g["label"])}{tag}</td>'
                    f'<td class="num">{g["share_a"] * 100:.1f}% → {g["share_b"] * 100:.1f}%</td>'
                    f'<td class="num"><span class="{d_cls}">{signed(delta_pp)} pp</span></td>'
                    f'<td class="bar">'
                    f'<div class="bar-container">'
                    f'<span class="bar-a" style="width:{wa:.1f}%"></span>'
                    f'<span class="bar-b" style="width:{wb:.1f}%"></span>'
                    f'</div>'
                    f'</td>'
                    f'</tr>'
                )

            more_html = ""
            if len(cd["groups"]) > DISPLAY_GROUPS:
                more_html = f'<div class="dim-more">… and {len(cd["groups"]) - DISPLAY_GROUPS} more groups</div>'

            cards_html.append(
                '<section class="drift-card">'
                '<div class="drift-card-head">'
                f'<h2>{esc(cd["name"])} <span class="kind">{esc(cd["kind"])}</span> '
                f'<span class="drift-badge {cd["drift_level"]}">{esc(cd["drift_level"])} drift</span></h2>'
                f'<div class="drift-metrics">PSI {cd["psi"]:.3f} · TVD {cd["tvd"]:.3f} · score {cd["dimension_score_a"]}→{cd["dimension_score_b"]} ({signed(cd["dimension_score_delta"], 0)})</div>'
                '</div>'
                f'<table><caption>Group-level share drift - {esc(cd["name"])}</caption>'
                f'<thead><tr><th scope="col">Group</th><th scope="col" class="num">Share A → B</th>'
                f'<th scope="col" class="num">Δ</th><th scope="col" class="bar"></th></tr></thead>'
                f'<tbody>{"".join(rows)}</tbody></table>'
                f'{more_html}'
                '</section>'
            )

    # Flags Block
    flags_html = ""
    if cmp["flags"]:
        items = "".join(f"<li>{esc(f)}</li>" for f in cmp["flags"])
        flags_html = f'<section class="flags"><h2>Drift Flags</h2><ul>{items}</ul></section>'

    # Proxy Hints (A/B)
    proxy_html = ""
    for key, label in (("proxy_hints_a", "A"), ("proxy_hints_b", "B")):
        if cmp.get(key):
            items = "".join(
                f'<li>{esc(h["a"])} ↔ {esc(h["b"])} '
                f'(χ² p={h["p_value"]:.4g}, Cramér\'s V={h["cramers_v"]:.2f})</li>'
                for h in cmp[key]
            )
            proxy_html += (
                f'<section class="flags"><h2>Proxy Hints - {label} '
                '<span class="kind">chi-squared association, informational</span></h2>'
                f'<ul>{items}</ul></section>'
            )

    # Dimensions missing/added info
    only_html = ""
    if cmp["added_dimensions"]:
        only_html += f'<div class="drift-only">Only in B ({esc(b["name"])}): <strong>{", ".join(map(esc, cmp["added_dimensions"]))}</strong></div>'
    if cmp["removed_dimensions"]:
        only_html += f'<div class="drift-only">Only in A ({esc(a["name"])}): <strong>{", ".join(map(esc, cmp["removed_dimensions"]))}</strong></div>'

    style = (
        ":root { --bg:#f4f1e8; --surface:#ebe7d9; --border:#d9d3c0; --accent:#a63a22; "
        "--accent3:#2f6b4f; --warn:#b8860b; --text:#36321f; --muted:#7d7459; --bar-a:#7d7459; --bar-b:#2f6b4f; } "
        "body { font-family:'Helvetica Neue',sans-serif; background:var(--bg); color:var(--text); "
        "max-width:820px; margin:0 auto; padding:48px 24px; } "
        "h1 { font-family:Georgia,serif; margin-bottom:8px; } "
        ".head { border-bottom:2px solid var(--accent); padding-bottom:12px; margin-bottom:20px; } "
        ".drift-summary { display:flex; align-items:center; justify-content:space-between; background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:16px; margin-bottom:20px; } "
        ".drift-score { font-weight:bold; font-size:14px; display:flex; flex-direction:column; } "
        ".drift-score .n { font-size:24px; color:var(--accent3); } "
        ".drift-score .l { font-size:12px; color:var(--muted); font-weight:normal; } "
        ".drift-arrow { font-size:20px; color:var(--muted); } "
        ".drift-delta { font-weight:bold; padding:4px 8px; border-radius:4px; font-size:14px; } "
        ".drift-delta.down { color:var(--accent); background:#fbeae3; } "
        ".drift-delta.up { color:var(--accent3); background:#e2f0e8; } "
        ".drift-delta.flat { color:var(--muted); } "
        ".kind { color:var(--muted); font-size:.6em; text-transform:uppercase; letter-spacing:.08em; font-weight:normal; } "
        ".drift-badge { font-size:11px; padding:2px 6px; border-radius:4px; text-transform:uppercase; font-weight:bold; background:var(--border); margin-left:8px; } "
        ".drift-badge.none { background:var(--accent3); color:#fff; } "
        ".drift-badge.moderate { background:var(--warn); color:#fff; } "
        ".drift-badge.significant { background:var(--accent); color:#fff; } "
        ".drift-card { background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:16px 20px; margin:16px 0; } "
        ".drift-card-head { display:flex; justify-content:space-between; align-items:baseline; border-bottom:1px solid var(--border); padding-bottom:8px; margin-bottom:12px; } "
        ".drift-card-head h2 { margin:0; font-size:18px; } "
        ".drift-metrics { font-size:12px; color:var(--muted); } "
        "table { width:100%; border-collapse:collapse; } "
        "caption { text-align:left; font-size:11px; color:var(--muted); text-transform:uppercase; "
        "letter-spacing:.04em; margin-bottom:4px; } "
        "th { padding:6px 8px; font-size:14px; font-weight:600; text-align:left; "
        "border-bottom:2px solid var(--border); } "
        "th.num { text-align:right; } "
        "td { padding:6px 8px; font-size:14px; border-bottom:1px solid var(--border); } "
        "td.num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; font-size:13px; } "
        "td.label { width:25%; } "
        "td.bar { width:40%; } "
        ".bar-container { display:flex; flex-direction:column; gap:3px; } "
        ".bar-a { display:block; height:6px; background:var(--bar-a); border-radius:2px; opacity:0.6; } "
        ".bar-b { display:block; height:6px; background:var(--bar-b); border-radius:2px; } "
        "tr.gone td.label { color:var(--accent); text-decoration:line-through; } "
        "tr.new td.label { color:var(--accent3); font-weight:bold; } "
        ".tag { font-size:10px; font-weight:bold; text-transform:uppercase; padding:1px 4px; border-radius:3px; border:1px solid currentColor; margin-left:4px; } "
        ".up { color:var(--accent3); } "
        ".down { color:var(--accent); } "
        ".dim-more { font-size:12px; color:var(--muted); margin-top:8px; font-style:italic; } "
        ".flags ul { list-style:none; padding:0; } "
        ".flags li { background:#fbeae3; border-left:3px solid var(--accent); padding:8px 12px; margin:6px 0; border-radius:0 4px 4px 0; font-size:14px; } "
        ".drift-only { font-size:13px; color:var(--muted); margin-top:8px; } "
        ".print-btn { position:fixed; top:16px; right:16px; background:var(--accent); color:#fff; border:0; border-radius:6px; padding:8px 14px; font-size:13px; cursor:pointer; font-family:inherit; } "
        "@media print { .print-btn { display:none; } body { padding:24px; max-width:none; } }"
    )

    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f'<title>Fair Code - Representation Drift</title><style>{style}</style></head><body>'
        '<button class="print-btn" onclick="window.print()">🖨 Print / Save as PDF</button>'
        '<div class="head"><h1>Representation Drift (A → B)</h1></div>'
        f'{summary_html}'
        f'{"".join(cards_html)}'
        f'{flags_html}'
        f'{proxy_html}'
        f'{only_html}'
        '<p style="color:var(--muted);font-size:12px;margin-top:32px">'
        'Generated by <a href="https://github.com/yakew7/Fair-Code">Fair Code</a> - diagnostic only.</p>'
        '</body></html>'
    )
