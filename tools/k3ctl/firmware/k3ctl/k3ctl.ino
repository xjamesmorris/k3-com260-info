// SPDX-License-Identifier: GPL-2.0-only
// k3ctl.ino — USB "button pusher" for the Firefly-carrier K3-CoM260 header.
// Reset and the power-button pin's power-off have maintainer-reported results;
// power-on via SLEEP/WAKE failed (README.md). Other functions are unverified.
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
//   GPIO10    <---- optional power sense across pins 2/1 (PC_LED+/-), see
//                   "Power sense" below. Treat PC_LED+ as potentially 5 V.
//   GPIO0     ----> optional external status LED (K3CTL_EXTLED_PIN), untested
//   GPIO1     ----> optional DC-switch module input (K3CTL_DCSW_PIN), untested
//
// Header controls avoid 2/8/9 (strapping; 8 is the local LED), 5/6 (OLED),
// 18/19 (USB D±), and 20/21 (UART0).
//
// Protocol (USB CDC, 8N1, baud ignored): one ASCII line in, exactly one line
// out beginning with "OK" or "ERR" (blank lines are ignored). Multi-step
// timing runs on the ESP, not the host; fault behavior remains unverified.
//
//   ping                 -> OK pong k3ctl <ver>
//   status               -> OK status rst=0 fcrec=0 pwr=0 k3=on|off|n/a up=<ms> ver=<ver>
//                           inpwr=0|1|- inrst=0|1|- ev=<last event>|-
//   reset                -> tap RST
//   recovery             -> hold FC_REC, tap RST, release FC_REC  (BootROM download mode)
//   power [ms]           -> tap SLEEP/WAKE (default 300 ms)
//   power on             -> press SLEEP/WAKE for K3CTL_PWR_ON_MS unless sensed on
//   power off            -> tap SLEEP/WAKE unless sensed off
//   power force-off      -> hold SLEEP/WAKE up to K3CTL_PWR_FORCE_MS
//   power cycle [ms]     -> cut DC via the optional switch for ms (default 3000)
//   press <line> [ms]    -> tap rst|fcrec|pwr for <ms> (default 200, max 15000)
//   hold <line>          -> assert (30 s release timer, serviced by the firmware loop)
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
#include "riscv_logo.h"
#endif

#define K3CTL_VERSION "1.1"

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
// Watch the released RST/PWR lines for low pulses that k3ctl did not cause
// (carrier buttons, PMIC reset output). Reading an input adds no connection.
#ifndef K3CTL_MONITOR
#define K3CTL_MONITOR 1
#endif
// External LED + series resistor to GND, lit while the K3 is sensed on or an
// event is showing (the dongle has no other spare on-board LED). e.g. 0.
#ifndef K3CTL_EXTLED_PIN
#define K3CTL_EXTLED_PIN -1
#endif
// Logic-level input of a relay/MOSFET module that switches the K3's DC input,
// for 'power cycle'. Push-pull output; never drive a relay coil directly.
// K3CTL_DCSW_CUT_LEVEL is the level that removes K3 power. e.g. 1.
#ifndef K3CTL_DCSW_PIN
#define K3CTL_DCSW_PIN -1
#endif
#ifndef K3CTL_DCSW_CUT_LEVEL
#define K3CTL_DCSW_CUT_LEVEL 1
#endif

