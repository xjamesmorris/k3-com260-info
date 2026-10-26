// SPDX-License-Identifier: GPL-2.0-only
// k3ctl.ino — USB "button pusher" for the Firefly-carrier K3-CoM260 header.
// Only reset has a maintainer-reported hardware test; other functions are unverified.
//
// Target: ABRobot "ESP32-C3 0.42 OLED" board (ESP32-C3FH4, native USB CDC,
// 72x40 SSD1306 on GPIO5/6). K3CTL_OLED=0 disables the display; that variant
// and other ESP32-C3 boards have not been validated here.
//
// Build (arduino-esp32 core 3.x):
//   Board "ESP32C3 Dev Module", USB CDC On Boot: Enabled, Flash 4MB.
//   Library: U8g2 (only when K3CTL_OLED=1).
//
// Wiring — every control line is OPEN-DRAIN towards the K3: released = input
// (Hi-Z), asserted = driven low. Verify the actual header and voltage levels;
// this does not establish startup/back-feed safety. See README.md before wiring.
//
//   ESP32-C3        K3 12-pin header
//   GPIO3     ----> pin 8   PMIC_RST_OUTn   (SYS_RST button)
//   GPIO4     ----> pin 10  FORCE_RECOVERY  (FC_REC button)
//   GPIO7     ----> pin 12  SLEEP/WAKE      (power button)
//   GND       ----- pin 9   GND
//   GPIO10    <---- optocoupler across pins 2/1 (PC_LED+/-), see "Power sense"
//                   below. Treat PC_LED+ as potentially 5 V; never wire it directly.
//
// Header controls avoid 2/8/9 (strapping; 8 is the local LED), 5/6 (OLED),
// 18/19 (USB D±), and 20/21 (UART0).
//
// Protocol (USB CDC, 8N1, baud ignored): one ASCII line in, exactly one line
// out beginning with "OK" or "ERR" (blank lines are ignored). Multi-step
// timing runs on the ESP, not the host; fault behavior remains unverified.
//
//   ping                 -> OK pong k3ctl <ver>
//   status               -> OK status rst=0 fcrec=0 pwr=0 k3=on|off|n/a up=<ms>
//   reset                -> tap RST
//   recovery             -> hold FC_REC, tap RST, release FC_REC  (BootROM download mode)
//   power [ms]           -> tap SLEEP/WAKE (default 300 ms)
//   press <line> [ms]    -> tap rst|fcrec|pwr for <ms> (default 200, max 15000)
//   hold <line>          -> assert (30 s release timer, serviced in the main loop)
//   release <line>|all   -> release
//   help                 -> OK help ...
//
#include <Arduino.h>

#ifndef K3CTL_OLED
#define K3CTL_OLED 1
#endif
#if K3CTL_OLED
#include <Wire.h>
#include <U8g2lib.h>
#endif

#define K3CTL_VERSION "1.0"

// ---- pins -------------------------------------------------------------------
static const int PIN_RST   = 3;
static const int PIN_FCREC = 4;
static const int PIN_PWR   = 7;
static const int PIN_LED   = 8;    // on-board blue LED, active-low
static const int PIN_SDA   = 5;    // OLED
static const int PIN_SCL   = 6;    // OLED
// Power sense (optional). Treat PC_LED+ as potentially 5 V. The ESP32-C3 is
// NOT 5 V tolerant; never connect the header signal directly. Untested designs:
//   K3_SENSE_INVERT=1  optocoupler across the LED pair (PC817: anode <- pin 2
//                      via 1 kΩ, cathode -> pin 1; emitter -> ESP GND,
//                      collector -> GPIO10). Reads LOW as K3 on; confirm the
//                      actual header's drive and switching behavior.
//   K3_SENSE_INVERT=0  divider 10 kΩ from pin 2 to GPIO10, 15 kΩ GPIO10 to GND
//                      (5 V -> 3.0 V). Only valid if pin 2 itself drops when
//                      the board is off. Reads HIGH when the K3 is on.
#ifndef K3_SENSE_PIN
#define K3_SENSE_PIN -1            // set to 10 to enable
#endif
#ifndef K3_SENSE_INVERT
#define K3_SENSE_INVERT 1          // default: optocoupler wiring
#endif

// ---- timing (ms) ------------------------------------------------------------
static const uint32_t TAP_MS        = 200;    // default button tap
static const uint32_t PWR_TAP_MS    = 300;    // power button tap
static const uint32_t FCREC_LEAD_MS = 300;    // FC_REC settled before RST
static const uint32_t FCREC_TAIL_MS = 500;    // FC_REC held after RST released
static const uint32_t MAX_PRESS_MS  = 15000;  // longest tap accepted
static const uint32_t HOLD_MAX_MS   = 30000;  // safety net for 'hold'
static const uint32_t DISPLAY_MS    = 1000;   // OLED refresh period

