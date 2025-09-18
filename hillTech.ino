/*
  ESP32 Smart Farm Dashboard + Percent-Based Auto Pump (Hysteresis + Debounce)

  - UI pages:
      /         → dashboard
      /simple   → soil-only page
      /data     → JSON for UI
      /pump     → manual pump on/off (disables auto)
      /mode     → switch AUTO/MANUAL
      /threshold → legacy raw threshold setter (kept for compatibility; AUTO ignores it)

  - AUTO behavior (hands-off):
      * Pump turns ON when soil% <= MOISTURE_ON_PCT (dry).
      * Pump turns OFF when soil% >= MOISTURE_OFF_PCT (wet enough).
      * Hysteresis + minimum ON/OFF windows to avoid chatter.
      * Optional ultrasonic empty-tank safety lockout (prevents running pump when tank seems empty).

  - Notes:
      * soilPercent() uses DRY_CAL (dry) and WET_CAL (wet). Ensure dry gives lower % and wet gives higher %.
      * If percent looks inverted, swap DRY_CAL and WET_CAL values.
*/

#include <WiFi.h>
#include <WebServer.h>
#include <DHT.h>

// ====== WiFi ======
const char* WIFI_SSID = "D1";
const char* WIFI_PASS = "12345678";

// ====== Pins ======
const int SOIL_PIN  = 32;   // Soil sensor analog pin
const int TRIG_PIN  = 22;   // Ultrasonic TRIG
const int ECHO_PIN  = 18;   // Ultrasonic ECHO
const int RELAY_PIN = 27;   // Relay pin
const int DHT_PIN   = 21;   // DHT11 pin

// ====== DHT ======
#define DHTTYPE DHT11
DHT dht(DHT_PIN, DHTTYPE);

// ====== Relay ======
const bool RELAY_ACTIVE_HIGH = false; // false for active-LOW relay modules

// ====== Soil calibration for % display ======
int DRY_CAL = 3500;   // raw ADC when DRY
int WET_CAL = 1200;   // raw ADC when WET

// ====== Percent-based AUTO thresholds ======
const int MOISTURE_ON_PCT  = 30;   // turn ON at/under this (%)
const int MOISTURE_OFF_PCT = 45;   // turn OFF at/over this (%)

// ====== Debounce / protection windows (ms) ======
const unsigned long MIN_ON_MS   = 15000; // min pump ON duration
const unsigned long MIN_OFF_MS  = 8000;  // min pump OFF duration
const unsigned long DRY_HOLD_MS = 2000;  // must stay dry this long before ON

// ====== Ultrasonic tank protection ======
const bool  TANK_PROTECT_ENABLED = true;
const float TANK_EMPTY_CM        = 25.0f; // >= this distance considered "empty"

// ====== Auto loop tick ======
const unsigned long AUTO_PERIOD_MS = 1000;

// ====== Ultrasonic timing ======
const unsigned long PULSE_TIMEOUT_US = 30000UL;
const float SOUND_SPEED_CM_PER_US = 0.0343f;

// ====== Smoothing (EMA) for soil raw ======
const float SOIL_EMA_ALPHA = 0.25f; // 0..1; higher = less smoothing
float soilEma = NAN;

// ====== Server + globals ======
WebServer server(80);
bool pumpOn = false;

// AUTO/MANUAL mode (true = AUTO)
bool autoMode = true;

// Legacy raw threshold (kept for UI/compat only, AUTO ignores it)
int SOIL_THRESHOLD_RAW = 2000;

unsigned long bootMillis;
unsigned long lastAutoCheck = 0;
unsigned long lastDebugMillis = 0;

// Auto state
unsigned long pumpOnSince  = 0;
unsigned long pumpOffSince = 0;
unsigned long drySince     = 0;
bool emptyLockout          = false;

// ---------- Helpers ----------
int readSoilRawAvg(int samples = 10) {
  long sum = 0;
  for (int i = 0; i < samples; i++) {
    sum += analogRead(SOIL_PIN);
    delay(5);
  }
  return sum / samples;
}

int readSoilRawStable(int samples = 10) {
  int raw = readSoilRawAvg(samples);
  if (isnan(soilEma)) soilEma = raw;
  soilEma = SOIL_EMA_ALPHA * raw + (1.0f - SOIL_EMA_ALPHA) * soilEma;
  return (int)(soilEma + 0.5f);
}

