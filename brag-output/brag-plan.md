# Brag Plan: Fair Code

## What is this app?
Fair Code is an open-source research project that audits real-world AI systems — a courtroom risk score, a hiring model, a lending model, healthcare and welfare eligibility models, a tenant-screening model — for demographic bias, then engineers a fixed version of the same model and proves the fairness gap closed, in the open, with real terminal output.

## The angle
This isn't a joke product, it's an exposé. The site is built like an "audit ledger": paper-cream background, brick-red for bias, ledger-green for fixed, terminal windows printing real before/after numbers. The angle is to play it completely straight and let the numbers do the work — a real courtroom algorithm flags Black defendants as high-risk at 87% and white defendants at 0.4%, same system. Then show the fix landing, live, in a terminal. Investigative-trailer energy applied to an open-source repo.

## Hook (first 2-3 seconds)
Cream ledger background. A terminal cursor blinks. The eyebrow line "Algorithmic bias research · Open source" flickers in, then the hero line types/slams in: "The bias is real." — hold — "So is the fix." The word "real" and "fix" render in the brick-red / ledger-green accent colors exactly as on the live site.

## Key moments (the middle)
- The COMPAS terminal pair: `unfair.py — BIASED MODEL` prints its result lines one by one (Black Defendant High-Risk Rate: 87.16%, White: 0.40%, Fairness Gap: 86.77%) in the red "bad" terminal styling.
- A code fragment types in showing the actual fix: `# Race removed ✓` / `# CustodyStatus removed ✓ (proxy for race via over-policing)` — the moment the mitigation happens, not just a claim about it.
- Cut to `fair.py — MITIGATED MODEL` printing green "good" lines, the bias bar animating down from 86.77% to 15.69%, and the `82% reduction` badge stamping on like a ledger stamp.
- A fast ticker-tape beat showing the same pattern repeats across the other audits: "97.3% REDUCTION" (hiring), "73.6% REDUCTION" (lending), "60% REDUCTION" (healthcare) — proving this is a system, not a one-off.

## Outro / punchline
Ledger stamp-in of the wordmark: "Fair Code." Tagline holds: "7 audits. Every fairness gap measured, then closed. Open source." URL stamps in last: thefaircode.xyz.

## User flow worth showing
The site's real "flow" is the audit pipeline itself, not a dashboard: **train a biased model → measure the fairness gap → engineer a fair model → measure again.** Show it literally as the terminal pair from the COMPAS project card:
1. Entry: `unfair.py` terminal runs, prints the biased result (87.16% / 0.40% / 86.77% gap) in red.
2. Key action: the code diff removing race + the `CustodyStatus` proxy variable.
3. Result: `fair.py` terminal runs, prints the mitigated result in green, bias bar drops, reduction badge lands.
This is the actual product in use — not a marketing recreation — pulled directly from the live COMPAS project card on thefaircode.xyz.

## Tone
- Preset: cinematic
- Creative direction: investigative-exposé trailer — courtroom-to-terminal, played completely seriously
- Interpretation: short declarative sentences, dramatic reveals (not quick chaotic cuts), full-bleed typography for the hook and outro, restrained motion that lets each stat land and be read before cutting. No jokes, no winking — the absurdity/gravity is in the real numbers.

## Format: landscape — 1920x1080
## Duration: 20s

## Visual identity (from the project)
- Background: `#f4f1e8` (paper cream, light theme — the site defaults to light)
- Surface: `#ebe7d9`, borders `#d9d3c0` / `#bdb59c`
- Accent (bias/bad): `#a63a22` brick red, deep red `#8c2f1b`
- Accent (fixed/good): `#2f6b4f` ledger green
- Text: `#36321f`, strongest ink/headings `#1d1910`, muted `#7d7459`
- Terminal chrome: bg `#191610`, bar `#211d14`, terminal text `#d6d0bd`
- Display font: 'Instrument Serif' (headlines, serif, editorial)
- Body/UI font: 'Archivo' (sans)
- Mono/data font: 'IBM Plex Mono' (terminal output, stats, tickers)
- Strongest visual element: the paired terminal windows (red "unfair.py" vs green "fair.py") with the bias bar animating down and the reduction badge stamping in — this is the site's signature moment, repeated across all 7 audits.

## Share copy (draft)
A real courtroom algorithm flags Black defendants as high-risk at 87%, white defendants at 0.4%. We found the proxy variable hiding the bias, removed it, and cut the gap by 82% — in the open, with the receipts. thefaircode.xyz

## Audio direction
- Role: cinematic support with restrained motion-matched accents
- Music: a low, serious cinematic bed — sparse strings/piano with a controlled low-end swell timed to the moment the fix lands (bias bar dropping + reduction badge)
- Music treatment: cold open under the hook (low volume), building through the "problem" terminal, swelling right as the "fix" terminal and bias bar drop, settling back down for the outro stamp, clean fade-out on the last frame
- Music cue guidance: to be detected at composition time (no bundled preset chosen yet); target strong-cue timestamps near ~6-7s (fix terminal appears) and ~10-11s (bias bar bottoms out / reduction badge stamps); no fast sequential-text beat-grid needed since the terminal lines are read in order, not as a rapid grid
- Audio-reactive treatment: subtle — the ledger stamp / logo in the outro may pulse gently with the final swell, nothing else reacts to the music
- SFX posture: sparse, motion-matched, professional restraint (this is a serious research project, not a hype reel)
- Audio-coupled moments: terminal lines printing (typewriter/print-line tick per line), the bias bar fill (a low mechanical "tighten" sound as it shrinks), the reduction badge stamp (a single dry stamp/thud), the final logo/URL (one dry hit)
- Restraint rule: no whooshes, no glitch/chaotic SFX, no laugh-track energy — every sound should feel like it belongs in a courtroom or an audit report, not an app-store ad

