# Squat-Press Wiki

A plain-text knowledge base following **Andrej Karpathy's LLM-wiki method**: raw
inputs are treated as immutable *source code*; the distilled **compiled pages**
are derived from them (the LLM is the compiler). No RAG, no embeddings — just
markdown fed to a long-context model.

## Layers

- **`sources/`** — immutable ground truth: manual extracts, datasheets, cited
  literature, research findings. Treat as append-only: don't edit a source to
  "fix" a conclusion — add a new source and re-compile.
- **compiled pages** (this level) — task-ready docs *synthesised from* `sources/`.
  Each page lists the sources it was compiled from; regenerate when sources change.

## Pages

| Compiled page | Compiled from |
|---|---|
| [peristaltic-pump.md](peristaltic-pump.md) — liquid-reward dosing subsystem | [kamoer-modbus-driver](sources/kamoer-modbus-driver.md), [kamoer-pump-tubing](sources/kamoer-pump-tubing.md), [mouse-reward-dosing](sources/mouse-reward-dosing.md) |
