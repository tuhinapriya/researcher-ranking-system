# ResearchAI Design Ideas

## 概述
基于截图，构建一个学术研究者搜索助手界面，去除 Compare 功能和左侧重复的 Saved Researchers 区块。
三栏布局：左侧导航栏 / 中间搜索结果列表 / 右侧研究者详情面板。

---

<response>
<probability>0.07</probability>
<idea>

**Design Movement**: Dark-Mode Scientific Terminal — inspired by academic data terminals and research dashboards (think NASA mission control meets arXiv)

**Core Principles**:
1. Information density over decoration — every pixel serves a purpose
2. Monochromatic base with precise accent color pops (electric teal)
3. Strict typographic hierarchy using tabular figures for metrics
4. Functional asymmetry: sidebar narrow, results expansive, detail panel anchored

**Color Philosophy**: Near-black (#0E1117) background evokes depth and focus. Electric teal (#00D4C8) for interactive elements signals precision and intelligence. Muted slate grays for secondary text. The palette communicates "serious research tool" not "consumer app."

**Layout Paradigm**: Three-column fixed layout. Left sidebar 220px fixed. Center scrollable results list. Right detail panel 320px fixed. No hero sections — pure utility layout.

**Signature Elements**:
1. Thin 1px teal left-border accent on active/hovered cards
2. Monospace font for relevance scores and citation counts
3. Subtle scanline texture on the sidebar background

**Interaction Philosophy**: Hover reveals additional metadata. Click selects and populates right panel. Keyboard-navigable. Transitions are fast (150ms) — no decorative delays.

**Animation**: Subtle fade-in for search results (staggered 30ms per card). Right panel slides in from right on first load. Score numbers count up on appear.

**Typography System**:
- Display/Logo: Space Grotesk 700
- Body: Inter 400/500
- Metrics/Scores: JetBrains Mono 600
- Hierarchy: 13px labels → 15px body → 18px names → 24px section headers

</idea>
</response>

<response>
<probability>0.06</probability>
<idea>

**Design Movement**: Warm Academic — editorial design meets research journal aesthetics (think Nature journal + Notion)

**Core Principles**:
1. Warm off-white background (#F8F5F0) for extended reading comfort
2. Serif display type for researcher names and section headers
3. Generous line-height and breathing room between cards
4. Subtle paper-like texture throughout

**Color Philosophy**: Warm cream base (#F8F5F0) with dark charcoal text (#1A1A1A). Deep burgundy (#8B1A3A) as the primary accent — scholarly and authoritative. Muted sage green for tags. The palette says "trusted academic resource."

**Layout Paradigm**: Three-column with a slightly wider center column. Cards use generous padding with subtle drop shadows. Right panel has a distinct warm-white background with a thin left border.

**Signature Elements**:
1. Serif font (Playfair Display) for researcher names
2. Pill-shaped keyword tags in sage green
3. Thin horizontal rules between sections

**Interaction Philosophy**: Deliberate, unhurried interactions. Hover states use background color shifts rather than borders. Selection feels like "opening a file."

**Animation**: Gentle fade transitions (200ms ease-out). Cards slide up slightly on hover. Right panel cross-fades content on researcher change.

**Typography System**:
- Display: Playfair Display 700 (researcher names, headings)
- Body: Source Serif 4 400/600
- UI Labels: DM Sans 400/500
- Metrics: DM Mono 600

</idea>
</response>

<response>
<probability>0.08</probability>
<idea>

**Design Movement**: Precision Dark UI — inspired by Bloomberg Terminal and Figma's dark mode. Dense, professional, zero-waste.

**Core Principles**:
1. True dark (#111318) with layered surface elevations
2. Blue-violet accent (#6366F1) for primary actions and highlights
3. Compact card design — maximum information per viewport height
4. Sharp corners and thin borders over rounded softness

**Color Philosophy**: Deep navy-black base with subtle blue-tinted surfaces. Indigo/violet accent for interactive states. White text at 90% opacity for primary, 60% for secondary. The palette communicates precision and modernity.

**Layout Paradigm**: Three-column fixed layout. Sidebar 240px. Center results 55% width. Right panel 320px. Compact card rows with 12px gaps.

**Signature Elements**:
1. Left colored bar (indigo) on selected/active researcher cards
2. Glowing score badge (indigo background, white text)
3. Thin separator lines between sidebar sections

**Interaction Philosophy**: Immediate feedback — hover states appear in <100ms. Active states use filled backgrounds. The UI responds like a professional tool.

**Animation**: Minimal — 120ms transitions only. Results list fades in. Right panel content cross-fades. No bouncy or elastic animations.

**Typography System**:
- Logo: Space Grotesk 700
- Researcher Names: Sora 600
- Body: Geist 400/500
- Scores: Geist Mono 700

</idea>
</response>

---

## Selected Approach
**Precision Dark UI** — Dense, professional dark interface with blue-violet accents, layered surfaces, and compact information density. This best matches the original screenshot's dark aesthetic while elevating it with sharper typography and more refined interactions.
