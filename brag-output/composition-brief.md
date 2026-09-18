# Hyperframes Composition Brief: Fair Code

## Objective
Create a short, cinematic launch-style brag video for Fair Code, an open-source project that audits real AI systems for demographic bias and proves the fix with real terminal output.

## Output
- Composition directory: `brag-output/composition/`
- Rendered video: `brag-output/brag.mp4`
- Format: landscape — 1920x1080
- Duration: 20 seconds (15-25s range)

## Source Material
- Project root: `/Users/yashkewlani/Desktop/Fair-Code`
- Primary files read: `index.html` (hero, ticker, COMPAS project card, bias bars, terminals), `README.md`, `CLAUDE.md`
- Product name: Fair Code
- Tagline / strongest claim: "The bias is real. So is the fix." — and the COMPAS stat: a real courtroom algorithm flags Black defendants high-risk at 87.16% vs 0.40% for white defendants.
- Key UI or visual moment to recreate: the paired terminal windows from the live COMPAS project card (`unfair.py — BIASED MODEL` vs `fair.py — MITIGATED MODEL`), the animated bias bar, and the `82% reduction` badge stamp.
- Copy that must appear verbatim:
  - "The bias is real. So is the fix."
  - "Black Defendant High-Risk Rate: 87.16%"
  - "White Defendant High-Risk Rate: 0.40%"
  - "Fairness Gap: 86.77%"
  - "# Race removed ✓"
  - "# CustodyStatus removed ✓ (proxy for race)"
  - "Black Defendant High-Risk Rate: 84.71%"
  - "White Defendant High-Risk Rate: 69.02%"
  - "New Fairness Gap: 15.69%"
  - "82% reduction"
  - "AI HIRING · 97.3% REDUCTION"
  - "LENDING · 73.6% REDUCTION"
  - "HEALTHCARE · 60% REDUCTION"
  - "Fair Code"
  - "7 audits. Every fairness gap measured, then closed. Open source."
  - "thefaircode.xyz"

## Creative Direction
- Tone preset: cinematic
- Creative direction: investigative-exposé trailer — courtroom-to-terminal, played completely seriously, no jokes or winking
- Interpretation: short declarative sentences, full-bleed typography for the hook/outro, dramatic reveals rather than rapid chaotic cuts, motion restrained enough that every stat and line of terminal output is fully read before the cut
- Angle: This is a real research project, not a gag — the video should feel like the trailer for an investigative report. Let the real numbers (87% vs 0.4%, then 82% reduction) carry the drama. The site's own "audit ledger" visual system (paper background, red for bias, green for fixed, terminal windows) already looks and feels like evidence, so recreate it faithfully rather than restyling it.
- Hook: cream ledger background, eyebrow line rises, then "The bias is real." (ink) → "So is the fix." (fix in ledger green, real in brick red) — matches the live site's `.hl` highlight treatment exactly
- Outro / punchline: ledger-stamp of the "Fair Code" wordmark, tagline "7 audits. Every fairness gap measured, then closed. Open source.", URL "thefaircode.xyz" stamped last
- Avoid:
  - Generic SaaS language ("streamline", "empower", etc.)
  - Abstract filler visuals — every scene must show real site content
  - Any restyling away from the site's existing paper/terminal/ledger identity
  - Chaotic or comedic SFX — this is a serious subject

## Visual Identity
- Background: `#f4f1e8` (paper cream), surface `#ebe7d9`, borders `#d9d3c0` / `#bdb59c`
- Text: `#36321f` body, `#1d1910` strongest ink (headings), `#7d7459` muted
- Accent (bias/bad): `#a63a22` brick red, deep red `#8c2f1b`
- Accent (fixed/good): `#2f6b4f` ledger green
- Terminal chrome: bg `#191610`, bar `#211d14`, terminal text `#d6d0bd`, terminal label `#8d8367`
- Display font: 'Instrument Serif' (headlines) — use a Google Fonts fallback load since this is a fresh composition, not the live site
- Body/UI font: 'Archivo' (sans)
- Mono/data font: 'IBM Plex Mono' (terminal output, stat numbers, ticker)
- Visual references from the project: hero eyebrow + `.hl` highlighted headline treatment, `.project-card` terminal-pair layout with traffic-light dots, `.bias-bar-wrap` / `.bias-fill` animated bar, `.reduction-badge` stamp, the scrolling `.ticker` strip

