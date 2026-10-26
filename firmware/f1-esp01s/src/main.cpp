// F1 rev3 carrier board - ESP-01S (ESP8266) minimal bring-up firmware.
//
// Hardware facts taken from the frozen rev3 netlist (docs/evidence/f1-c-2026-10-22/):
//   U101 = Ai-Thinker ESP-01S, 8-pin module (ESP8266, 1MB flash).
//   J102 = 4-pin debug header: pin1=3V3, pin2=TXD, pin3=RXD, pin4=GND.
//   D101 is a power indicator driven from 3V3 through R106; it is NOT on a GPIO.
//   SW101 = RST, SW102 = IO0 (boot/download strap). EN/RST/IO0/IO2 all have 10k pull-ups.
//   There is no user LED or user button on a GPIO in this design.
//
// So this sketch deliberately does the minimum that can be verified on a real board
// without inventing peripherals: a UART heartbeat, chip identity, and a Wi-Fi scan.
// Wi-Fi credentials are NOT hardcoded; the scan only needs the radio.
//
// Build:  pio run
// Flash:  pio run -t upload --upload-port COMx
// Monitor: pio device monitor -p COMx -b 115200

#include <Arduino.h>
#include <ESP8266WiFi.h>

#ifndef F1_FW_VERSION
#define F1_FW_VERSION "dev"
#endif
#ifndef F1_BOARD_REV
#define F1_BOARD_REV "unknown"
#endif

static const uint32_t HEARTBEAT_MS = 2000;
static const uint32_t SCAN_MS = 15000;

static uint32_t lastBeat = 0;
static uint32_t lastScan = 0;
static bool radioReady = false;

static void printIdentity() {
  Serial.printf("[F1] board=%s fw=%s\n", F1_BOARD_REV, F1_FW_VERSION);
  Serial.printf("[F1] chip_id=%08X flash=%uKB sdk=%s\n",
                ESP.getChipId(), ESP.getFlashChipSize() / 1024,
                ESP.getSdkVersion());
  Serial.printf("[F1] cpu=%uMHz free_heap=%u\n",
                ESP.getCpuFreqMHz(), ESP.getFreeHeap());
}

static void scanNetworks() {
  if (!radioReady) {
    // Wi-Fi station mode with a placeholder SSID is enough to scan; no secrets.
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    delay(100);
    radioReady = true;
  }
  int found = WiFi.scanNetworks(/*async=*/false, /*show_hidden=*/false);
  if (found < 0) {
    Serial.printf("[F1][FAULT] wifi_scan failed code=%d\n", found);
    return;
  }
  int best = -127;
  for (int i = 0; i < found; i++) {
    int rssi = WiFi.RSSI(i);
    if (rssi > best) best = rssi;
  }
  Serial.printf("[F1] scan aps=%d best_rssi=%d\n", found, best);
  WiFi.scanDelete();
}

void setup() {
  Serial.begin(115200);
  delay(200);
  printIdentity();
  Serial.println("[F1] boot ok; heartbeat is 1 line / 2 s");
}

void loop() {
  uint32_t now = millis();
  if (now - lastBeat >= HEARTBEAT_MS) {
    lastBeat = now;
    Serial.printf("[F1] alive uptime_ms=%lu heap=%u\n",
                  static_cast<unsigned long>(now), ESP.getFreeHeap());
  }
  if (now - lastScan >= SCAN_MS) {
    lastScan = now;
    scanNetworks();
  }
  delay(10);
}
