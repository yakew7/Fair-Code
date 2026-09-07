#!/usr/bin/env python3
"""Generate static, crawlable explainer pages from explainers/*.md.

Contributors only ever touch two files: explainers/<slug>.md and one entry
in assets/explainers-data.json. This script (run by CI on every push that
touches those files) does everything else:

  - renders each markdown file to HTML using the same rendering rules as
    the browser-side renderer in assets/explainers-ui.js, so output matches
    what the site already looks like
  - writes one real, pre-rendered page per explainer to explainers/<slug>.html
    (title/description/canonical/JSON-LD baked into the raw HTML, not
    loaded in afterward by JS)
  - regenerates assets/explainers-data.js from assets/explainers-data.json
    so the two never drift apart
  - regenerates sitemap.xml

Nothing here is contributor-facing. Run with: python3 scripts/build_explainers.py
"""
import json
import re
import subprocess
from html import escape as _escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPLAINERS_DIR = ROOT / "explainers"
DATA_JSON = ROOT / "assets" / "explainers-data.json"
DATA_JS = ROOT / "assets" / "explainers-data.js"
SITEMAP = ROOT / "sitemap.xml"
LLMS_FULL = ROOT / "llms-full.txt"
OG_DIR = ROOT / "assets" / "og"
OG_LIGHT_DIR = ROOT / "assets" / "og-light"

# A generated, package-internal mirror of explainers/*.md + explainers-data.json
# for faircode/mcp_server.py's list_explainers/get_explainer tools. explainers/
# and assets/ live at the repo root, outside the faircode/ package pyproject.toml
# actually ships - a real `pip install faircode[mcp]` never has them on disk, so
# the MCP tools need their own copy that IS inside the installed package (issue
# #388). Mirrors the same "generated copy for a different consumer" precedent
# assets/explainers-data.js already is for the browser.
PACKAGE_MIRROR_DIR = ROOT / "faircode" / "_explainers"
SITE_URL = "https://www.thefaircode.xyz"
REPO_URL = "https://github.com/yakew7/Fair-Code"


PROJECT_ANCHORS = {
    "COMPAS": "project-compas",
    "AI Fair Recruitment": "project-hiring",
    "German Credit Lending": "project-credit",
    "Insurance Denial": "project-insurance",
    "Benefits Denial": "project-benefits",
    "Healthcare Readmission": "project-readmission",
    "Tenant Screening": "project-tenant",
}


def escape_html(value):
    return _escape(str(value), quote=True)


def slugify_heading(text):
    text = str(text).lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def resolve_link_target(url, known_slugs):
    if re.match(r"^(?:[a-z]+:|#|/)", url, flags=re.IGNORECASE):
        return url

    hash_index = url.find("#")
    query_index = url.find("?")
    candidates = [i for i in (hash_index, query_index) if i != -1]
    path_end = min(candidates) if candidates else len(url)
    raw_path = url[:path_end]
    suffix = url[path_end:]

    normalized_path = re.sub(r"^\.\./", "", raw_path)
    normalized_path = re.sub(r"^\./", "", normalized_path)
    from urllib.parse import unquote

    normalized_path = unquote(normalized_path)
    clean_path = normalized_path.rstrip("/")
    basename = clean_path.split("/")[-1] if clean_path else clean_path
    base_without_ext = re.sub(r"\.md$", "", basename, flags=re.IGNORECASE)

    if re.search(r"\.md$", basename, flags=re.IGNORECASE) and base_without_ext in known_slugs:
        # Generated pages live as siblings inside explainers/, so a link to
        # another explainer is just "<slug>.html" in the same directory.
        return f"{base_without_ext}.html{suffix}"

    if clean_path in PROJECT_ANCHORS or basename in PROJECT_ANCHORS:
        anchor = PROJECT_ANCHORS.get(clean_path) or PROJECT_ANCHORS.get(basename)
        return f"../index.html#{anchor}{suffix}"

    if re.search(r"\.md$", basename, flags=re.IGNORECASE):
        return f"{base_without_ext}.html{suffix}"

    # Not a known explainer or project folder - explainers/*.md and the
    # explainers/*.html generated from it live in the same directory, so a
    # plain relative link (e.g. "../notebooks/x.ipynb") is already correct
    # as-is and must not be rewritten (previously this stripped a leading
    # "../", which quietly broke every such link - see #253).
    return url