int soilPercent(int raw) {
  if (DRY_CAL == WET_CAL) return 0;
  long pct = map(raw, DRY_CAL, WET_CAL, 0, 100);
  return constrain(pct, 0, 100);
}

// 12-bit → 10-bit
int to10bit(int raw12) {
  long num = (long)raw12 * 1023 + 2047;
  return (int)(num / 4095);
}

String soilBucketFromV10(int v10) {
  if (v10 >= 1000) return "Not in soil / Disconnected";
  else if (v10 > 600) return "0";
  else if (v10 >= 370) return "50";
  else return "100";
}

float readUltrasonicCM() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(3);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(12);
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(3);

  unsigned long duration = pulseIn(ECHO_PIN, HIGH, PULSE_TIMEOUT_US);
  if (duration == 0) return NAN;
  return (duration * SOUND_SPEED_CM_PER_US) / 2.0f;
}

float readUltrasonicFiltered(int samples = 5) {
  float sum = 0;
  int valid = 0;
  for (int i = 0; i < samples; i++) {
    float d = readUltrasonicCM();
    if (!isnan(d)) {
      sum += d;
      valid++;
    }
    delay(30);
  }
  return (valid > 0) ? (sum / valid) : NAN;
}

void setPump(bool on) {
  pumpOn = on;
  int level = RELAY_ACTIVE_HIGH ? (on ? HIGH : LOW) : (on ? LOW : HIGH);
  digitalWrite(RELAY_PIN, level);
  Serial.print("Pump state set to: ");
  Serial.println(on ? "ON" : "OFF");
  if (on) {
    pumpOnSince = millis();
    pumpOffSince = 0;
  } else {
    pumpOffSince = millis();
    pumpOnSince = 0;
  }
}

String jsonSafe(String s) {
  s.replace("\\","\\\\");
  s.replace("\"","\\\"");
  return s;
}

String ipToString(const IPAddress& ip) {
  return String(ip[0])+"."+String(ip[1])+"."+String(ip[2])+"."+String(ip[3]);
}