// ---- timing (ms) ------------------------------------------------------------
#ifndef K3CTL_PWR_ON_MS
#define K3CTL_PWR_ON_MS 1000       // no tested value powers this board on yet
#endif
#ifndef K3CTL_PWR_FORCE_MS
#define K3CTL_PWR_FORCE_MS 10000
#endif
#ifndef K3CTL_EVENT_MS
#define K3CTL_EVENT_MS 3000
#endif
#ifndef K3CTL_LOGO_MS
#define K3CTL_LOGO_MS 3000
#endif
static const uint32_t TAP_MS        = 200;    // default button tap
static const uint32_t PWR_TAP_MS    = 300;    // power button tap
static const uint32_t FCREC_LEAD_MS = 300;    // FC_REC settled before RST
static const uint32_t FCREC_TAIL_MS = 500;    // FC_REC held after RST released
static const uint32_t MAX_PRESS_MS  = 15000;  // longest tap accepted
static const uint32_t HOLD_MAX_MS   = 30000;  // safety net for 'hold'
static const uint32_t PWR_ON_WAIT_MS = 5000;  // sense wait after 'power on'
static const uint32_t FORCE_MIN_MS  = 1000;   // force-off: earliest sensed release
static const uint32_t DCSW_OFF_MS   = 3000;   // 'power cycle' default
static const uint32_t SENSE_DEBOUNCE_MS = 200;
static const uint32_t MON_DEBOUNCE_MS = 30;   // low pulse must last this long
static const uint32_t MON_ARM_MS    = 500;    // ...after this long stable high
static const uint32_t MON_QUIET_MS  = 200;    // ignore our own release edge
static const uint32_t DISPLAY_MS    = 100;    // OLED refresh period
static const uint32_t SHIFT_MS      = 60000;  // idle burn-in shift period

// ---- state ------------------------------------------------------------------
struct Line {
  const char *name;
  int pin;
  bool asserted;      // driven low by us (tap or hold)
  bool holdCmd;       // asserted by 'hold', subject to the auto-release timer
  uint32_t since;
  uint32_t releasedAt;
};

static Line lines[] = {
  {"rst",   PIN_RST,   false, false, 0, 0},
  {"fcrec", PIN_FCREC, false, false, 0, 0},
  {"pwr",   PIN_PWR,   false, false, 0, 0},
};
static const size_t NLINES = sizeof(lines) / sizeof(lines[0]);
static Line &L_RST = lines[0], &L_FCREC = lines[1], &L_PWR = lines[2];

enum K3State { K3_NA, K3_OFF, K3_ON };
static K3State k3State = K3_NA;

struct Event {
  char text[6];       // big word, e.g. PWR
  char label[8];      // small second line, may be empty
  uint32_t until;
  bool active;
};
static Event ev = {"", "", 0, false};
static char lastEvent[6] = "-";
static uint32_t bootUntil = 0;

static char rxbuf[64];
static size_t rxlen = 0;
static bool rxOverflow = false;

#if K3CTL_OLED
// 72x40 panel; the ER variant maps the visible area without manual offsets.
static U8G2_SSD1306_72X40_ER_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE, PIN_SCL, PIN_SDA);
#endif

static void serviceDelay(uint32_t ms);

// ---- events -----------------------------------------------------------------
static void setEvent(const char *text, const char *label = "") {
  strncpy(ev.text, text, sizeof(ev.text) - 1);
  ev.text[sizeof(ev.text) - 1] = '\0';
  strncpy(ev.label, label, sizeof(ev.label) - 1);
  ev.label[sizeof(ev.label) - 1] = '\0';
  strncpy(lastEvent, text, sizeof(lastEvent) - 1);
  lastEvent[sizeof(lastEvent) - 1] = '\0';
  ev.until = millis() + K3CTL_EVENT_MS;
  ev.active = true;
}

// Restart the overlay timer so it stays up for K3CTL_EVENT_MS after an action ends.
static void eventTouch() {
  if (ev.active) ev.until = millis() + K3CTL_EVENT_MS;
}

static void replyErr(const char *msg) {
  Serial.printf("ERR %s\n", msg);
  setEvent("ERR");
}

// ---- open-drain helpers -----------------------------------------------------
// Release = plain input with pulls disabled (arduino-esp32 INPUT = floating).
// Assert = output register preloaded low *before* enabling the driver, so the
// pad never emits a high glitch on the way to low.
static void lineRelease(Line &l) {
  pinMode(l.pin, INPUT);
  if (l.asserted) l.releasedAt = millis();
  l.asserted = false;
  l.holdCmd = false;
}