def inline_markdown(text, known_slugs):
    escaped = escape_html(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)

    def replace_link(match):
        label, url = match.group(1), match.group(2)
        trimmed = url.strip()
        is_external = bool(re.match(r"^(?:[a-z]+:)", trimmed, flags=re.IGNORECASE))
        resolved = resolve_link_target(trimmed, known_slugs)
        target_attr = ' target="_blank" rel="noreferrer noopener"' if is_external else ""
        return f'<a href="{escape_html(resolved)}"{target_attr}>{label}</a>'

    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", replace_link, escaped)
    return escaped


def parse_table(lines, start_index):
    rows = []
    index = start_index
    while index < len(lines) and re.match(r"^\s*\|", lines[index]):
        rows.append(lines[index].strip())
        index += 1

    if len(rows) < 2 or not re.match(
        r"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?$", rows[1]
    ):
        return None

    def split_row(row):
        return [cell.strip() for cell in row.split("|")[1:-1]]

    headers = split_row(rows[0])
    body_rows = [split_row(row) for row in rows[2:]]
    return headers, body_rows, index - 1


def render_markdown(markdown_text, known_slugs):
    lines = markdown_text.replace("\r\n", "\n").split("\n")
    blocks = []
    paragraph = []
    list_items = []
    quote_lines = []
    code_lines = []
    code_lang = ""
    in_code = False
    heading_counts = {}

    def flush_paragraph():
        nonlocal paragraph
        if paragraph:
            text = re.sub(r"\s+", " ", " ".join(paragraph)).strip()
            blocks.append(f"<p>{inline_markdown(text, known_slugs)}</p>")
            paragraph = []

    def flush_list():
        nonlocal list_items
        if list_items:
            items = "".join(f"<li>{inline_markdown(item, known_slugs)}</li>" for item in list_items)
            blocks.append(f"<ul>{items}</ul>")
            list_items = []

    def flush_quote():
        nonlocal quote_lines
        if quote_lines:
            paras = "".join(f"<p>{inline_markdown(line, known_slugs)}</p>" for line in quote_lines)
            blocks.append(f"<blockquote>{paras}</blockquote>")
            quote_lines = []

    def flush_code():
        nonlocal code_lines, code_lang
        if code_lines:
            lang_attr = f' class="language-{escape_html(code_lang)}"' if code_lang else ""
            blocks.append(f"<pre><code{lang_attr}>{escape_html(chr(10).join(code_lines))}</code></pre>")
            code_lines = []
            code_lang = ""

    index = 0
    while index < len(lines):
        line = lines[index]
        trimmed = line.strip()

        if in_code:
            if trimmed.startswith("```"):
                in_code = False
                flush_code()
            else:
                code_lines.append(line)
            index += 1
            continue

        table = parse_table(lines, index)
        if table:
            flush_paragraph()
            flush_list()
            flush_quote()
            headers, body_rows, next_index = table
            header_html = "".join(f"<th>{inline_markdown(cell, known_slugs)}</th>" for cell in headers)
            body_html = "".join(
                "<tr>" + "".join(f"<td>{inline_markdown(cell, known_slugs)}</td>" for cell in row) + "</tr>"
                for row in body_rows
            )
            blocks.append(
                f'<div class="explainer-table-wrap"><table class="explainer-table">'
                f"<thead><tr>{header_html}</tr></thead><tbody>{body_html}</tbody></table></div>"
            )
            index = next_index + 1
            continue

        if trimmed.startswith("```"):
            flush_paragraph()
            flush_list()
            flush_quote()
            in_code = True
            code_lang = trimmed[3:].strip()
            index += 1
            continue

        if not trimmed:
            flush_paragraph()
            flush_list()
            flush_quote()
            index += 1
            continue

        if re.match(r"^---+$", trimmed):
            flush_paragraph()
            flush_list()
            flush_quote()
            blocks.append("<hr>")
            index += 1
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+)$", trimmed)
        if heading_match:
            flush_paragraph()
            flush_list()
            flush_quote()
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2)
            base_id = slugify_heading(heading_text)
            next_count = heading_counts.get(base_id, 0) + 1
            heading_counts[base_id] = next_count
            heading_id = base_id if next_count == 1 else f"{base_id}-{next_count}"
            blocks.append(
                f'<h{level} id="{escape_html(heading_id)}">{inline_markdown(heading_text, known_slugs)}</h{level}>'
            )
            index += 1
            continue

        if re.match(r"^>\s?", trimmed):
            flush_paragraph()
            flush_list()
            quote_lines.append(re.sub(r"^>\s?", "", trimmed))
            index += 1
            continue

        if re.match(r"^[-*]\s+", trimmed):
            flush_paragraph()
            flush_quote()
            list_items.append(re.sub(r"^[-*]\s+", "", trimmed))
            index += 1
            continue

        flush_quote()
        flush_list()
        paragraph.append(trimmed)
        index += 1

    flush_paragraph()
    flush_list()
    flush_quote()
    flush_code()

    return "\n".join(blocks)


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} · Fair Code</title>
<meta name="description" content="{summary}">
<link rel="canonical" href="{canonical}">
<meta name="author" content="Yash Kewlani">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta property="og:site_name" content="Fair Code">
<meta property="og:locale" content="en_US">
<meta property="og:title" content="{title} · Fair Code">
<meta property="og:description" content="{summary}">
<meta property="og:type" content="article">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{og_image}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:type" content="image/png">
<meta property="og:image:alt" content="{title} · Fair Code">
<meta property="og:image" content="{og_image_light}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:type" content="image/png">
<meta property="og:image:alt" content="{title} · Fair Code (light)">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title} · Fair Code">
<meta name="twitter:description" content="{summary}">
<meta name="twitter:image" content="{og_image}">

