#!/usr/bin/env python3
"""Back-of-envelope estimates for research/2026-11-hardware/README.md.

Only the ESP8266 baseline is measured (bench/results/baseline.md). Every other number follows
from the assumptions in this file and is good to a factor of 2 to 3 at best. Change an
assumption, run again, compare. No dependencies:

    python3 research/2026-11-hardware/abschaetzung.py
"""

from __future__ import annotations

# --- Today's model (header of models/nodemcu.utny) ------------------------------------------
# 4 layers x 128, multi-query attention (4 heads of 32, one KV head), d_ff 384, vocab 92,
# context 104, int8 weights with one scale per row.
LAYERS, D, HEAD_DIM, HEADS, D_FF, VOCAB, CTX = 4, 128, 32, 4, 384, 92, 104

# --- Measured on the board (bench/results/baseline.md, chemie-nodemcu, NodeMCU v2) -----------
ESP_HZ = 160e6
T2_MEASURED = 4.8  # chars/s, normal answer
T3_MEASURED = 3.8  # chars/s, full context

# --- Assumptions (not measured) ---------------------------------------------------------------
ESP_POWER_W = 0.1  # ESP8266 at 160 MHz plus SPI flash, radio off
CACHE_LINE_B = 32  # ESP8266 flash cache line
LINE_OVERHEAD_CLK = 24  # command, address, dummy clocks per cache line fill
ESP_CYCLES_PER_TERNARY_WEIGHT = (8, 4)  # (simple loop, tuned loop in IRAM)

TERNARY_BITS = 1.6  # 5 trits per byte (3^5 = 243 <= 256)
W1 = 0.6e6  # ternary parameters, same count as today
W2 = 2.4e6  # ternary parameters, same flash as today's int8 model

# name, clock Hz, cores, cycles per ternary weight per core (slow, fast), power W, SRAM bytes
MCUS = [
    ("RP2350", 150e6, 2, (3.0, 1.5), 0.06, 520 * 1024),
    ("ESP32-S3", 240e6, 2, (1.5, 0.5), 0.15, 512 * 1024),
]

# iCE40 UP5K: 4 SPRAM blocks x 16 bit = 64 bit per clock = 8 bytes = 40 trits (base-3 packed)
FPGA_TRITS_PER_CLK = 40
FPGA_HZ = (24e6, 48e6)
FPGA_POWER_W = (0.005, 0.015)
FPGA_SRAM_B = 128 * 1024

QSPI_BYTES_PER_S = 25e6  # quad SPI, 50 MHz, single data rate
QSPI_POWER_W = (0.033, 0.050)  # NOR flash read, 10-15 mA at 3.3 V

ASIC_TRITS_PER_CLK = 256
ASIC_HZ = 200e6

# Horowitz, ISSCC 2014, 45 nm: 64-bit read 8 KB 10 pJ, 32 KB 20 pJ, 1 MB 100 pJ; 8-bit add 0.03 pJ
PJ_PER_BIT_SRAM_SMALL = 20 / 64  # banks around 32 KB
PJ_PER_BIT_SRAM_LARGE = 100 / 64  # arrays around 1 MB
PJ_PER_ADD8 = 0.03

COIN_CELL_J = 2400  # CR2032, about 225 mAh at 3 V


def ternary_bytes(params: float) -> float:
    return params * TERNARY_BITS / 8


def spi_bytes_per_s(bits_per_clk: int, hz: float) -> float:
    clk = CACHE_LINE_B * 8 / bits_per_clk + LINE_OVERHEAD_CLK
    return CACHE_LINE_B / (clk / hz)


def serial(*rates: float) -> float:
    """Steps/s when the stages do not overlap (the CPU stalls on every cache miss)."""
    return 1 / sum(1 / r for r in rates)