// ---- state ------------------------------------------------------------------
struct Line {
  const char *name;
  int pin;
  bool held;          // asserted by 'hold', subject to the auto-release timer
  uint32_t since;
};

static Line lines[] = {
  {"rst",   PIN_RST,   false, 0},
  {"fcrec", PIN_FCREC, false, 0},
  {"pwr",   PIN_PWR,   false, 0},
};
static const size_t NLINES = sizeof(lines) / sizeof(lines[0]);

static char lastAction[20] = "idle";
static char rxbuf[64];
static size_t rxlen = 0;
static bool rxOverflow = false;

#if K3CTL_OLED
// 72x40 panel; the ER variant maps the visible area without manual offsets.
static U8G2_SSD1306_72X40_ER_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE, PIN_SCL, PIN_SDA);
#endif

// ---- open-drain helpers -----------------------------------------------------
// Release = plain input with pulls disabled (arduino-esp32 INPUT = floating).
// Assert = output register preloaded low *before* enabling the driver, so the
// pad never emits a high glitch on the way to low.
static void lineRelease(Line &l) {
  pinMode(l.pin, INPUT);
  l.held = false;
}

static void lineAssert(Line &l) {
  digitalWrite(l.pin, LOW);
  pinMode(l.pin, OUTPUT);
  l.since = millis();
}

static bool lineAsserted(const Line &l) {
  return l.held;   // the only way a line is ever low is us driving it
}

static void ledRefresh() {
  bool any = false;
  for (size_t i = 0; i < NLINES; i++) any |= lines[i].held;
  digitalWrite(PIN_LED, any ? LOW : HIGH);
}

static void setAction(const char *s) {
  strncpy(lastAction, s, sizeof(lastAction) - 1);
  lastAction[sizeof(lastAction) - 1] = '\0';
}

// Blocking taps keep timing on the ESP, but delay servicing the hold timer.
static void linePress(Line &l, uint32_t ms) {
  lineAssert(l);
  l.held = true; ledRefresh();
  delay(ms);
  lineRelease(l);
  ledRefresh();
}

static Line *findLine(const char *name) {
  if (!name) return nullptr;
  for (size_t i = 0; i < NLINES; i++)
    if (strcmp(lines[i].name, name) == 0) return &lines[i];
  return nullptr;
}

// ---- K3 power sense ---------------------------------------------------------
static const char *k3PowerState() {
#if K3_SENSE_PIN >= 0
  bool level = digitalRead(K3_SENSE_PIN);
  return (K3_SENSE_INVERT ? !level : level) ? "on" : "off";
#else
  return "n/a";
#endif
}

// ---- display ----------------------------------------------------------------
static void display() {
#if K3CTL_OLED
  char buf[24];
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_5x8_tr);
  u8g2.drawStr(0, 8, "k3ctl v" K3CTL_VERSION);
  snprintf(buf, sizeof(buf), "K3: %s", k3PowerState());
  u8g2.drawStr(0, 18, buf);
  snprintf(buf, sizeof(buf), "> %s", lastAction);
  u8g2.drawStr(0, 28, buf);
  snprintf(buf, sizeof(buf), "%c%c%c  %lus",
           lines[0].held ? 'R' : '-', lines[1].held ? 'F' : '-',
           lines[2].held ? 'P' : '-', (unsigned long)(millis() / 1000));
  u8g2.drawStr(0, 38, buf);
  u8g2.sendBuffer();
#endif
}

// ---- commands ---------------------------------------------------------------
static void cmdStatus() {
  Serial.printf("OK status rst=%d fcrec=%d pwr=%d k3=%s up=%lu ver=" K3CTL_VERSION "\n",
                lineAsserted(lines[0]), lineAsserted(lines[1]), lineAsserted(lines[2]),
                k3PowerState(), (unsigned long)millis());
}

static void cmdRecovery() {
  // Intended running-board recovery sequence; not hardware-tested.
  setAction("recovery"); display();
  lineAssert(lines[1]); lines[1].held = true; ledRefresh();
  delay(FCREC_LEAD_MS);
  linePress(lines[0], TAP_MS);
  delay(FCREC_TAIL_MS);
  lineRelease(lines[1]); ledRefresh();
  Serial.println("OK recovery");
}

static bool parseMs(const char *s, uint32_t dflt, uint32_t &out) {
  if (!s) { out = dflt; return true; }
  char *end = nullptr;
  unsigned long v = strtoul(s, &end, 10);
  if (end == s || *end != '\0' || v == 0 || v > MAX_PRESS_MS) return false;
  out = (uint32_t)v;
  return true;
}