<link rel="icon" href="/assets/icons/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="/assets/icons/favicon-32x32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/assets/icons/favicon-16x16.png">
<link rel="apple-touch-icon" sizes="180x180" href="/assets/icons/apple-touch-icon.png">
<link rel="icon" type="image/png" sizes="192x192" href="/assets/icons/icon-192.png">

<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect x='32' y='18' width='13' height='64' fill='%2314171A'/><rect x='32' y='18' width='42' height='13' fill='%2314171A'/><rect x='32' y='44' width='36' height='13' fill='%234F7A5B'/></svg>">

<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Archivo:wght@400;500;600;700&family=IBM+Plex+Mono:ital,wght@0,400;0,500;1,400&display=swap" rel="stylesheet">
<script>
  (function () {{
    const systemPref = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    const saved = localStorage.getItem('fc-theme') || systemPref;
    document.documentElement.setAttribute('data-theme', saved);
  }})();
</script>
<link rel="stylesheet" href="../assets/explainers.css">
<style>
  :root {{
    --bg: #f4f1e8;
    --surface: #ebe7d9;
    --border: #d9d3c0;
    --border2: #bdb59c;
    --accent: #a63a22;
    --accent3: #2f6b4f;
    --text: #36321f;
    --muted: #7d7459;
    --white: #1d1910;
    --bias-track-bg: #e2dcc9;

    --serif: 'Instrument Serif', 'Iowan Old Style', Georgia, serif;
    --sans: 'Archivo', 'Helvetica Neue', sans-serif;
    --mono: 'IBM Plex Mono', 'SF Mono', monospace;
  }}

  html[data-theme="dark"] {{
    --bg: #15130d;
    --surface: #1c1912;
    --border: #2e2a1f;
    --border2: #443e2d;
    --accent: #cf6f49;
    --accent3: #79b294;
    --text: #cfc7b0;
    --muted: #8d8367;
    --white: #f1e9d4;
    --bias-track-bg: #242013;
  }}

  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: var(--sans);
    background: var(--bg);
    color: var(--text);
    -webkit-font-smoothing: antialiased;
    transition: background 0.3s, color 0.3s;
  }}
  a {{ color: inherit; }}
  ::selection {{ background: var(--accent); color: var(--bg); }}
  :focus-visible {{ outline: 2px solid var(--accent); outline-offset: 3px; }}
</style>
<script type="application/ld+json">
{jsonld}
</script>
<script>
  window.va = window.va || function () {{ (window.vaq = window.vaq || []).push(arguments); }};