static void lineAssert(Line &l) {
  digitalWrite(l.pin, LOW);
  pinMode(l.pin, OUTPUT);
  l.asserted = true;
  l.since = millis();
}

static void ledRefresh() {
  bool any = false;
  for (size_t i = 0; i < NLINES; i++) any |= lines[i].asserted;
  digitalWrite(PIN_LED, any ? LOW : HIGH);
}

static void linePress(Line &l, uint32_t ms) {
  lineAssert(l); ledRefresh();
  serviceDelay(ms);
  lineRelease(l); ledRefresh();
  eventTouch();
}

static Line *findLine(const char *name) {
  if (!name) return nullptr;
  for (size_t i = 0; i < NLINES; i++)
    if (strcmp(lines[i].name, name) == 0) return &lines[i];
  return nullptr;
}

// ---- K3 power sense ---------------------------------------------------------
#if K3_SENSE_PIN >= 0
static bool senseRawOn;
static uint32_t senseChangedAt;
static bool senseRead() {
  bool level = digitalRead(K3_SENSE_PIN);
  return K3_SENSE_INVERT ? !level : level;
}
#endif

static void senseInit() {
#if K3_SENSE_PIN >= 0
  // Opto: internal pull-up, transistor pulls low when the K3's LED is lit.
  // Divider: the 15 kΩ leg holds the pin low, no internal pull wanted (it
  // would load the divider). Either way an unplugged lead reads "off".
  pinMode(K3_SENSE_PIN, K3_SENSE_INVERT ? INPUT_PULLUP : INPUT);
  delay(5);
  senseRawOn = senseRead();
  senseChangedAt = millis();
  k3State = senseRawOn ? K3_ON : K3_OFF;
#endif
}

static void senseUpdate() {
#if K3_SENSE_PIN >= 0
  uint32_t now = millis();
  bool on = senseRead();
  if (on != senseRawOn) { senseRawOn = on; senseChangedAt = now; return; }
  K3State s = on ? K3_ON : K3_OFF;
  if (s != k3State && now - senseChangedAt >= SENSE_DEBOUNCE_MS) {
    k3State = s;
    setEvent(on ? "ON" : "OFF");
  }
#endif
}

static const char *k3PowerState() {
  return k3State == K3_ON ? "on" : k3State == K3_OFF ? "off" : "n/a";
}

// ---- line monitor -----------------------------------------------------------
struct Mon {
  Line *line;
  const char *text;
  bool raw, stable, armed;
  uint32_t rawAt;
};
static Mon mons[] = {
  {&L_PWR, "PWR", true, true, false, 0},
  {&L_RST, "RST", true, true, false, 0},
};

static void monInit() {
  for (auto &m : mons) {
    m.raw = m.stable = digitalRead(m.line->pin);
    m.armed = false;
    m.rawAt = millis();
  }
}

static void monUpdate() {
#if K3CTL_MONITOR
  uint32_t now = millis();
  for (auto &m : mons) {
    Line &l = *m.line;
    bool raw = digitalRead(l.pin);
    if (l.asserted || now - l.releasedAt < MON_QUIET_MS) {
      m.raw = m.stable = raw; m.armed = false; m.rawAt = now;
      continue;
    }
    if (raw != m.raw) { m.raw = raw; m.rawAt = now; continue; }
    if (now - m.rawAt < MON_DEBOUNCE_MS) continue;
    if (raw == m.stable) {
      if (raw && now - m.rawAt >= MON_ARM_MS) m.armed = true;
      continue;
    }
    m.stable = raw;
    if (!raw && m.armed) setEvent(m.text, "ext");
    m.armed = false;
  }
#endif
}

static const char *inputLevel(const Line &l) {
  if (l.asserted) return "-";
  return digitalRead(l.pin) ? "1" : "0";
}

