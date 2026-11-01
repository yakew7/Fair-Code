<div align="center">

# Security Policy

![Responsible Disclosure](https://img.shields.io/badge/Disclosure-Coordinated-blue?style=flat-square)
![Response Time](https://img.shields.io/badge/Acknowledgement-%3C48h-brightgreen?style=flat-square)
![Supported](https://img.shields.io/badge/Supported-main%20branch-success?style=flat-square)

*This document applies to **Fair Code** (`yakew7/Fair-Code`) and any other repository under this account that links to it.*

[Scope](#scope) · [Supported Versions](#supported-versions) · [What Counts](#what-counts-as-a-vulnerability) · [Reporting](#reporting-a-vulnerability) · [Timeline](#response-timeline) · [Disclosure](#disclosure-policy)

</div>

---

## Scope

This policy covers the following repositories:

| Repository | What It Is |
|---|---|
| [`yakew7/Fair-Code`](https://github.com/yakew7/Fair-Code) | Algorithmic bias detection & mitigation - audits, explainers, website |
| [`yakew7/Cardiovascular-disease-prediction`](https://github.com/yakew7/Cardiovascular-disease-prediction) | Predits the chance of having Cardiovascular Disease and Hypertension |

If you find a vulnerability in any of the above, follow the process below regardless of which repo it affects.

---

## Supported Versions

These repositories are educational and research projects. Only the **latest commit on `main`** is actively maintained. No version-specific backports are made.

| Branch / Version | Supported |
|---|---|
| `main` (latest) | ✅ Yes |
| Any previous commit / fork | ❌ No |

---

## What Counts as a Vulnerability

Because these projects are primarily data analysis scripts and a static website, the realistic attack surface is narrow. Please report any of the following:

- **Dependency vulnerabilities** - a Python package or npm dependency with a known CVE that could affect users who clone and run the code
- **Script injection** - any way a specially crafted dataset could cause `unfair.py` or `fair.py` to execute arbitrary code on a user's machine
- **Website vulnerabilities** - XSS, CSP bypass, or any injection vector in `index.html` that could affect visitors to [thefaircode.xyz](https://www.thefaircode.xyz)
- **Dependency confusion / supply chain** - a malicious package name collision in `requirements.txt` or any future `package.json`
- **Data exposure** - if any future dataset or file in the repo inadvertently contains personally identifiable information (PII) that was not intended to be public

The following are **out of scope** and do not need to be reported:

- Theoretical vulnerabilities with no practical exploit path on a static site or offline script
- Issues in third-party tools (scikit-learn, pandas, etc.) - report those upstream
- Missing security headers on Vercel's CDN - report those to Vercel
- Rate limiting, DoS, or brute-force concerns (there is no authentication surface)

---

## Reporting a Vulnerability

**Do not open a public GitHub Issue for security vulnerabilities.**

Instead, use one of the following private channels:

### Option 1 - GitHub Private Vulnerability Reporting *(preferred)*

GitHub has a built-in private reporting flow:

1. Go to the affected repository on GitHub
2. Click **Security** → **Advisories** → **Report a vulnerability**
3. Fill in the form - it goes directly to the maintainer without being public

This is the fastest path. GitHub will notify me immediately and we can coordinate a fix privately before any public disclosure.

### Option 2 - Direct Contact

If you cannot use GitHub's reporting flow, reach out directly:

- **Instagram DM:** [@thefaircodeproject](https://www.instagram.com/thefaircodeproject)
- **LinkedIn:** [Yash Kewlani](https://www.linkedin.com/in/yash-kewlani-7ab090357)

Include the word **SECURITY** at the start of your message so it doesn't get missed.

---

## What to Include in Your Report

A good report makes it possible to reproduce and fix the issue quickly. Please include:

```
Repository:       yakew7/Fair-Code  (or the specific repo)
Affected file(s): e.g. requirements.txt, index.html
Description:      What the vulnerability is and how it works
Steps to reproduce:
  1. ...
  2. ...
Impact:           What an attacker could achieve
Suggested fix:    (optional, but appreciated)
```

---

## Response Timeline

| Stage | Target |
|---|---|
| Acknowledgement of report | Within **48 hours** |
| Confirmation (valid / not valid) | Within **5 days** |
| Fix deployed (if valid) | Within **14 days** for high severity; best-effort for low |
| Public disclosure | After fix is live, coordinated with reporter |

These are best-effort timelines for a solo maintainer. If something genuinely critical comes in, I will prioritise it.

---

## Disclosure Policy

This project follows **coordinated disclosure**:

- Vulnerabilities are fixed privately before any public announcement
- The reporter is credited in the fix commit and/or GitHub Security Advisory (unless they prefer to stay anonymous)
- Public disclosure happens after a fix is live - typically within 90 days of the initial report, sooner if the fix is fast

---

## Dependencies

The main runtime dependencies are listed in [`requirements.txt`](requirements.txt). If you discover a CVE in one of them, please:

1. Check whether the version pinned in `requirements.txt` is actually affected
2. If yes, report it here so the pinned version can be updated
3. Also report it to the upstream package maintainers directly

---

## Automated Scanning

[CodeQL](https://github.com/yakew7/Fair-Code/security/code-scanning) runs on every push to `main`, every PR, and weekly on a schedule (`.github/workflows/codeql.yml`). Findings go to the repo's Security tab and trigger a GitHub notification email - the maintainer (@yakew7) triages those as they come in, same as an externally reported vulnerability. There's no separate SLA for automated findings beyond the [response timeline](#response-timeline) above; a scan result gets the same treatment as a report through Option 1 or 2.

If a CodeQL alert turns out to be a false positive for this project's domain (e.g. logging aggregate fairness statistics isn't a PII leak), it's dismissed with a comment explaining why rather than left open indefinitely - see `CHANGELOG.md` for past examples.

---

## Credits

Responsible disclosure is appreciated. Reporters who identify valid vulnerabilities will be credited here (with permission):

*No reports received yet.*

---

*This policy covers Fair Code and linked repositories. For general questions about the project, open a GitHub Discussion or reach out on Instagram.*