</script>
<script defer src="/_vercel/insights/script.js"></script>
<script>
  window.si = window.si || function () {{ (window.siq = window.siq || []).push(arguments); }};
</script>
<script defer src="/_vercel/speed-insights/script.js"></script>
<script defer src="https://cloud.umami.is/script.js" data-website-id="84e0aebf-44e1-466e-b2c6-62f75e1c36c7"></script>
</head>
<body class="explainer-page">
  <main class="explainer-shell is-ready" data-explainer-shell>
    <div class="explainer-topbar">
      <a class="explainer-back" href="../index.html#explainers">← Back to explainers</a>
      <div class="explainer-topbar-actions">
        <a class="explainer-source" href="{source_url}" target="_blank" rel="noopener noreferrer">View source on GitHub</a>
        <button class="explainer-theme-toggle" id="explainerThemeToggle" aria-label="Toggle theme" aria-pressed="false">☀</button>
      </div>
    </div>

    <section class="explainer-hero">
      <div class="explainer-kicker">Explainer</div>
      <h1 class="explainer-headline">{title}</h1>
      <p class="explainer-lede">{subtitle}</p>
      <p class="explainer-lede">{summary}</p>
    </section>

    <article class="explainer-content">{content}</article>
  </main>

  <script>
    (function () {{
      const toggle = document.getElementById('explainerThemeToggle');
      const html = document.documentElement;
      const systemPref = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';

      function syncTheme() {{
        const current = html.getAttribute('data-theme') || systemPref;
        toggle.textContent = current === 'light' ? '☾' : '☀';
        toggle.setAttribute('aria-label', current === 'light' ? 'Switch to dark mode' : 'Switch to light mode');
        toggle.setAttribute('aria-pressed', current === 'dark' ? 'true' : 'false');
      }}

      syncTheme();

      toggle.addEventListener('click', () => {{
        const current = html.getAttribute('data-theme') || systemPref;
        const next = current === 'dark' ? 'light' : 'dark';
        html.setAttribute('data-theme', next);
        localStorage.setItem('fc-theme', next);
        syncTheme();
      }});
    }})();
  </script>