// ---- display ----------------------------------------------------------------
#if K3CTL_OLED
static uint8_t curContrast = 0;
static void contrast(uint8_t c) {
  if (c != curContrast) { u8g2.setContrast(c); curContrast = c; }
}

// Small horizontal drift so a static idle screen does not burn in.
static int idleShift() {
  static const int8_t dx[] = {0, 1, 2, 1, 0, -1, -2, -1};
  return dx[(millis() / SHIFT_MS) % (sizeof(dx) / sizeof(dx[0]))];
}

static void drawLogo(int dx) {
  u8g2.drawXBMP((72 - RISCV_LOGO_W) / 2 + dx, (40 - RISCV_LOGO_H) / 2,
                RISCV_LOGO_W, RISCV_LOGO_H, riscv_logo_bits);
}

static void drawBig(const char *text, const char *label, int dx) {
  u8g2.setFont(u8g2_font_logisoso24_tr);
  if (u8g2.getStrWidth(text) > 72) u8g2.setFont(u8g2_font_logisoso16_tr);
  int asc = u8g2.getAscent();
  int w = u8g2.getStrWidth(text);
  int base = (label && *label) ? asc + 1 : (40 + asc) / 2;
  u8g2.drawStr((72 - w) / 2 + dx, base, text);
  if (label && *label) {
    u8g2.setFont(u8g2_font_6x10_tr);
    if (u8g2.getStrWidth(label) > 72) u8g2.setFont(u8g2_font_5x8_tr);
    w = u8g2.getStrWidth(label);
    u8g2.drawStr((72 - w) / 2 + dx, 39, label);
  }
}
#endif

static void display() {
  uint32_t now = millis();
  bool tapActive = false, holdActive = false;
  for (size_t i = 0; i < NLINES; i++) {
    tapActive |= lines[i].asserted && !lines[i].holdCmd;
    holdActive |= lines[i].holdCmd;
  }
  if (ev.active && tapActive) ev.until = now + K3CTL_EVENT_MS;
  if (ev.active && (int32_t)(now - ev.until) >= 0) ev.active = false;

#if K3CTL_EXTLED_PIN >= 0
  digitalWrite(K3CTL_EXTLED_PIN, (k3State == K3_ON || ev.active) ? HIGH : LOW);
#endif

#if K3CTL_OLED
  u8g2.clearBuffer();
  if (ev.active) {
    contrast(255);
    drawBig(ev.text, ev.label, 0);
  } else if (holdActive) {
    char names[16] = "";
    for (size_t i = 0; i < NLINES; i++) {
      if (!lines[i].holdCmd) continue;
      if (*names) strcat(names, "+");
      strcat(names, lines[i].name);
    }
    contrast(255);
    drawBig("HOLD", names, 0);
  } else if ((int32_t)(now - bootUntil) < 0) {
    contrast(255);
    drawLogo(0);
  } else {
    contrast(16);
    if (k3State == K3_ON) drawBig("ON", "", idleShift());
    else drawLogo(idleShift());
  }
  u8g2.sendBuffer();
#endif
}

// ---- background servicing ---------------------------------------------------
static void holdService() {
  uint32_t now = millis();
  // Safety net: a 'hold' the host forgot (or died before) releasing.
  for (size_t i = 0; i < NLINES; i++) {
    if (lines[i].holdCmd && now - lines[i].since > HOLD_MAX_MS) {
      lineRelease(lines[i]); ledRefresh();
    }
  }
}

static void background() {
  static uint32_t lastDisplay = 0;
  holdService();
  senseUpdate();
  monUpdate();
  if (millis() - lastDisplay >= DISPLAY_MS) {
    lastDisplay = millis();
    display();
  }
}

// Blocking wait that keeps sense, monitor, hold timer and display serviced.
static void serviceDelay(uint32_t ms) {
  uint32_t start = millis();
  while (millis() - start < ms) {
    background();
    uint32_t left = ms - (millis() - start);
    delay(left < 5 ? left : 5);
  }
}

