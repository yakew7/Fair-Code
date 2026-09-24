(function () {
  const repoUrl = 'https://github.com/yakew7/Fair-Code';
  const explainers = window.FAIR_CODE_EXPLAINERS || [];
  // Keep in sync with the pillLabels map in index.html's search script -
  // both render the same tag vocabulary as a human-readable pill.
  const TAG_LABELS = {
    detection: 'Detection',
    metrics: 'Metrics',
    data: 'Data Bias',
    explainability: 'Explainability',
    healthcare: 'Healthcare',
    'case-study': 'Case Study',
  };
  const projectAnchors = {
    'COMPAS': 'project-compas',
    'AI Fair Recruitment': 'project-hiring',
    'German Credit Lending': 'project-credit',
    'Insurance Denial': 'project-insurance',
    'Benefits Denial': 'project-benefits',
    'Healthcare Readmission': 'project-readmission',
    'Tenant Screening': 'project-tenant',
  };

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function unescapeHtml(value) {
    return String(value)
      .replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, '\'');
  }

  function inlineMarkdown(text) {
    const escaped = escapeHtml(text);
    return escaped
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\*([^*]+)\*/g, '<em>$1</em>')
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label, url) => {
        // `url` was extracted from `escaped` above, so it's already
        // HTML-entity-encoded - unescape before resolving so the
        // escapeHtml() below is the only encoding pass the URL goes
        // through, instead of double-encoding e.g. "&" into "&amp;amp;".
        const trimmed = unescapeHtml(url.trim());
        const isExternal = /^(?:[a-z]+:)/i.test(trimmed);
        const resolved = resolveLinkTarget(trimmed);
        return `<a href="${escapeHtml(resolved)}"${isExternal ? ' target="_blank" rel="noreferrer noopener"' : ''}>${label}</a>`;
      });
  }

  function resolveLinkTarget(url) {
    if (/^(?:[a-z]+:|#|\/)/i.test(url)) {
      return url;
    }

    const hashIndex = url.indexOf('#');
    const queryIndex = url.indexOf('?');
    const pathEnd = [hashIndex, queryIndex].filter(index => index !== -1).sort((a, b) => a - b)[0] ?? url.length;
    const rawPath = url.slice(0, pathEnd);
    const suffix = url.slice(pathEnd);
    const normalizedPath = decodeURIComponent(rawPath.replace(/^\.\.\//, '').replace(/^\.\//, ''));
    const cleanPath = normalizedPath.replace(/\/+$/, '');
    const basename = cleanPath.split('/').pop() || cleanPath;
    const baseWithoutExt = basename.replace(/\.md$/i, '');

    if (/\.md$/i.test(basename) && explainers.some(entry => entry.slug === baseWithoutExt)) {
      return `${encodeURIComponent(baseWithoutExt)}.html${suffix}`;
    }

    if (projectAnchors[cleanPath] || projectAnchors[basename]) {
      const anchor = projectAnchors[cleanPath] || projectAnchors[basename];
      return `../index.html#${anchor}${suffix}`;
    }

    if (/\.md$/i.test(basename)) {
      return `${encodeURIComponent(baseWithoutExt)}.html${suffix}`;
    }

    return url.startsWith('../') ? cleanPath : url;
  }

  function slugifyHeading(text) {
    return String(text)
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '');
  }

  function parseTable(lines, startIndex) {
    const rows = [];
    let index = startIndex;

    while (index < lines.length && /^\s*\|/.test(lines[index])) {
      rows.push(lines[index].trim());
      index++;
    }

    if (rows.length < 2 || !/^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?$/.test(rows[1])) {
      return null;
    }

    // Split on unescaped "|" only, then unescape "\|" -> "|" in each cell, so
    // a literal pipe inside a cell (GFM's "\|") no longer starts a spurious
    // column. Mirrors scripts/build_explainers.py's split_row().
    const splitRow = row => row.trim().split(/(?<!\\)\|/).slice(1, -1)
      .map(cell => cell.trim().replace(/\\\|/g, '|'));

    const headers = splitRow(rows[0]);
    const bodyRows = rows.slice(2).map(splitRow);

    const headerHtml = headers.map(cell => `<th>${inlineMarkdown(cell)}</th>`).join('');
    const bodyHtml = bodyRows.map(row => `<tr>${row.map(cell => `<td>${inlineMarkdown(cell)}</td>`).join('')}</tr>`).join('');

    return {
      html: `<div class="explainer-table-wrap"><table class="explainer-table"><thead><tr>${headerHtml}</tr></thead><tbody>${bodyHtml}</tbody></table></div>`,
      nextIndex: index - 1,
    };
  }

  function renderMarkdown(markdown) {
    const lines = String(markdown).replace(/\r\n/g, '\n').split('\n');
    const blocks = [];
    let paragraph = [];
    let listItems = [];
    let quoteLines = [];
    let codeLines = [];
    let codeLang = '';
    let inCode = false;
    const headingCounts = new Map();

    function flushParagraph() {
      if (paragraph.length) {
        blocks.push(`<p>${inlineMarkdown(paragraph.join(' ').replace(/\s+/g, ' ').trim())}</p>`);
        paragraph = [];
      }
    }

    function flushList() {
      if (listItems.length) {
        blocks.push(`<ul>${listItems.map(item => `<li>${inlineMarkdown(item)}</li>`).join('')}</ul>`);
        listItems = [];
      }
    }

    function flushQuote() {
      if (quoteLines.length) {
        blocks.push(`<blockquote>${quoteLines.map(line => `<p>${inlineMarkdown(line)}</p>`).join('')}</blockquote>`);
        quoteLines = [];
      }
    }

    function flushCode() {
      if (codeLines.length) {
        blocks.push(`<pre><code${codeLang ? ` class="language-${escapeHtml(codeLang)}"` : ''}>${escapeHtml(codeLines.join('\n'))}</code></pre>`);
        codeLines = [];
        codeLang = '';
      }
    }

    for (let index = 0; index < lines.length; index++) {
      const line = lines[index];
      const trimmed = line.trim();

      if (inCode) {
        if (/^```/.test(trimmed)) {
          inCode = false;
          flushCode();
        } else {
          codeLines.push(line);
        }
        continue;
      }

      const table = parseTable(lines, index);
      if (table) {
        flushParagraph();
        flushList();
        flushQuote();
        blocks.push(table.html);
        index = table.nextIndex;
        continue;
      }

      if (/^```/.test(trimmed)) {
        flushParagraph();
        flushList();
        flushQuote();
        inCode = true;
        codeLang = trimmed.slice(3).trim();
        continue;
      }

      if (!trimmed) {
        flushParagraph();
        flushList();
        flushQuote();
        continue;
      }

      if (/^---+$/.test(trimmed)) {
        flushParagraph();
        flushList();
        flushQuote();
        blocks.push('<hr>');
        continue;
      }

      const headingMatch = trimmed.match(/^(#{1,6})\s+(.+)$/);
      if (headingMatch) {
        flushParagraph();
        flushList();
        flushQuote();
        // +1 offset: the explainer page's hero already renders a real <h1>.
        // Mirrors scripts/build_explainers.py's render_markdown().
        const level = Math.min(headingMatch[1].length + 1, 6);
        const headingText = headingMatch[2];
        const baseId = slugifyHeading(headingText);
        const nextCount = (headingCounts.get(baseId) || 0) + 1;
        headingCounts.set(baseId, nextCount);
        const headingId = nextCount === 1 ? baseId : `${baseId}-${nextCount}`;
        blocks.push(`<h${level} id="${escapeHtml(headingId)}">${inlineMarkdown(headingText)}</h${level}>`);
        continue;
      }

      if (/^>\s?/.test(trimmed)) {
        flushParagraph();
        flushList();
        quoteLines.push(trimmed.replace(/^>\s?/, ''));
        continue;
      }

      if (/^[-*]\s+/.test(trimmed)) {
        flushParagraph();
        flushQuote();
        listItems.push(trimmed.replace(/^[-*]\s+/, ''));
        continue;
      }

      flushQuote();
      flushList();
      paragraph.push(trimmed);
    }

    flushParagraph();
    flushList();
    flushQuote();
    flushCode();

    return blocks.join('\n');
  }

  function findExplainer(slug) {
    return explainers.find(entry => entry.slug === slug) || null;
  }

  function renderCards(container) {
    if (!container) return;

    container.innerHTML = explainers.map((entry, index) => {
      const tags = entry.tags.join(' ');
      const label = String(index + 1).padStart(2, '0');
      return `
        <article class="explainer-card reveal" data-explainer-tags="${escapeHtml(tags)}" data-explainer-text="${escapeHtml(`${entry.title} ${entry.subtitle} ${entry.summary} ${tags}`)}">
          <a class="explainer-card-link" href="explainers/${encodeURIComponent(entry.slug)}.html" aria-label="Open ${escapeHtml(entry.title)} explainer">
            <div class="explainer-card-top">
              <div>
                <div class="explainer-num">Explainer - ${label}</div>
                <h3 class="explainer-title">${escapeHtml(entry.title)}</h3>
                <p class="explainer-tagline">${escapeHtml(entry.subtitle)}</p>
              </div>
              <span class="explainer-arrow" aria-hidden="true">↗</span>
            </div>
            <p class="explainer-summary">${escapeHtml(entry.summary)}</p>
            <div class="explainer-card-footer">
              <span class="explainer-pill">${escapeHtml(TAG_LABELS[entry.tags[0]] || entry.tags[0])}</span>
              <span class="explainer-link-copy">Open explainer</span>
            </div>
          </a>
        </article>
      `;
    }).join('');
  }

  async function renderDetailPage() {
    const shell = document.querySelector('[data-explainer-shell]');
    const titleEl = document.querySelector('[data-explainer-title]');
    const subtitleEl = document.querySelector('[data-explainer-subtitle]');
    const summaryEl = document.querySelector('[data-explainer-summary]');
    const sourceEl = document.querySelector('[data-explainer-source]');
    const container = document.querySelector('[data-explainer-content]');
    const statusEl = document.querySelector('[data-explainer-status]');

    if (!shell || !container || !titleEl) return;

    const params = new URLSearchParams(window.location.search);
    const slug = params.get('slug') || 'proxy-variables';
    const entry = findExplainer(slug) || explainers[0];

    if (!entry) {
      statusEl.textContent = 'No explainer found.';
      container.innerHTML = '';
      return;
    }

    document.title = `${entry.title} · Fair Code`;
    titleEl.textContent = entry.title;
    subtitleEl.textContent = entry.subtitle;
    summaryEl.textContent = entry.summary;
    sourceEl.href = `${repoUrl}/blob/main/explainers/${entry.slug}.md`;
    sourceEl.textContent = 'View source on GitHub';

    statusEl.textContent = 'Loading explainer...';

    const response = await fetch(`explainers/${entry.slug}.md`);
    if (!response.ok) {
      throw new Error(`Could not load explainer markdown for ${entry.slug}.`);
    }

    const markdown = await response.text();
    container.innerHTML = renderMarkdown(markdown);
    statusEl.textContent = '';
    shell.classList.add('is-ready');
  }

  window.FairCodeExplainersApp = {
    renderCards,
    renderDetailPage,
  };

  renderCards(document.getElementById('explainers-grid'));

  if (document.querySelector('[data-explainer-shell]')) {
    renderDetailPage().catch(error => {
      const statusEl = document.querySelector('[data-explainer-status]');
      if (statusEl) statusEl.textContent = error.message;
    });
  }
})();
