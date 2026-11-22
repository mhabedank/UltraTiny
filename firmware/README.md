# Firmware (ESP-IDF)

> **Altbestand.** Das Zielboard ist seit Constitution v2.0.0 die NodeMCU (ESP8266), siehe
> [`firmware-nodemcu/`](../firmware-nodemcu/). Diese ESP32-Firmware bleibt im Repository und
> wird in der CI weiter gebaut, aber nicht weiterentwickelt.

Dünne Plattformschicht für den klassischen ESP32. Die gesamte Logik (Modell, Konsole) liegt im
portablen [`runtime/`](../runtime), das hier als ESP-IDF-Komponente eingebunden wird.

| Datei | Aufgabe |
|-------|---------|
| `main/main.c` | Start, statische Arena (96 KB), Konsolen-Schleife auf Kern 1 |
| `main/model_partition.c` | `model`-Partition finden und per `esp_partition_mmap` einblenden |
| `main/console_uart.c` | UART0 (115200 8N1) als I/O für die Konsole |
| `partitions.csv` | nvs, phy, factory (1 MB), model (2 MB @ 0x110000) |
| `sdkconfig.defaults` | Bluetooth aus, 240 MHz, Performance-Optimierung, Watchdog für Kern 1 aus |

## Bauen und flashen

```bash
. $IDF_PATH/export.sh            # ESP-IDF v5.4
idf.py set-target esp32
idf.py build
idf.py -p <PORT> flash           # Firmware + Partitionstabelle
make -C .. flash-model PORT=<PORT> MODEL=models/starter.utny
idf.py -p <PORT> monitor
```

WLAN wird nie initialisiert, Bluetooth ist nicht einkompiliert. Ein fehlendes oder beschädigtes
Modell führt zu `FEHLER: Modell ungültig (…)`; `/hilfe` und `/info` funktionieren weiter, das Board
startet nicht neu.