// ---- commands ---------------------------------------------------------------
static void cmdStatus() {
  Serial.printf("OK status rst=%d fcrec=%d pwr=%d k3=%s up=%lu ver=" K3CTL_VERSION
                " inpwr=%s inrst=%s ev=%s\n",
                L_RST.asserted, L_FCREC.asserted, L_PWR.asserted,
                k3PowerState(), (unsigned long)millis(),
                inputLevel(L_PWR), inputLevel(L_RST), lastEvent);
}

static void cmdRecovery() {
  // Intended running-board recovery sequence; not hardware-tested.
  setEvent("REC"); display();
  lineAssert(L_FCREC); ledRefresh();
  serviceDelay(FCREC_LEAD_MS);
  linePress(L_RST, TAP_MS);
  serviceDelay(FCREC_TAIL_MS);
  lineRelease(L_FCREC); ledRefresh();
  eventTouch();
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

static bool waitK3(K3State want, uint32_t ms) {
  uint32_t start = millis();
  while (k3State != want && millis() - start < ms) serviceDelay(10);
  return k3State == want;
}

static void cmdPower(const char *arg1, const char *arg2) {
  uint32_t ms;
  if (!arg1 || isdigit((unsigned char)arg1[0])) {
    if (arg2) { replyErr("usage: power [ms|on|off|force-off|cycle [ms]]"); return; }
    if (!parseMs(arg1, PWR_TAP_MS, ms)) { replyErr("bad duration"); return; }
    setEvent("PWR"); display();
    linePress(L_PWR, ms);
    Serial.printf("OK power %lu\n", (unsigned long)ms);
  } else if (!strcmp(arg1, "on") && !arg2) {
    if (k3State == K3_ON) { setEvent("ON"); Serial.println("OK power on k3=on (already on)"); return; }
    setEvent("PWR", "on"); display();
    linePress(L_PWR, K3CTL_PWR_ON_MS);
    if (k3State == K3_NA) { Serial.println("OK power on k3=n/a"); return; }
    if (waitK3(K3_ON, PWR_ON_WAIT_MS)) Serial.println("OK power on k3=on");
    else replyErr("power on: k3 still off");
  } else if (!strcmp(arg1, "off") && !arg2) {
    if (k3State == K3_OFF) { setEvent("OFF"); Serial.println("OK power off k3=off (already off)"); return; }
    setEvent("PWR", "off"); display();
    linePress(L_PWR, PWR_TAP_MS);
    Serial.printf("OK power off k3=%s\n", k3PowerState());
  } else if (!strcmp(arg1, "force-off") && !arg2) {
    setEvent("PWR", "force"); display();
    lineAssert(L_PWR); ledRefresh();
    uint32_t start = millis();
    while (millis() - start < K3CTL_PWR_FORCE_MS) {
      serviceDelay(10);
      if (k3State == K3_OFF && millis() - start >= FORCE_MIN_MS) break;
    }
    uint32_t held = millis() - start;
    lineRelease(L_PWR); ledRefresh(); eventTouch();
    Serial.printf("OK power force-off %lu k3=%s\n", (unsigned long)held, k3PowerState());
  } else if (!strcmp(arg1, "cycle")) {
#if K3CTL_DCSW_PIN >= 0
    if (!parseMs(arg2, DCSW_OFF_MS, ms)) { replyErr("bad duration"); return; }
    setEvent("DC", "cycle"); display();
    digitalWrite(K3CTL_DCSW_PIN, K3CTL_DCSW_CUT_LEVEL ? HIGH : LOW);
    serviceDelay(ms);
    digitalWrite(K3CTL_DCSW_PIN, K3CTL_DCSW_CUT_LEVEL ? LOW : HIGH);
    eventTouch();
    Serial.printf("OK power cycle %lu\n", (unsigned long)ms);
#else
    replyErr("power cycle: no DC switch (build with -DK3CTL_DCSW_PIN)");
#endif
  } else {
    replyErr("usage: power [ms|on|off|force-off|cycle [ms]]");
  }
}

static const char *eventFor(const Line &l) {
  return &l == &L_RST ? "RST" : &l == &L_FCREC ? "REC" : "PWR";
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
    Serial.println("OK help ping|status|reset|recovery|power [ms|on|off|force-off|cycle [ms]]|press <rst|fcrec|pwr> [ms]|hold <line>|release <line|all>");
  } else if (!strcmp(cmd, "reset")) {
    setEvent("RST"); display();
    linePress(L_RST, TAP_MS);
    Serial.println("OK reset");
  } else if (!strcmp(cmd, "recovery")) {
    cmdRecovery();
  } else if (!strcmp(cmd, "power")) {
    cmdPower(arg1, arg2);
  } else if (!strcmp(cmd, "press")) {
    Line *l = findLine(arg1);
    if (!l) { replyErr("unknown line (rst|fcrec|pwr)"); return; }
    if (!parseMs(arg2, TAP_MS, ms)) { replyErr("bad duration"); return; }
    setEvent(eventFor(*l), "press"); display();
    linePress(*l, ms);
    Serial.printf("OK press %s %lu\n", l->name, (unsigned long)ms);
  } else if (!strcmp(cmd, "hold")) {
    Line *l = findLine(arg1);
    if (!l) { replyErr("unknown line (rst|fcrec|pwr)"); return; }
    lineAssert(*l); l->holdCmd = true; ledRefresh();
    Serial.printf("OK hold %s (auto-release in %lu s)\n", l->name, (unsigned long)(HOLD_MAX_MS / 1000));
  } else if (!strcmp(cmd, "release")) {
    if (arg1 && !strcmp(arg1, "all")) {
      for (size_t i = 0; i < NLINES; i++) lineRelease(lines[i]);
      ledRefresh();
      Serial.println("OK release all");
      return;
    }
    Line *l = findLine(arg1);
    if (!l) { replyErr("unknown line (rst|fcrec|pwr|all)"); return; }
    lineRelease(*l); ledRefresh();
    Serial.printf("OK release %s\n", l->name);
  } else {
    replyErr("unknown command (try help)");
  }
}

