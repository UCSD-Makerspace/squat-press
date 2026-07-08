# SOURCE — Kamoer Pump & Tubing

> Immutable extract. Primary: *KMC Multi-channel Peristaltic Pump Product Manual*
> (CPBZ-KMC-01, A1, 2024-09-02) and KPMP10 product listing / datasheet, Kamoer
> Fluid Tech. Tube dimensional research cross-checked against Saint-Gobain /
> Cole-Parmer PharMed BPT datasheets (2026-07).

## Pump
- **Kamoer KPMP10** (module designation **KPM10-ST-A2**; ST = 24 V stepper). Low-flow, **0–5.9 mL/min**, 4-roller head. Motor life ~6000 h.
- Recommended max working speed 100 rpm; brief bursts ≤ 120 rpm.

## Reference flow @ 100 rpm (pure water, 20 °C) — materials MED55 & P60 identical
| Tube ID × OD (mm) | Wall (mm) | Flow (mL/min) | µL/rev (=flow×10) |
|---|---|---|---|
| 0.25 × 2.05 | 0.90 | 0.135 | 1.35 |
| 0.51 × 2.31 | 0.90 | 0.85 | 8.5 |
| 0.89 × 2.59 | 0.85 | 2.25 | 22.5 |
| 1.02 × 2.72 | 0.85 | 3.05 | 30.5 |
| 1.30 × 3.00 | 0.85 | 4.45 | 44.5 |
| 1.52 × 3.22 | 0.85 | 5.90 | 59.0 |

- **µL per revolution = (mL/min at 100 rpm) × 10.** Head grips OD/wall, not ID.
- The stock KPMP10 tube is **1.52 × 3.22 mm** (= 1/16" ID × 1/8" OD).

## Tube materials
- **MED55** — medical-grade tube (Kamoer). **P60 ("Perx P60")** — BPT-class TPE: long life, sterilizable, acid/alkali & oxidation resistant, biocompatible.
- Kamoer rates BPT-class ~1000 h vs silicone ~200 h peristaltic life.
- Kamoer in-stock BPT part numbers (sheet spec): 0.51×2.31 = 14.08.0063, 1.02×2.72 = 14.08.0064, 1.52×3.22 = 14.08.0065; other sizes custom.

## Generic equivalent chosen for this rig
- **PharMed BPT 1/16" ID × 1/8" OD** (1.588 × 3.175 mm, 0.79 mm wall, 64 Shore A). Biocompatible, USP Class VI, plasticizer-free; buy 25 ft coil.
- **Marginal fit:** wall ~0.06 mm thinner than the 0.85 mm OEM → can under-occlude. Verify no free-siphon at rest (add an anti-siphon loop; keep reservoir at/below spout) and re-calibrate µL/rev after any tube change.
- Do **not** use Kamoer FX-STP 3.2 × 6.4 mm tube — that is the larger aquarium-dosing head.