// ---------- Web Interface (Dashboard) ----------
const char* INDEX_HTML = R"HTML(
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>ESP32 Smart Farm Dashboard</title>
  <style>
    :root{
      --bg:#f5f3e9; --card:#ffffff; --line:#e5dcc8; --muted:#8b7765; --text:#3d3a34;
      --on:#3fa34d; --on-hover:#338741; --off:#cc3d3d; --off-hover:#b53434; --accent:#a8c88b; --mode:#6b5b95;
    }
    *{box-sizing:border-box}
    body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,Segoe UI,Roboto,system-ui,sans-serif}
    header{background:var(--accent);padding:14px;text-align:center;border-bottom:2px solid var(--line);}
    header h1{margin:0;font-size:1.4rem}
    #status{font-size:.85rem;color:var(--muted)}
    main{padding:18px;display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
    .card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px;box-shadow:0 6px 14px rgba(0,0,0,.08)}
    .label{font-size:.9rem;color:var(--muted)}
    .value{font-size:1.3rem;font-weight:700;margin-top:6px}
    .big{font-size:1.8rem}
    .btn{padding:12px 18px;border:none;border-radius:12px;color:#fff;font-weight:700;cursor:pointer;transition:background .2s,transform .1s}
    .btn:active{transform:translateY(1px)}
    .btn-on{background:var(--on)} .btn-on:hover{background:var(--on-hover)}
    .btn-off{background:var(--off)} .btn-off:hover{background:var(--off-hover)}
    .btn-mode{background:var(--mode)}
    .row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
    input[type=number]{padding:10px;border:1px solid var(--line);border-radius:10px;width:120px}
  </style>
</head>
<body>
  <header>
    <h1>🌾 ESP32 Smart Farm</h1>
    <div id="status">Connecting…</div>
  </header>

  <main>
    <div class="card"><div class="label">Temperature</div><div class="value big" id="temp">— °C</div></div>
    <div class="card"><div class="label">Humidity</div><div class="value big" id="humid">— %</div></div>
    <div class="card">
      <div class="label">Soil Moisture</div>
      <div class="value big" id="soil">— %</div>
      <div class="label">Raw / Threshold</div>
      <div class="value" id="soilRaw">—</div>
      <div class="label">Bucket (simple)</div>
      <div class="value" id="soilBucket">—</div>
      <div class="row">
        <input id="thRaw" type="number" step="1" min="0" max="4095" />
        <button class="btn btn-on" id="setTh">Set Threshold</button>
      </div>
    </div>
    <div class="card"><div class="label">Water Level</div><div class="value big" id="ultra">— cm</div></div>

    <div class="card">
      <div class="label">Pump</div>
      <div class="value big" id="pump">—</div>
      <button id="pumpBtn" class="btn">Toggle</button>
    </div>

    <div class="card">
      <div class="label">Mode</div>
      <div class="value big" id="mode">—</div>
      <button id="modeBtn" class="btn btn-mode">Switch Mode</button>
    </div>
  </main>

<script>
async function fetchData(){
  try{
    const res = await fetch('/data',{cache:'no-store'});
    const j = await res.json();

    document.getElementById('status').textContent =
      `WiFi: ${j.wifi_ssid} · IP: ${j.ip} · Uptime: ${j.uptime_s}s`;

    document.getElementById('temp').textContent   = (j.temp_c!=null)   ? (j.temp_c.toFixed(1)+" °C") : "— °C";
    document.getElementById('humid').textContent  = (j.humidity_pct!=null)? (j.humidity_pct.toFixed(1)+" %") : "— %";
    document.getElementById('soil').textContent   = (j.soil_pct!=null) ? (j.soil_pct+" %") : "— %";
    document.getElementById('ultra').textContent  = (j.ultrasonic_cm!=null)? (j.ultrasonic_cm.toFixed(1)+" cm") : "— cm";
    document.getElementById('soilRaw').textContent = `${j.soil_raw} / th=${j.soil_threshold_raw}`;
    document.getElementById('soilBucket').textContent = j.soil_status_text ?? "—";

    const pumpVal = document.getElementById('pump');
    const btn = document.getElementById('pumpBtn');
    if(j.pump_on){
      pumpVal.textContent = "ON";
      btn.textContent = "Turn OFF";
      btn.className = "btn btn-off";
    } else {
      pumpVal.textContent = "OFF";
      btn.textContent = "Turn ON";
      btn.className = "btn btn-on";
    }

    document.getElementById('mode').textContent = j.auto_mode ? "AUTO" : "MANUAL";
    document.getElementById('modeBtn').textContent = j.auto_mode ? "Switch to MANUAL" : "Switch to AUTO";

    document.getElementById('thRaw').value = j.soil_threshold_raw;
  }catch(e){
    document.getElementById('status').textContent = "Disconnected (retrying)…";
  }
}

document.getElementById('pumpBtn').addEventListener('click', async ()=>{
  try{
    await fetch('/pump?state='+(document.getElementById('pump').textContent==="ON"?"off":"on"), {cache:'no-store'});
  }catch(e){}
  fetchData();
});

document.getElementById('modeBtn').addEventListener('click', async ()=>{
  const now = document.getElementById('mode').textContent;
  const next = (now==="AUTO") ? "manual" : "auto";
  try{ await fetch('/mode?state='+next, {cache:'no-store'}); }catch(e){}
  fetchData();
});

document.getElementById('setTh').addEventListener('click', async ()=>{
  const v = document.getElementById('thRaw').value;
  try{ await fetch('/threshold?raw='+encodeURIComponent(v), {cache:'no-store'}); }catch(e){}
  fetchData();
});

setInterval(fetchData, 1000);
fetchData();
</script>
</body>
</html>
)HTML";

// ---------- Simple Soil Page ----------
const char* SIMPLE_HTML = R"HTML(
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Soil Moisture</title>
  <style>
    body{font-family:Arial,Helvetica,sans-serif;margin:36px}
    h1{margin-top:0}
    p{font-size:1.1rem}
    code{background:#f2f2f2;padding:2px 6px;border-radius:6px}
  </style>
</head>
<body>
  <h1>🌱 Soil Moisture Monitor</h1>
  <p><b>Raw 12-bit ADC:</b> <span id="raw12">—</span></p>
  <p><b>Mapped 10-bit:</b> <span id="raw10">—</span></p>
  <p><b>Status:</b> <span id="status">—</span></p>

<script>
async function load(){
  try{
    const r = await fetch('/data',{cache:'no-store'});
    const j = await r.json();
    document.getElementById('raw12').textContent = j.soil_raw ?? '—';
    document.getElementById('raw10').textContent = j.soil_raw10 ?? '—';
    document.getElementById('status').textContent = j.soil_status_text ?? '—';
  }catch(e){
    document.getElementById('status').textContent='Disconnected';
  }
}
setInterval(load, 1000);
load();
</script>
</body>
</html>
)HTML";