## Storyboard
Use the storyboard in `brag-output/brag-plan.md` as the creative contract. Scene summary:
1. Hook — 3s — eyebrow line, then "The bias is real. / So is the fix." with the site's red/green highlight treatment
2. The problem terminal — 4s — `unfair.py` terminal prints its 3 real stat lines, then "86.77%" punches up full-scale
3. The fix, live — 5s — code comment lines type in (race/CustodyStatus removed), `fair.py` terminal prints its green result, bias bar animates down, `82% reduction` badge stamps in (this is the payoff — beat-lock candidate near 8.74s/9.29s from the bundled cue file, ±0.15s, if it lands naturally with this scene's timing)
4. Pattern proof — 3.5s — 3 ticker items snap in showing the same red→green pattern across other audits (hiring 97.3%, lending 73.6%, healthcare 60%)
5. Outro — 4s — "Fair Code" wordmark stamps in, tagline settles, URL stamps last (beat-lock candidate near 17.47s/18.56s if it aligns naturally)

## Audio
- Audio role: cinematic support with restrained, motion-matched accents
- Audio arc: quiet and tense under the hook → builds through the biased-model terminal → swells at the fix/payoff (bias bar drop + reduction stamp) → settles through the ticker proof beat → fades cleanly under the outro stamp
- Music: `assets/music/happy-beats-business-moves-vol-12-by-ende-dot-app.mp3` (steady, clean — the tone reference's recommended cinematic/polished track)
- Music treatment: start quiet (~0.25-0.3 volume) under the hook, no hard volume jumps — let the arrangement's own build carry the rise, clean fade-out under the final outro hold, no ducking needed (no voiceover)
- Music cue guidance: bundled preset at `assets/music/cues/happy-beats-business-moves-vol-12-by-ende-dot-app.music-cues.json` (109.96 BPM). Candidate strong cues inside the 0-20s window: 8.74s and 9.29s (near the Scene 3 payoff), 10.93s, 13.11s, 17.47s and 18.56s (near the Scene 5 outro stamp). Use as optional bias only — do not distort scene 3's read-time floor to hit a cue.
- Audio-reactive treatment: subtle — the ledger-stamp wordmark and the `82% reduction` badge may gain a very slight presence/glow breathing with the music's RMS at their landing moment; nothing else should react
- Audio-coupled moments:
  - Scene 1 hook lines — soft mechanical "line print" tick per phrase (not full keyboard typing, this is a headline not a text field)
  - Scene 2 terminal lines — print-line tick per row, low tone building under the final "86.77%" punch
  - Scene 3 code comments — subtle keypress ticks (randomize from the keyboard set) as the two comment lines type in
  - Scene 3 bias bar — a low mechanical "tighten" sound as the fill shrinks, no whoosh
  - Scene 3 reduction badge stamp — one dry impact/bell hit, this is the emotional peak of the video
  - Scene 4 ticker items — soft tick per item, echoing the terminal print sound for continuity
  - Scene 5 wordmark stamp — one dry impact hit matching Scene 3's stamp sound for consistency
- SFX selection guidance: prefer the copied `impactBell_heavy_000`/`_003` or `impactSoft_medium_000` for the two stamp moments (Scene 3 badge, Scene 5 wordmark), `interface/bong_001` only if a softer single accent is needed elsewhere. Use randomized `keyboard/keypress-*.wav` files (copy a handful into `assets/sfx/keyboard/` if used) for the Scene 3 code-comment typing. Keep everything sparse — 2-3 SFX moments beyond the print-line ticks, per the cinematic tone's SFX energy guidance.
- SFX analysis guidance: consult `sfx-analysis.md` in the skill assets (via the hyperframes-creative skill's own lookup) before finalizing exact files — prefer low/medium HF-risk picks since these moments repeat/matter.
- Exact SFX choice: Hyperframes should choose exact filenames, timestamps, density, and volume based on the implemented animation timing.
- Audio files: music and SFX already copied into `brag-output/composition/assets/` (music + cues, `impact/impactBell_heavy_000.ogg`, `impact/impactBell_heavy_003.ogg`, `impact/impactSoft_medium_000.ogg`, `interface/bong_001.ogg`). Copy additional keyboard SFX from the skill assets if used for Scene 3 typing.

## Hyperframes Instructions
Load the composition-building Hyperframes domain skills — `hyperframes-core` (composition contract + `data-*` timing), `hyperframes-animation` (motion), `hyperframes-creative` (design spec, beats, audio-reactive), `hyperframes-keyframes` (seek-safe keyframes), and `hyperframes-cli` (lint/check/render). `/brag` is its own workflow: do not enter the `hyperframes` entry-point intent interview and do not route into its generic promo/launch-video workflow. Prefer native Hyperframes conventions over anything in `/brag`.

Requirements:
- Show at least one real UI, copy, or visual element from the source project (the COMPAS terminal pair, bias bar, and reduction badge are the mandatory centerpiece).
- Keep all text readable in the final render — respect the reading-time floors noted in the storyboard (short label ~0.8s settled, full sentence ~0.3s/word).
- Keep the video within 15-25 seconds (target 20s).
- Include the planned music/SFX layer — audio was not disabled.
- Treat the `/brag` audio notes above as guidance, not a fixed cue sheet — choose exact SFX after the visual animation exists.
- Treat the bundled music cue metadata as optional timing hints; ignore any cue that would hurt readability, scene pacing, or the product story. Use at most 1-3 strong-cue locks in this 20s video.
- Use SFX to support motion and interaction: print-line ticks for terminal text, keypress ticks for the code-comment typing, a single stamp/impact sound for the reduction badge and the outro wordmark.
- When wiring the music, consider the hyperframes-creative audio-reactive workflow for a subtle glow/presence effect on the reduction badge and outro wordmark only — no waveform/equalizer visuals, no strobing.
- Use local assets already copied into `composition/assets/` for audio; add any further local assets (fonts, keypress SFX) as needed.
- Run `npx hyperframes check` before render — it is /brag's single gate.