// ---- arduino entry points ---------------------------------------------------
void setup() {
  // Release controls before display/USB setup; reset transients are unverified.
  for (size_t i = 0; i < NLINES; i++) lineRelease(lines[i]);
#if K3CTL_DCSW_PIN >= 0
  digitalWrite(K3CTL_DCSW_PIN, K3CTL_DCSW_CUT_LEVEL ? LOW : HIGH);   // keep DC on
  pinMode(K3CTL_DCSW_PIN, OUTPUT);
#endif
#if K3CTL_EXTLED_PIN >= 0
  digitalWrite(K3CTL_EXTLED_PIN, LOW);
  pinMode(K3CTL_EXTLED_PIN, OUTPUT);
#endif
  senseInit();
  monInit();
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_LED, HIGH);             // off

  Serial.begin(115200);                    // baud is cosmetic on native CDC
#if K3CTL_OLED
  Wire.begin(PIN_SDA, PIN_SCL);
  u8g2.begin();
  contrast(255);
#endif
  bootUntil = millis() + K3CTL_LOGO_MS;
  display();
}

void loop() {
  background();

  while (Serial.available() > 0) {
    int c = Serial.read();
    if (c < 0) break;
    if (c == '\r') continue;
    if (c == '\n') {
      rxbuf[rxlen] = '\0';
      if (rxOverflow) replyErr("line too long");
      else handle(rxbuf);
      rxlen = 0; rxOverflow = false;
      display();
      continue;
    }
    if (rxlen < sizeof(rxbuf) - 1) rxbuf[rxlen++] = (char)c;
    else rxOverflow = true;
  }
}
