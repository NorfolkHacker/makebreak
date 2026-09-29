/* esp32-probe-sniffer.ino — MAKE / BREAK issue #05: "Sniff the air"
 *
 * Passive Wi-Fi listener for the ESP32. Receive-only: it never transmits.
 * Prints the "probe requests" nearby devices broadcast — the network names
 * they remember and call out for. Listen on your own kit and your own space;
 * don't collect, keep, or act on anyone else's data.
 *
 * Board: any ESP32 dev module. Arduino IDE -> Tools -> Board -> "ESP32 Dev Module".
 * Open the Serial Monitor at 115200 baud.
 * Full walkthrough: https://makebreak.co.uk/issues/05.html
 */
#include <WiFi.h>
#include "esp_wifi.h"

void onPacket(void *buf, wifi_promiscuous_pkt_type_t type) {
  auto *pkt = (wifi_promiscuous_pkt_t *)buf;
  const uint8_t *f = pkt->payload;

  if (f[0] != 0x40) return;            // 0x40 = a probe request, ignore the rest

  const uint8_t *mac = f + 10;         // address 2 = who's asking
  uint8_t len = f[25];                 // length of the network name they want
  char ssid[33] = {0};
  for (int i = 0; i < len && i < 32; i++) ssid[i] = f[26 + i];

  Serial.printf("%4d dBm  %02X:%02X:%02X:%02X:%02X:%02X  wants: \"%s\"\n",
    pkt->rx_ctrl.rssi, mac[0], mac[1], mac[2], mac[3], mac[4], mac[5],
    len ? ssid : "(anything out there?)");
}

void setup() {
  Serial.begin(115200);
  WiFi.mode(WIFI_STA);
  esp_wifi_set_promiscuous(true);
  wifi_promiscuous_filter_t filter = { .filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT };
  esp_wifi_set_promiscuous_filter(&filter);
  esp_wifi_set_promiscuous_rx_cb(&onPacket);
}

void loop() {                          // hop channels so we hear the whole room
  for (uint8_t ch = 1; ch <= 13; ch++) {
    esp_wifi_set_channel(ch, WIFI_SECOND_CHAN_NONE);
    delay(300);
  }
}