## Storyboard

### Scene 1 — Hook — 3s
Cream ledger background (`#f4f1e8`). Terminal cursor blinks once. Eyebrow line "Algorithmic bias research · Open source" (IBM Plex Mono, small, muted) rises in first. Then the hero line slams in across two beats: "The bias is real." (ink black) holds, then "So is the fix." completes it, with "real" in brick red and "fix" in ledger green — matching the live site's `.hl` treatment exactly.
Sequential/interaction: yes — eyebrow rises first (~0.4s), then "The bias is" (~0.6s), then "real." highlighted in red (~0.5s hold), then "So is the fix." with "fix" in green (~0.9s hold — full sentence needs the read-time floor).
Audio intent: cold, serious, a single low tone under the type-in, no swell yet.
Audio-coupled idea: a soft mechanical "line print" tick as each phrase lands, like a typewriter/dot-matrix printer.
Music: cinematic bed, quiet, just started.
Transition mood: hard cut → Scene 2.

### Scene 2 — The problem terminal — 4s
Recreation of the actual COMPAS project card terminal: a terminal window titled `unfair.py — BIASED MODEL` (red/yellow/green traffic-light dots, IBM Plex Mono body) prints its real lines one by one: "Black Defendant High-Risk Rate: 87.16%" (red/bad), "White Defendant High-Risk Rate: 0.40%", "Fairness Gap: 86.77%" (red/bad, larger). The big stat "86.77%" then punches up to full scale over the terminal as the scene's final beat.
Sequential/interaction: yes — three terminal lines print in order at readable hold (~0.9s each settled), then the big stat number scales in.
Audio intent: tension building, slightly ominous, matter-of-fact not melodramatic.
Audio-coupled idea: print-line tick per terminal row; a low sustained tone builds under the final big-stat punch.
Music: cinematic bed rising.
Transition mood: hard cut → Scene 3.

### Scene 3 — The fix, live — 5s
Code fragment types in over a dark editor strip: `# Race removed ✓` then `# CustodyStatus removed ✓ (proxy for race)` — real lines from the repo's `fair.py`. Cut to the second terminal, `fair.py — MITIGATED MODEL` (green accents), printing "Black Defendant High-Risk Rate: 84.71%", "White Defendant High-Risk Rate: 69.02%" (good), "New Fairness Gap: 15.69%". Simultaneously the bias bar (from the live site's bias-bar-wrap) animates its fill down from 86.77% to 15.69% width, and a `82% reduction` badge stamps on top like an ink stamp.
Sequential/interaction: yes — two code comment lines type in (~0.6s each), then terminal lines print (~0.7s each), then bias bar animates its width down over ~0.8s while the reduction badge stamps in on the final beat.
Audio intent: release / payoff — this is the emotional turn of the video.
Audio-coupled idea: a distinct tonal shift when the code comments type in (subtle key ticks), a low mechanical "tighten" whoosh-free sound as the bias bar shrinks, one confident dry stamp thud exactly as "82% reduction" lands — this is the music swell peak.
Music: swell peaks here.
Transition mood: clean crossfade → Scene 4.

### Scene 4 — It's a pattern, not a one-off — 3.5s
Fast but readable cut to the site's ticker-tape strip: 3-4 items snap across in the same mono ticker styling — "AI HIRING · 97.3% REDUCTION", "LENDING · 73.6% REDUCTION", "HEALTHCARE · 60% REDUCTION" — each with its little colored dot, reinforcing this same red→green pattern repeats across seven audits.
Sequential/interaction: yes — 3 ticker items reveal in quick succession, each held long enough to read (~0.7s each, short label floor) before the scene cuts.
Audio intent: matter-of-fact momentum, no chaos — still serious, just confirming scale.
Audio-coupled idea: a soft tick per ticker item, echoing the terminal print-line sound from Scenes 2-3 so it feels like the same system, not a new gimmick.
Music: settling down from the swell, still present.
Transition mood: soft crossfade → Scene 5.

### Scene 5 — Outro / punchline — 4s
Ledger-stamp-in of the wordmark "Fair Code" (Instrument Serif, full scale, ink black on cream). Tagline settles beneath: "7 audits. Every fairness gap measured, then closed. Open source." URL stamps in last, smaller, mono: "thefaircode.xyz". Final frame holds clean.
Sequential/interaction: yes — wordmark stamps in first (~0.8s), tagline settles (~1.3s, sentence-length floor), URL stamps last (~0.8s hold to close).
Audio intent: resolution, quiet confidence, the case is closed.
Audio-coupled idea: one dry ink-stamp thud on the wordmark, matching the reduction-badge stamp sound from Scene 3 for consistency; music fades cleanly under the final hold.
Music: fades out.
Transition mood: — (final scene).

**Music mood for this video:** cinematic — low, serious, restrained swell at the midpoint payoff, clean fade to silence.
**Audio summary:** A quiet, tense cinematic bed opens under the hook, builds through the biased-model terminal, peaks in a controlled swell exactly as the fix lands and the bias bar drops, settles through the pattern-proof ticker beat, and fades cleanly under the final ledger-stamp outro — sparse, motion-matched print/stamp SFX throughout, no whooshes or glitch effects, everything sounds like it belongs in an audit report.