def main() -> None:
    mac_lin = LAYERS * (D * D + 2 * D * HEAD_DIM + D * D + 2 * D * D_FF) + VOCAB * D
    mac_att = LAYERS * HEADS * CTX * HEAD_DIM * 2
    print("## Heutiges Modell auf dem ESP8266")
    print(f"MAC pro Zeichen: {mac_lin:,} linear + bis zu {mac_att:,} Attention (voller Kontext)")
    lo = ESP_HZ / (T2_MEASURED * (mac_lin + mac_att))
    hi = ESP_HZ / (T2_MEASURED * mac_lin)
    print(f"Takte pro MAC bei T2 {T2_MEASURED}: {lo:.0f}-{hi:.0f}")
    print(f"Takte pro MAC bei T3 {T3_MEASURED}: {ESP_HZ / (T3_MEASURED * (mac_lin + mac_att)):.0f}")
    dio40 = spi_bytes_per_s(2, 40e6)
    qio80 = spi_bytes_per_s(4, 80e6)
    flash_cap = dio40 / mac_lin  # int8: one byte per weight
    rest_s = 1 / T2_MEASURED - 1 / flash_cap
    print(f"Flash DIO 40 MHz: {dio40 / 1e6:.1f} MB/s -> höchstens {flash_cap:.1f} Zeichen/s")
    print(f"Flash QIO 80 MHz: {qio80 / 1e6:.1f} MB/s -> höchstens {qio80 / mac_lin:.1f} Zeichen/s")
    print(
        f"Anteil Flash an der Zeit pro Zeichen: {(1 / flash_cap) * T2_MEASURED:.0%}; "
        f"Rest ~{rest_s * ESP_HZ / mac_lin:.0f} Takte pro MAC"
    )
    e_today = ESP_POWER_W / T2_MEASURED
    print(f"Energie pro Zeichen (Annahme {ESP_POWER_W} W): {fmt_j(e_today)}")

    rows = []
    for params, tag in ((W1, "0,6 Mio."), (W2, "2,4 Mio.")):
        b = ternary_bytes(params)
        slow = serial(dio40 / b, ESP_HZ / (params * ESP_CYCLES_PER_TERNARY_WEIGHT[0]))
        fast = serial(qio80 / b, ESP_HZ / (params * ESP_CYCLES_PER_TERNARY_WEIGHT[1]))
        rows.append(("ESP8266 ternär, optimiert", tag, slow, fast, ESP_POWER_W, ESP_POWER_W))
        for name, hz, cores, cpw, power, sram in MCUS:
            fits = "" if b < 0.8 * sram else " (knapp im RAM)" if b < sram else " (passt nicht)"
            r_slow = hz * cores / (params * cpw[0])
            r_fast = hz * cores / (params * cpw[1])
            rows.append((f"{name}, Gewichte im RAM{fits}", tag, r_slow, r_fast, power, power))
        if b <= FPGA_SRAM_B:
            r = [FPGA_TRITS_PER_CLK * hz / params for hz in FPGA_HZ]
            rows.append(("FPGA iCE40 UP5K, Chip-RAM", tag, r[0], r[1], *FPGA_POWER_W))
        q = QSPI_BYTES_PER_S / b
        rows.append(("FPGA/Tiny Tapeout, QSPI-Flash", tag, q, q, *QSPI_POWER_W))
        pj_bit = PJ_PER_BIT_SRAM_SMALL if b <= 256 * 1024 else PJ_PER_BIT_SRAM_LARGE
        e_asic = b * 8 * pj_bit * 1e-12 + params * PJ_PER_ADD8 * 1e-12
        r = ASIC_TRITS_PER_CLK * ASIC_HZ / params
        rows.append(("Eigener Chip mit SRAM (45 nm)", tag, r, r, e_asic * r, e_asic * r))

    print("\n## Plattformen (ternäres rekurrentes Modell)")
    print("| Plattform | Parameter | Schritte/s | Energie pro Schritt |")
    print("|---|---|---|---|")
    typical = {"ESP8266 heute": e_today}  # geometric middle of each 0,6-Mio. energy range
    for name, tag, r0, r1, p0, p1 in rows:
        e = sorted((p0 / r0, p1 / r1, p0 / r1, p1 / r0))
        print(f"| {name} | {tag} | {r0:,.0f}-{r1:,.0f} | {fmt_j(e[0])}-{fmt_j(e[-1])} |")
        if params_tag_is_w1(tag):
            typical.setdefault(name, (e[0] * e[-1]) ** 0.5)

    print("\n## Speicher ist teuer, Rechnen nicht (pJ pro Bit bzw. pro Addition)")
    qspi_pj = QSPI_POWER_W[0] / (QSPI_BYTES_PER_S * 8) * 1e12
    print(
        f"8-Bit-Addition {PJ_PER_ADD8} | SRAM klein {PJ_PER_BIT_SRAM_SMALL:.2f} | "
        f"SRAM 1 MB {PJ_PER_BIT_SRAM_LARGE:.2f} | QSPI-Flash ~{qspi_pj:.0f}"
    )

    print("\n## Knopfzelle CR2032, ein Schritt pro Sekunde rund um die Uhr (ohne Schlafstrom)")
    for name, e in typical.items():
        days = COIN_CELL_J / (e * 86400)
        print(f"{name}: {fmt_j(e)} pro Schritt -> {days:,.1f} Tage ({days / 365:,.1f} Jahre)")

    print("\n## Mehrere Kanäle teilen sich jedes gelesene Gewicht (QSPI-Flash, 0,6 Mio.)")
    e_flash = QSPI_POWER_W[0] / (QSPI_BYTES_PER_S / ternary_bytes(W1))
    for n in (1, 4, 8, 16):
        print(f"{n:2d} Kanäle: {fmt_j(e_flash / n)} Flash-Energie pro Messwert")


def params_tag_is_w1(tag: str) -> bool:
    return tag == "0,6 Mio."


def fmt_j(j: float) -> str:
    if j >= 1e-3:
        return f"{j * 1e3:.1f} mJ"
    if j >= 1e-6:
        return f"{j * 1e6:.1f} µJ"
    return f"{j * 1e9:.0f} nJ"


if __name__ == "__main__":
    main()