</body>
</html>
"""


def _plain_text(md: str) -> str:
    """Reduce a markdown fragment to plain text for a JSON-LD answer."""
    md = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", md)   # links -> label
    md = re.sub(r"[*_`>#]", "", md)                    # emphasis / code / quote / heading marks
    return re.sub(r"\s+", " ", md).strip()


def _first_paragraph(markdown_text: str, keywords) -> str | None:
    """First paragraph under the first `##` heading matching any keyword."""
    capturing = False
    buf: list[str] = []
    for line in markdown_text.splitlines():
        heading = re.match(r"^##\s+(.*)", line)
        if heading:
            if capturing:
                break
            capturing = any(k in heading.group(1).lower() for k in keywords)
            continue
        if not capturing:
            continue
        stripped = line.strip()
        if not stripped:
            if buf:
                break
            continue
        if stripped.startswith(("---", "|", "```", "- ", "* ", ">")):
            if buf:
                break
            continue
        buf.append(stripped)
    return _plain_text(" ".join(buf)) if buf else None


def _faq(entry, markdown_text):
    """Two question/answer pairs derived from the explainer's own content, so
    the FAQPage schema reflects real text (for AI answer engines / GEO)."""
    title = entry["title"].strip()
    q1 = title if title.endswith("?") else f"What is {title}?"
    definition = _first_paragraph(markdown_text, ("definition",)) or entry["summary"]
    pairs = [(q1, definition)]
    why = _first_paragraph(markdown_text, ("why it matters", "why this matters"))
    if why:
        if len(why) > 500:
            trimmed = why[:500].rsplit(". ", 1)[0]
            why = (trimmed + ".") if trimmed else why[:500]
        pairs.append(("Why does this matter for fairness?", why))
    return pairs


def build_jsonld(entry, canonical, markdown_text="", dates=None):
    defined_term = {
        "@type": "DefinedTerm",
        "author": {"@type": "Person", "name": "Yash Kewlani",
                   "url": "https://github.com/yakew7"},
        "name": entry["title"],
        "description": entry["summary"],
        "url": canonical,
        "inDefinedTermSet": {
            "@type": "DefinedTermSet",
            "name": "Fair Code Explainers",
            "url": f"{SITE_URL}/index.html#explainers",
        },
    }
    if dates:
        if dates.get("published"):
            defined_term["datePublished"] = dates["published"]
        if dates.get("modified"):
            defined_term["dateModified"] = dates["modified"]
    faq_page = {
        "@type": "FAQPage",
        "url": canonical,
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in _faq(entry, markdown_text)
        ],
    }
    breadcrumbs = {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Fair Code", "item": f"{SITE_URL}/"},
            {"@type": "ListItem", "position": 2, "name": "Explainers", "item": f"{SITE_URL}/index.html#explainers"},
            {"@type": "ListItem", "position": 3, "name": entry["title"], "item": canonical},
        ],
    }
    return json.dumps({"@context": "https://schema.org",
                       "@graph": [defined_term, faq_page, breadcrumbs]}, indent=2)


def build_page(entry, known_slugs):
    slug = entry["slug"]
    md_path = EXPLAINERS_DIR / f"{slug}.md"
    markdown_text = md_path.read_text(encoding="utf-8")
    content_html = render_markdown(markdown_text, known_slugs)
    canonical = f"{SITE_URL}/explainers/{slug}.html"
    dates = {
        "published": _git_first_commit(f"explainers/{slug}.md"),
        "modified": _git_lastmod(f"explainers/{slug}.md"),
    }

    return PAGE_TEMPLATE.format(
        title=escape_html(entry["title"]),
        summary=escape_html(entry["summary"]),
        canonical=canonical,
        subtitle=escape_html(entry["subtitle"]),
        content=content_html,
        source_url=f"{REPO_URL}/blob/main/explainers/{slug}.md",
        og_image=f"{SITE_URL}/assets/og/{slug}.png",
        og_image_light=f"{SITE_URL}/assets/og-light/{slug}.png",
        jsonld=build_jsonld(entry, canonical, markdown_text, dates),
    )


def _git_lastmod(relpath: str) -> str | None:
    """Last commit date (YYYY-MM-DD) of a tracked file, for <lastmod>. None if
    unavailable (untracked file or no git history)."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", relpath],
            capture_output=True, text=True, cwd=str(ROOT), check=False,
        ).stdout.strip()
    except Exception:  # noqa: BLE001 - git absent / shallow clone: just skip lastmod
        return None
    return out if re.match(r"^\d{4}-\d{2}-\d{2}$", out) else None


def _git_first_commit(relpath: str) -> str | None:
    """First commit date (YYYY-MM-DD) of a tracked file, for JSON-LD
    datePublished. None if unavailable (untracked file or no git history)."""
    try:
        out = subprocess.run(
            ["git", "log", "--follow", "--format=%cs", "--", relpath],
            capture_output=True, text=True, cwd=str(ROOT), check=False,
        ).stdout.strip().splitlines()
    except Exception:  # noqa: BLE001 - git absent / shallow clone: just skip datePublished
        return None
    last = out[-1] if out else ""
    return last if re.match(r"^\d{4}-\d{2}-\d{2}$", last) else None


def build_sitemap(entries):
    # (public URL, repo file whose commit date drives <lastmod>)
    items = [(f"{SITE_URL}/", "index.html"),
             (f"{SITE_URL}/profiler.html", "profiler.html")]
    items += [(f"{SITE_URL}/explainers/{e['slug']}.html",
               f"explainers/{e['slug']}.md") for e in entries]
    rows = []
    for url, src in items:
        lastmod = _git_lastmod(src)
        lm = f"\n    <lastmod>{lastmod}</lastmod>" if lastmod else ""
        rows.append(f"  <url>\n    <loc>{escape_html(url)}</loc>{lm}\n  </url>")
    body = "\n".join(rows)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n"
        "</urlset>\n"
    )


def build_data_js(entries):
    payload = json.dumps(entries, indent=2)
    return f"window.FAIR_CODE_EXPLAINERS = {payload};\n"