static void handle(char *cmdline) {
  char *save = nullptr;
  const char *cmd  = strtok_r(cmdline, " \t", &save);
  const char *arg1 = strtok_r(nullptr, " \t", &save);
  const char *arg2 = strtok_r(nullptr, " \t", &save);
  uint32_t ms;

  if (!cmd || !*cmd) return;  // blank line: stay silent (keeps 'pong' pairing exact)

  if (!strcmp(cmd, "ping")) {
    Serial.println("OK pong k3ctl " K3CTL_VERSION);
  } else if (!strcmp(cmd, "status")) {
    cmdStatus();
  } else if (!strcmp(cmd, "help")) {
    Serial.println("OK help ping|status|reset|recovery|power [ms]|press <rst|fcrec|pwr> [ms]|hold <line>|release <line|all>");
  } else if (!strcmp(cmd, "reset")) {
    setAction("reset"); display();
    linePress(lines[0], TAP_MS);
    Serial.println("OK reset");
  } else if (!strcmp(cmd, "recovery")) {
    cmdRecovery();
  } else if (!strcmp(cmd, "power")) {
    if (!parseMs(arg1, PWR_TAP_MS, ms)) { Serial.println("ERR bad duration"); return; }
    setAction("power"); display();
    linePress(lines[2], ms);
    Serial.printf("OK power %lu\n", (unsigned long)ms);
  } else if (!strcmp(cmd, "press")) {
    Line *l = findLine(arg1);
    if (!l) { Serial.println("ERR unknown line (rst|fcrec|pwr)"); return; }
    if (!parseMs(arg2, TAP_MS, ms)) { Serial.println("ERR bad duration"); return; }
    setAction(l->name); display();
    linePress(*l, ms);
    Serial.printf("OK press %s %lu\n", l->name, (unsigned long)ms);
  } else if (!strcmp(cmd, "hold")) {
    Line *l = findLine(arg1);
    if (!l) { Serial.println("ERR unknown line (rst|fcrec|pwr)"); return; }
    lineAssert(*l); l->held = true; ledRefresh();
    setAction("hold");
    Serial.printf("OK hold %s (auto-release in %lu s)\n", l->name, (unsigned long)(HOLD_MAX_MS / 1000));
  } else if (!strcmp(cmd, "release")) {
    if (arg1 && !strcmp(arg1, "all")) {
      for (size_t i = 0; i < NLINES; i++) lineRelease(lines[i]);
      ledRefresh(); setAction("released");
      Serial.println("OK release all");
      return;
    }
    Line *l = findLine(arg1);
    if (!l) { Serial.println("ERR unknown line (rst|fcrec|pwr|all)"); return; }
    lineRelease(*l); ledRefresh(); setAction("released");
    Serial.printf("OK release %s\n", l->name);
  } else {
    Serial.println("ERR unknown command (try help)");
  }
}

// ---- arduino entry points ---------------------------------------------------
void setup() {
  // Release controls before display/USB setup; reset transients are unverified.
  for (size_t i = 0; i < NLINES; i++) lineRelease(lines[i]);
#if K3_SENSE_PIN >= 0
  // Opto: internal pull-up, transistor pulls low when the K3's LED is lit.
  // Divider: the 15 kΩ leg holds the pin low, no internal pull wanted (it
  // would load the divider). Either way an unplugged lead reads "off".
  pinMode(K3_SENSE_PIN, K3_SENSE_INVERT ? INPUT_PULLUP : INPUT);
#endif
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_LED, HIGH);             // off

  Serial.begin(115200);                    // baud is cosmetic on native CDC
#if K3CTL_OLED
  Wire.begin(PIN_SDA, PIN_SCL);
  u8g2.begin();
  u8g2.setContrast(64);
#endif
  setAction("ready");
  display();
}

void loop() {
  static uint32_t lastDisplay = 0;
  uint32_t now = millis();

  // Safety net: a 'hold' the host forgot (or died before) releasing.
  for (size_t i = 0; i < NLINES; i++) {
    if (lines[i].held && now - lines[i].since > HOLD_MAX_MS) {
      lineRelease(lines[i]); ledRefresh(); setAction("auto-rel");
    }
  }

  while (Serial.available() > 0) {
    int c = Serial.read();
    if (c < 0) break;
    if (c == '\r') continue;
    if (c == '\n') {
      rxbuf[rxlen] = '\0';
      if (rxOverflow) Serial.println("ERR line too long");
      else handle(rxbuf);
      rxlen = 0; rxOverflow = false;
      display();
      continue;
    }
    if (rxlen < sizeof(rxbuf) - 1) rxbuf[rxlen++] = (char)c;
    else rxOverflow = true;
  }

  if (now - lastDisplay >= DISPLAY_MS) {
    lastDisplay = now;
    display();
  }
}