// ---------- Handlers ----------
void handleRoot() { server.send(200,"text/html",INDEX_HTML); }
void handleSimple() { server.send(200,"text/html",SIMPLE_HTML); }

void handleData() {
  static unsigned long lastDHT=0; static float t=NAN,h=NAN;
  if (millis()-lastDHT>3000) {
    t=dht.readTemperature();
    h=dht.readHumidity();
    lastDHT=millis();
  }

  int soilRaw = readSoilRawAvg();
  int soilPct = soilPercent(soilRaw);
  int raw10   = to10bit(soilRaw);
  String bucket = soilBucketFromV10(raw10);

  float cm = readUltrasonicFiltered();
  unsigned long uptime=(millis()-bootMillis)/1000UL;

  String json="{";
  json+="\"soil_raw\":"+String(soilRaw)+",";
  json+="\"soil_raw10\":"+String(raw10)+",";
  json+="\"soil_status_text\":\""+jsonSafe(bucket)+"\",";
  json+="\"soil_pct\":"+String(soilPct)+",";
  json+=(isnan(cm)? "\"ultrasonic_cm\":null," : "\"ultrasonic_cm\":"+String(cm,1)+",");
  json+=(isnan(t)? "\"temp_c\":null," : "\"temp_c\":"+String(t,1)+",");
  json+=(isnan(h)? "\"humidity_pct\":null," : "\"humidity_pct\":"+String(h,1)+",");
  json+="\"pump_on\":" + String(pumpOn ? "true" : "false") + ",";
  json+="\"auto_mode\":" + String(autoMode ? "true" : "false") + ",";
  json+="\"soil_threshold_raw\":"+String(SOIL_THRESHOLD_RAW)+","; // legacy for UI
  json+="\"wifi_ssid\":\""+jsonSafe(WIFI_SSID)+"\",";
  json+="\"ip\":\""+ipToString(WiFi.localIP())+"\",";
  json+="\"uptime_s\":"+String(uptime);
  json+="}";
  server.send(200,"application/json",json);
}

void handlePump() {
  if (!server.hasArg("state")) {
    server.send(400,"text/plain","Missing state");
    return;
  }
  String s=server.arg("state");
  s.toLowerCase();
  Serial.print("Pump command: ");
  Serial.println(s);
  if(s=="on"){
    autoMode=false;
    setPump(true);
  }
  else if(s=="off"){
    autoMode=false;
    setPump(false);
  }
  server.send(200,"text/plain","OK");
}

void handleMode() {
  if (!server.hasArg("state")) {
    server.send(400,"text/plain","Missing state");
    return;
  }
  String s=server.arg("state");
  s.toLowerCase();
  if(s=="auto") autoMode=true;
  else if(s=="manual") autoMode=false;
  Serial.print("Mode set to: ");
  Serial.println(autoMode?"AUTO":"MANUAL");
  server.send(200,"text/plain","OK");
}

void handleThreshold() {
  // Legacy raw threshold setter; AUTO is now %-based and ignores this.
  if (!server.hasArg("raw")) {
    server.send(400,"text/plain","Missing raw");
    return;
  }
  int v = server.arg("raw").toInt();
  if (v < 0) v = 0;
  if (v > 4095) v = 4095;
  SOIL_THRESHOLD_RAW = v;
  Serial.print("Legacy threshold set to raw=");
  Serial.println(SOIL_THRESHOLD_RAW);
  server.send(200,"text/plain","OK");
}

void handleNotFound() {
  server.send(404,"text/plain","Not found");
}

