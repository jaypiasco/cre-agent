# CRE-Agent AP Workbench — Design System (`DESIGN.md`)

## Visual Philosophy
- **Institutional Clarity**: Crisp light alabaster & slate surfaces (`#f8fafc`, `#ffffff`) paired with deep navy ink (`#0f172a`) for high-density financial & AP review workflows.
- **Semantic Audit Signals**:
  - `VALID`: Emerald (`#059669` / `#ecfdf5` tint, `#a7f3d0` border)
  - `NEEDS_REVIEW`: Amber (`#d97706` / `#fffbeb` tint, `#fde68a` border)
  - `ERROR / OFFLINE`: Rose (`#e11d48` / `#fff1f2` tint, `#fecdd3` border)
- **Financial Precision**: Monospace (`Geist Mono`) with `tabular-nums` for all currency amounts, invoice numbers, GL codes, and Langfuse trace IDs.

## Typography
- **Display & Body**: `Geist` (`--font-geist-sans`)
- **Monospace / Financial**: `Geist Mono` (`--font-geist-mono`)

## Layout & Spacing
- Sticky top status bar (`max-w-7xl`) with live API health and Langfuse observability indicators.
- Asymmetric 2-column workbench: 360px ingestion & sample-preset rail on the left; validation gate, extracted line-item table, GL recommendation, and HITL Yardi export controls on the right.
- Consistent `0.625rem` (`10px`) border radius across cards, inputs, and buttons (`ROUND_EIGHT`).
