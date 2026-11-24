# Benchmark-Bericht

_erzeugt 2026-11-24 05:19_

| Schritt | Rolle | Suite | Seeds | Board | Datum | Modell |
|---|---|---|---|---|---|---|
| chemie-nodemcu | Baseline | chemie v1 | 1 | ja | 2026-11-23 | `7de799937683` |
| nodemcu | Schritt | allgemein v1 | 1 | nein | 2026-11-23 | `ef7ab9be0ff6` |

## Zusammenfassung

- nodemcu gegen chemie-nodemcu: 1 besser, 0 schlechter, 1 unverändert (andere Suite, nur Ressourcen vergleichbar)

## Kennzahlen

| Gruppe | KPI | Richtung | chemie-nodemcu | nodemcu | Δ nodemcu zu chemie-nodemcu | Schwelle |
|---|---|---|---|---|---|---|
| Faktenqualität | **F1** richtig, ungesehene Formulierungen (%) | ↑ | 38.5 | 88.6 | nicht vergleichbar |  |
| Faktenqualität | **F2** falsche Fakten (%) | ↓ | 17.8 | 6.3 | nicht vergleichbar |  |
| Faktenqualität | **F3** richtig abgewiesen (%) | ↑ | 62.9 | 0.0 | nicht vergleichbar |  |
| Faktenqualität | **F4** fälschlich abgewiesen (%) | ↓ | 7.0 | 0.0 | nicht vergleichbar |  |
| Faktenqualität | **F5** Kurzarbeit (%) | ↑ | 37.7 | nicht gemessen | nicht gemessen |  |
| Faktenqualität | **F6** beantwortbare Fakten | ↑ | 1.404 | 287 | nicht vergleichbar |  |
| Tempo | **T1** erstes Zeichen, getippt (ms) | ↓ | 178 | nicht gemessen | nicht gemessen |  |
| Tempo | **T2** Zeichen/s | ↑ | 4.8 | nicht gemessen | nicht gemessen |  |
| Tempo | **T3** Zeichen/s bei vollem Kontext | ↑ | 3.8 | nicht gemessen | nicht gemessen |  |
| Ressourcen | **R1** Arena (B) | ↓ | 35.504 | nicht gemessen | nicht gemessen |  |
| Ressourcen | **R2** Flash Modell (B) | ↓ | 601.412 | 601.404 | -8 (besser) | exakt |
| Ressourcen | **R3** Flash Wissen (B) | ↓ | 0 | 0 | 0 (unverändert) | exakt |
| Ressourcen | **R4** Bytes pro Fakt | ↓ | 428.4 | 2095.5 | nicht vergleichbar |  |
| Sprache | **S1** Bit pro Zeichen | ↓ | 13.314 | 13.505 | nicht vergleichbar |  |
| Sprache | **S2** nutzbarer Kontext (Zeichen) | ↑ | 0 | 0 | nicht vergleichbar |  |
| Sprache | **S3** Grammatik ok (%) | ↑ | 100 | 65 | nicht vergleichbar |  |

## Budget

| Schritt | Posten | Wert (B) | Grenze (B) | Status | Regel |
|---|---|---|---|---|---|
| chemie-nodemcu | Modell (Flash) | 601.412 | 619.315 | ok | Modellbereich − 10 % |
| chemie-nodemcu | Arena (RAM) | 35.504 | 35.840 | ok | ≤ 35 KB und ≥ 10 % Reserve |
| chemie-nodemcu | Firmware | 293.232 | 324.403 | ok | Firmwarebereich − 10 % |
| nodemcu | Modell (Flash) | 601.404 | 619.315 | ok | Modellbereich − 10 % |
| nodemcu | Arena (RAM) | 35.504 | 35.840 | ok | ≤ 35 KB und ≥ 10 % Reserve |