def build_llms_full(entries):
    """Concatenate every explainer's full markdown into llms-full.txt.

    Follows the llms.txt convention (llmstxt.org): `llms.txt` is the short
    index, `llms-full.txt` is the complete text so AI answer engines and LLM
    crawlers (GEO) can ground on the whole corpus in one fetch.
    """
    header = [
        "# Fair Code - Full Text for LLMs and AI Answer Engines",
        "",
        "> Fair Code exposes and fixes bias in real-world AI systems - criminal "
        "justice, hiring, lending, healthcare, welfare eligibility, and tenant "
        "screening - through open-source audits with measurable results and clear "
        "explainers of the underlying fairness concepts.",
        "",
        f"Site: {SITE_URL}  |  Source: {REPO_URL}  |  Index: {SITE_URL}/llms.txt",
        "",
        "Created and maintained by Yash Kewlani. This file is generated from "
        "explainers/*.md by scripts/build_explainers.py; it concatenates every "
        "explainer in full so an AI assistant can read the complete text in a "
        "single request. Development is fully open - new audits, explainers, "
        "and tooling all merge to main normally; paper/results-frozen/ (tag "
        "v1.0-paper) is kept only as a reference snapshot ahead of a real "
        "paper submission planned for next year.",
        "",
    ]
    parts = ["\n".join(header)]
    for entry in entries:
        slug = entry["slug"]
        body = (EXPLAINERS_DIR / f"{slug}.md").read_text(encoding="utf-8").strip()
        parts.append(
            "---\n\n"
            f"# {entry['title']}\n"
            f"URL: {SITE_URL}/explainers/{slug}.html\n"
            f"Summary: {entry['summary']}\n\n"
            f"{body}\n"
        )
    return "\n".join(parts) + "\n"


def build_package_mirror(entries):
    """Copies assets/explainers-data.json -> faircode/_explainers/data.json
    and every explainers/<slug>.md -> faircode/_explainers/<slug>.md, so the
    installed faircode package carries its own copy for
    mcp_server.py's list_explainers/get_explainer tools (issue #388) -
    removing any stale slug left over from a previously-published explainer
    that no longer exists."""
    PACKAGE_MIRROR_DIR.mkdir(parents=True, exist_ok=True)
    current_slugs = {entry["slug"] for entry in entries}
    for existing in PACKAGE_MIRROR_DIR.glob("*.md"):
        if existing.stem not in current_slugs:
            existing.unlink()
    (PACKAGE_MIRROR_DIR / "data.json").write_text(
        DATA_JSON.read_text(encoding="utf-8"), encoding="utf-8")
    for entry in entries:
        slug = entry["slug"]
        (PACKAGE_MIRROR_DIR / f"{slug}.md").write_text(
            (EXPLAINERS_DIR / f"{slug}.md").read_text(encoding="utf-8"), encoding="utf-8")


def main():
    entries = json.loads(DATA_JSON.read_text(encoding="utf-8"))
    known_slugs = {entry["slug"] for entry in entries}

    missing = [
        e["slug"]
        for e in entries
        if not (EXPLAINERS_DIR / f"{e['slug']}.md").exists()
    ]

    if missing:
        raise SystemExit(
            f"Missing markdown file(s) for: {', '.join(missing)}"
        )

    def _og_missing_or_empty(path):
        return not path.exists() or path.stat().st_size == 0

    missing_og = [
        e["slug"]
        for e in entries
        if _og_missing_or_empty(OG_DIR / f"{e['slug']}.png")
        or _og_missing_or_empty(OG_LIGHT_DIR / f"{e['slug']}.png")
    ]

    if missing_og:
        raise SystemExit(
            "Missing Open Graph image(s) for: "
            + ", ".join(missing_og)
            + ". Run scripts/generate_og_images.py first."
        )
    for entry in entries:
        page_html = build_page(entry, known_slugs)
        out_path = EXPLAINERS_DIR / f"{entry['slug']}.html"
        out_path.write_text(page_html, encoding="utf-8")

    DATA_JS.write_text(build_data_js(entries), encoding="utf-8")
    SITEMAP.write_text(build_sitemap(entries), encoding="utf-8")
    LLMS_FULL.write_text(build_llms_full(entries), encoding="utf-8")
    build_package_mirror(entries)

    print(f"Generated {len(entries)} explainer pages, assets/explainers-data.js, "
          "sitemap.xml, llms-full.txt, and faircode/_explainers/ (MCP package mirror)")


if __name__ == "__main__":
    main()