// ---------- Setup ----------
void setup() {
  Serial.begin(115200);
  pinMode(TRIG_PIN,OUTPUT);
  pinMode(ECHO_PIN,INPUT);
  pinMode(RELAY_PIN,OUTPUT);
  setPump(false);

  analogReadResolution(12);
  analogSetPinAttenuation(SOIL_PIN, ADC_11db);
  dht.begin();

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID,WIFI_PASS);
  while(WiFi.status()!=WL_CONNECTED){
    delay(300);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected. IP: "+ipToString(WiFi.localIP()));

  WiFi.onEvent([](WiFiEvent_t event, WiFiEventInfo_t){
    if (event == WIFI_EVENT_STA_DISCONNECTED) {
      Serial.println("WiFi lost, reconnecting...");
      WiFi.reconnect();
    }
  });

  server.on("/",HTTP_GET,handleRoot);
  server.on("/simple",HTTP_GET,handleSimple);
  server.on("/data",HTTP_GET,handleData);
  server.on("/pump",HTTP_GET,handlePump);
  server.on("/mode",HTTP_GET,handleMode);
  server.on("/threshold",HTTP_GET,handleThreshold);
  server.onNotFound(handleNotFound);
  server.begin();

  bootMillis=millis();

  // Initialize timers
  pumpOnSince  = 0;
  pumpOffSince = millis();
}

// ---------- Loop (AUTO controller) ----------
void loop() {
  server.handleClient();

  unsigned long now = millis();
  if (autoMode && (now - lastAutoCheck >= AUTO_PERIOD_MS)) {
    lastAutoCheck = now;

    // Smooth soil then compute %
    int soilRaw = readSoilRawStable();
    int pct = soilPercent(soilRaw);

    // Ultrasonic tank protection
    float cm = readUltrasonicFiltered();
    if (TANK_PROTECT_ENABLED) {
      if (!isnan(cm) && cm >= TANK_EMPTY_CM) {
        if (!emptyLockout) {
          Serial.println("AUTO: Tank looks EMPTY → lockout + Pump OFF");
          emptyLockout = true;
          if (pumpOn) setPump(false);
        }
      } else {
        if (emptyLockout) Serial.println("AUTO: Tank level OK → clear lockout");
        emptyLockout = false;
      }
    } else {
      emptyLockout = false;
    }

    // Initialize timers if needed
    if (!pumpOn && pumpOffSince == 0) pumpOffSince = now;
    if ( pumpOn && pumpOnSince  == 0) pumpOnSince  = now;

    // Percent-based hysteresis logic with debounce
    if (!pumpOn) {
      bool dry = (pct <= MOISTURE_ON_PCT);
      if (dry && !emptyLockout) {
        if (drySince == 0) drySince = now;
      } else {
        drySince = 0;
      }
      bool offWindowElapsed = (now - pumpOffSince >= MIN_OFF_MS);
      bool dryHeldEnough    = (drySince != 0) && (now - drySince >= DRY_HOLD_MS);
      if (dry && offWindowElapsed && dryHeldEnough && !emptyLockout) {
        Serial.print("AUTO: Dry "); Serial.print(pct); Serial.println("% → Pump ON");
        setPump(true);
        drySince = 0;
      }
    } else {
      bool wetEnough = (pct >= MOISTURE_OFF_PCT);
      bool onWindowElapsed = (now - pumpOnSince >= MIN_ON_MS);
      if (wetEnough && onWindowElapsed) {
        Serial.print("AUTO: Recovered "); Serial.print(pct); Serial.println("% → Pump OFF");
        setPump(false);
      }
      // Safety: if tank empties while ON
      if (pumpOn && emptyLockout) {
        Serial.println("AUTO: Safety OFF due to empty tank while ON");
        setPump(false);
      }
    }
  }

  // Optional debug
  if (now - lastDebugMillis >= 2000) {
    lastDebugMillis = now;
    int soilRaw = readSoilRawAvg();
    int soilPct = soilPercent(soilRaw);
    Serial.print("Soil raw: "); Serial.print(soilRaw);
    Serial.print("  → "); Serial.print(soilPct); Serial.println("%");

    float cm = readUltrasonicCM();
    if (!isnan(cm)) {
      Serial.print("Ultrasonic distance: "); Serial.print(cm); Serial.println(" cm");
    } else {
      Serial.println("Ultrasonic: no echo");
    }
  }
}
