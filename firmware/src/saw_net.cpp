/*
 * Advisory network layer — core 1, low priority. SR-8.
 *
 * "The web interface may display state, history, and alerts, and may acknowledge a fault.
 * It may not be required for protection to function. Wi-Fi down = system still protects.
 * Treat all network input as untrusted."
 *
 * Enforced structurally, not by UI convention:
 *
 *   - There is exactly one mutating endpoint, POST /api/ack, and all it can do is set a
 *     flag that clears advisory alert bits. It cannot clear a MANUAL_LOCKOUT — that needs
 *     the physical button, because the point of the lockout is to require a human at the
 *     machine.
 *   - No endpoint writes a threshold, forces a state, or touches the hold line. There is
 *     no code path from here to any of them; the protection context is not even visible
 *     from this translation unit.
 *   - Every read goes through the seqlock snapshot in saw_runtime.h, so a slow client
 *     cannot stall core 0.
 *
 * The access point is deliberately local-only: no cloud, no internet dependency, and the
 * offline error-code bundle is served from flash so the operator's phone can read the
 * remediation for a code while joined to a network with no route anywhere.
 */
#include "saw_config.h"

#include <Arduino.h>
#include <ctype.h>
#include <ESPmDNS.h>
#include <LittleFS.h>
#include <math.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <WebServer.h>
#include <WiFi.h>

#if SAW_OTA_ENABLED
#include <ArduinoOTA.h>
#endif

#include "error_codes.h"
#include "saw_net.h"
#include "saw_runtime.h"
#include "saw_store.h"

static WebServer s_server(SAW_HTTP_PORT);
static bool      s_ready = false;

static const char PAGE[] PROGMEM = R"HTML(<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Table saw thermal supervisor</title>
<style>
:root{--bg:#f7f7f6;--fg:#16181d;--mut:#5b6070;--card:#fff;--line:#e0e1e6;
--ok:#1a7f4b;--warn:#a8631a;--bad:#b3261e;--lock:#6b2fb3}
@media(prefers-color-scheme:dark){:root{--bg:#14161a;--fg:#e8e9ec;--mut:#9aa0ae;
--card:#1c1f25;--line:#2c3038;--ok:#4ec98a;--warn:#e0a45c;--bad:#ff6b5e;--lock:#b98cf0}}
*{box-sizing:border-box}body{margin:0;padding:16px;background:var(--bg);color:var(--fg);
font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:760px;margin:0 auto}h1{font-size:17px;margin:0 0 12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:14px;margin-bottom:12px}
.state{font-size:26px;font-weight:650;letter-spacing:-.01em}
.temp{font-size:44px;font-weight:700;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.mut{color:var(--mut);font-size:13px}
.row{display:flex;flex-wrap:wrap;gap:14px}.row>div{flex:1 1 130px}
.k{color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.v{font-size:16px;font-variant-numeric:tabular-nums}
.pill{display:inline-block;padding:2px 9px;border-radius:99px;font-size:12px;
font-weight:600;color:#fff}
.armed{background:var(--ok)}.cool{background:var(--warn)}.trip{background:var(--bad)}
.lock{background:var(--lock)}.boot{background:var(--mut)}
.alert{border-left:3px solid var(--warn);padding:8px 12px;margin:6px 0;
background:color-mix(in srgb,var(--warn) 8%,transparent);border-radius:0 6px 6px 0}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:5px 6px;border-bottom:1px solid var(--line)}
th{color:var(--mut);font-weight:600;font-size:11px;text-transform:uppercase}
pre{margin:0;font-size:12px;white-space:pre-wrap;word-break:break-word;
max-height:230px;overflow:auto}
svg{width:100%;height:120px;display:block}
button{font:inherit;padding:7px 14px;border-radius:7px;border:1px solid var(--line);
background:var(--bg);color:var(--fg);cursor:pointer}
a{color:inherit}.scroll{overflow-x:auto}
</style></head><body><div class="wrap">
<h1>Table saw thermal supervisor</h1>

<div class="card">
  <div class="row" style="align-items:flex-start">
    <div style="flex:1 1 200px">
      <div class="state"><span id="pill" class="pill boot">—</span></div>
      <div class="temp"><span id="c">—</span><span style="font-size:22px"> °C</span></div>
      <div class="mut" id="sub">connecting…</div>
    </div>
    <div style="flex:0 0 auto;text-align:right">
      <div class="k">trip / warn / reset</div>
      <div class="v" id="thr">—</div>
      <div class="k" style="margin-top:8px">sensor</div>
      <div class="v" id="loc">—</div>
    </div>
  </div>
</div>

<div id="alerts"></div>

<div class="card">
  <div class="row">
    <div><div class="k">time in state</div><div class="v" id="tis">—</div></div>
    <div><div class="k">rate of rise</div><div class="v" id="ror">—</div></div>
    <div><div class="k">frame / delta</div><div class="v" id="delta">—</div></div>
    <div><div class="k">trips (window / total)</div><div class="v" id="trips">—</div></div>
  </div>
</div>

<div class="card">
  <div class="k" style="margin-bottom:6px">last 20 minutes</div>
  <svg id="chart" viewBox="0 0 600 120" preserveAspectRatio="none"></svg>
  <div class="mut" id="chartmut"></div>
</div>

<div class="card">
  <div class="k" style="margin-bottom:6px">recent events</div>
  <pre id="ev">—</pre>
  <div style="margin-top:10px">
    <button id="ack">Acknowledge alerts</button>
    <span class="mut" id="ackmut">Clears the banner only. A lockout needs the
      physical ack button at the machine.</span>
  </div>
</div>

<div class="card">
  <div class="k" style="margin-bottom:6px">error codes</div>
  <div class="scroll"><table id="codes"><tbody></tbody></table></div>
</div>

<div class="card mut" id="foot">—</div>
</div>
<script>
const S=["BOOT","ARMED","TRIPPED","COOLDOWN","MANUAL_LOCKOUT"];
const CL=["boot","armed","trip","cool","lock"];
const ALERTS=[["W01","Approaching trip temperature"],
["W02","Heating faster than baseline"],["W03","Probe never warmed up"],
["--","Uncalibrated build — run the two-point calibration"]];
const f=(n,d)=>n===null||n===undefined||Number.isNaN(n)?"—":n.toFixed(d===undefined?1:d);
const dur=ms=>{const s=Math.floor(ms/1000);if(s<60)return s+" s";
const m=Math.floor(s/60);if(m<60)return m+" m "+(s%60)+" s";
return Math.floor(m/60)+" h "+(m%60)+" m"};
let codes=[],bundle=false;
async function state(){
 try{
  const r=await fetch("api/state",{cache:"no-store"});const d=await r.json();
  document.getElementById("pill").textContent=S[d.state]||"?";
  document.getElementById("pill").className="pill "+(CL[d.state]||"boot");
  document.getElementById("c").textContent=f(d.c);
  document.getElementById("thr").textContent=f(d.trip_c,0)+" / "+f(d.warn_c,0)+" / "+f(d.reset_c,0);
  document.getElementById("loc").textContent=d.sensor_location;
  document.getElementById("tis").textContent=dur(d.state_ms)+
   (d.state===3&&d.cooldown_ms>0?" ("+dur(d.cooldown_ms)+" left)":"");
  document.getElementById("ror").textContent=f(d.ror,2)+" °C/min";
  document.getElementById("delta").textContent=
   d.frame_c===null?"no frame sensor":f(d.frame_c)+" °C / "+f(d.delta_c)+" °C";
  document.getElementById("trips").textContent=d.trip_count+" / "+d.trips_lifetime;
  document.getElementById("sub").textContent=
   (d.hold?"contact closed — Start will run the saw":"contact open — the saw cannot start")+
   " · LED: "+d.led_name+" · probe "+(d.probe_verified?"verified":"unverified")+
   " · reading "+dur(d.sensor_age_ms)+" old";
  const a=document.getElementById("alerts");a.innerHTML="";
  ALERTS.forEach((t,i)=>{if(d.alerts&(1<<i)){const e=document.createElement("div");
   e.className="card alert";e.innerHTML="<b>"+t[0]+"</b> "+t[1];a.appendChild(e)}});
  document.getElementById("foot").textContent=
   "Path "+d.path+" · registry "+d.registry+" · session "+d.session+
   " · up "+dur(d.uptime_ms)+" · log "+(d.fs_ok?d.retention_h+" h ring":"unavailable")+
   " · "+d.sample_hz+" Hz loop"+(d.calibrated?"":" · UNCALIBRATED");
 }catch(e){document.getElementById("sub").textContent="lost contact with the supervisor"}
}
async function hist(){
 try{
  const d=await(await fetch("api/history",{cache:"no-store"})).json();
  const n=d.c.length,sv=document.getElementById("chart");
  if(n<2){sv.innerHTML="";document.getElementById("chartmut").textContent=
   "collecting…";return}
  const ok=d.c.filter(v=>v!==null);
  let lo=Math.min.apply(null,ok),hi=Math.max.apply(null,ok);
  if(hi-lo<5){const m=(hi+lo)/2;lo=m-2.5;hi=m+2.5}
  const x=i=>i*600/(n-1),y=v=>115-(v-lo)/(hi-lo)*110;
  let p="",started=false;
  d.c.forEach((v,i)=>{if(v===null){started=false;return}
   p+=(started?"L":"M")+x(i).toFixed(1)+","+y(v).toFixed(1);started=true});
  sv.innerHTML='<path d="'+p+'" fill="none" stroke="currentColor" stroke-width="2"/>';
  document.getElementById("chartmut").textContent=
   f(lo)+" – "+f(hi)+" °C over "+dur((d.t[n-1]-d.t[0])*1000);
 }catch(e){}
}
async function ev(){try{document.getElementById("ev").textContent=
 (await(await fetch("api/events",{cache:"no-store"})).text())||"none yet"}catch(e){}}
async function loadCodes(){
 try{
  codes=await(await fetch("api/codes")).json();
  bundle=(await fetch("codes/index.html",{method:"HEAD"})).ok;
 }catch(e){bundle=false}
 const b=document.querySelector("#codes tbody");
 b.innerHTML="<tr><th>Code</th><th>Meaning</th><th>Event</th></tr>"+
  codes.map(c=>{const href=bundle?("codes/"+c.code+".html"):
   ("https://github.com/6ilo/tablesaw-thermal-protection/blob/main/docs/codes/"+c.code+".md");
   return "<tr><td><a href='"+href+"'>"+c.code+"</a></td><td>"+c.title+
    "</td><td class='mut'>"+c.event+"</td></tr>"}).join("");
 if(!bundle)document.getElementById("codes").insertAdjacentHTML("afterend",
  "<div class='mut' style='margin-top:6px'>Offline pages are not on this device — "+
  "links go to GitHub. Run <code>pio run -t uploadfs</code> to bundle them.</div>");
}
document.getElementById("ack").onclick=async()=>{
 await fetch("api/ack",{method:"POST"});state()};
loadCodes();state();hist();ev();
setInterval(state,1000);setInterval(hist,5000);setInterval(ev,5000);
</script></body></html>)HTML";

/* --------------------------------------------------------------------------- */
/* Endpoints                                                                   */
/* --------------------------------------------------------------------------- */

static void handle_root(void)
{
    s_server.sendHeader("Cache-Control", "no-store");
    s_server.send_P(200, "text/html; charset=utf-8", PAGE);
}

/*
 * snprintf returns the length it *would* have written, not the length it did. Accumulating
 * that return value straight into an offset is the classic way to end up formatting past
 * the end of a buffer the moment one field grows. Everything below goes through this.
 */
struct JsonBuf {
    char  *buf;
    size_t cap;
    size_t used;
    bool   truncated;
};

static void jb_add(JsonBuf &j, const char *fmt, ...) __attribute__((format(printf, 2, 3)));

static void jb_add(JsonBuf &j, const char *fmt, ...)
{
    if (j.truncated || j.used + 1 >= j.cap) {
        j.truncated = true;
        return;
    }
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(j.buf + j.used, j.cap - j.used, fmt, ap);
    va_end(ap);
    if (n < 0 || (size_t)n >= j.cap - j.used) {
        j.truncated = true;
        j.buf[j.cap - 1] = '\0';
        return;
    }
    j.used += (size_t)n;
}

static void jb_float(JsonBuf &j, const char *key, float v)
{
    if (isnan(v)) {
        jb_add(j, "\"%s\":null,", key);
    } else {
        jb_add(j, "\"%s\":%.2f,", key, (double)v);
    }
}

static void handle_state(void)
{
    SawSnapshot d = saw_runtime_snapshot();

    char buf[1024];
    JsonBuf j = {buf, sizeof(buf), 0, false};

    jb_add(j, "{\"state\":%u,\"state_name\":\"%s\",\"cause\":%u,",
           d.state, saw_state_name((SawState)d.state), d.cause);
    jb_add(j, "\"led\":%u,\"led_name\":\"%s\",\"hold\":%s,",
           d.led, saw_led_name((SawLedPattern)d.led),
           d.hold_closed ? "true" : "false");
    jb_float(j, "c", d.celsius);
    jb_float(j, "frame_c", d.frame_c);
    jb_float(j, "delta_c", d.delta_c);
    jb_float(j, "internal_c", d.internal_c);
    jb_float(j, "ror", d.ror_c_per_min);
    jb_float(j, "ntc_r", d.ntc_resistance);
    jb_add(j, "\"ntc_raw\":%ld,\"alerts\":%lu,\"uptime_ms\":%lu,\"state_ms\":%lu,",
           (long)d.ntc_raw, (unsigned long)d.alerts,
           (unsigned long)d.uptime_ms, (unsigned long)d.state_ms);
    jb_add(j, "\"cooldown_ms\":%lu,\"sensor_age_ms\":%lu,\"trip_count\":%u,",
           (unsigned long)d.cooldown_remaining_ms,
           (unsigned long)d.sensor_age_ms, d.trip_count);
    jb_add(j, "\"trips_lifetime\":%lu,\"session\":%lu,\"probe_verified\":%s,",
           (unsigned long)d.trips_lifetime, (unsigned long)d.session,
           d.probe_verified ? "true" : "false");
    jb_add(j, "\"calibrated\":%s,\"fs_ok\":%s,\"retention_h\":%lu,",
           d.calibrated ? "true" : "false", d.fs_ok ? "true" : "false",
           (unsigned long)saw_store_retention_hours());
    /* The thresholds this unit is actually running. docs/codes/ quotes the Path B
     * winding figures, so on a Path A build these are the numbers that are true. */
    jb_add(j, "\"trip_c\":%.1f,\"warn_c\":%.1f,\"reset_c\":%.1f,",
           (double)SAW_TRIP_C, (double)SAW_WARN_C, (double)SAW_RESET_C);
    jb_add(j, "\"path\":\"%s\",\"sensor_location\":\"%s\",\"sample_hz\":%u,"
              "\"registry\":\"%s\"}",
           SAW_PATH_NAME, SAW_SENSOR_LOCATION, (unsigned)SAW_SAMPLE_HZ,
           SAW_REGISTRY_VERSION);

    if (j.truncated) {
        /* Better a clean error than a half-written object the dashboard would choke on. */
        s_server.send(500, "application/json", "{\"error\":\"state buffer overflow\"}");
        return;
    }

    s_server.sendHeader("Cache-Control", "no-store");
    s_server.send(200, "application/json", buf);
}

static void handle_history(void)
{
    static SawHistPoint pts[SAW_LOG_RAM_SAMPLES];
    size_t n = saw_runtime_history(pts, SAW_LOG_RAM_SAMPLES);

    String out;
    out.reserve(n * 22 + 64);
    out += "{\"t\":[";
    for (size_t i = 0; i < n; i++) {
        if (i) {
            out += ',';
        }
        out += String((unsigned long)pts[i].t_s);
    }
    out += "],\"c\":[";
    for (size_t i = 0; i < n; i++) {
        if (i) {
            out += ',';
        }
        out += pts[i].c_x10 == INT16_MIN ? String("null")
                                         : String(pts[i].c_x10 / 10.0f, 1);
    }
    out += "],\"f\":[";
    for (size_t i = 0; i < n; i++) {
        if (i) {
            out += ',';
        }
        out += pts[i].frame_x10 == INT16_MIN ? String("null")
                                             : String(pts[i].frame_x10 / 10.0f, 1);
    }
    out += "],\"s\":[";
    for (size_t i = 0; i < n; i++) {
        if (i) {
            out += ',';
        }
        out += String((unsigned)pts[i].state);
    }
    out += "]}";

    s_server.sendHeader("Cache-Control", "no-store");
    s_server.send(200, "application/json", out);
}

static void handle_events(void)
{
    static char buf[SAW_EVENT_RING * SAW_EVENT_LINE_MAX + 8];
    saw_runtime_events(buf, sizeof(buf));
    s_server.sendHeader("Cache-Control", "no-store");
    s_server.send(200, "text/plain; charset=utf-8", buf);
}

static void handle_codes(void)
{
    String out;
    out.reserve(SAW_CODE_COUNT * 96 + 16);
    out += '[';
    for (int i = 0; i < SAW_CODE_COUNT; i++) {
        if (i) {
            out += ',';
        }
        out += "{\"code\":\"";
        out += SAW_CODES[i].code;
        out += "\",\"event\":\"";
        out += SAW_CODES[i].event;
        out += "\",\"title\":\"";
        out += SAW_CODES[i].title;
        out += "\",\"severity\":";
        out += String((int)SAW_CODES[i].severity);
        out += ",\"loto\":";
        out += SAW_CODES[i].loto ? "true" : "false";
        out += '}';
    }
    out += ']';
    s_server.send(200, "application/json", out);
}

struct CsvCtx {
    String chunk;
};

static void csv_field(char *out, size_t len, int16_t x10)
{
    if (x10 == INT16_MIN) {
        out[0] = '\0';   /* empty cell: the sample had no valid reading */
        return;
    }
    snprintf(out, len, "%.1f", (double)x10 / 10.0);
}

static void csv_row(const SawSampleRecord &rec, void *ctx)
{
    CsvCtx *c = (CsvCtx *)ctx;
    char primary[12], frame[12], line[96];
    csv_field(primary, sizeof(primary), rec.c_x10);
    csv_field(frame, sizeof(frame), rec.frame_x10);

    snprintf(line, sizeof(line), "%lu,%lu,%s,%s,%u,%u\n",
             (unsigned long)rec.session, (unsigned long)rec.uptime_s,
             primary, frame, rec.state, rec.flags);
    c->chunk += line;

    /* sendContent() rather than a raw client write: setContentLength(UNKNOWN) puts the
     * response into chunked transfer encoding, and bytes written straight to the socket
     * would not carry chunk framing — the client would see a corrupt body. */
    if (c->chunk.length() > 1024) {
        s_server.sendContent(c->chunk);
        c->chunk = "";
    }
}

/* The long-term log, streamed rather than buffered — 30 days of records does not fit in
 * RAM. `curl -o log.csv http://saw.local/api/log.csv` is the intended use. */
static void handle_log_csv(void)
{
    s_server.setContentLength(CONTENT_LENGTH_UNKNOWN);
    s_server.sendHeader("Content-Disposition", "attachment; filename=\"saw-log.csv\"");
    s_server.send(200, "text/csv; charset=utf-8", "");

    CsvCtx ctx;
    ctx.chunk = "session,uptime_s,celsius,frame_c,state,alerts\n";
    saw_store_stream_samples(csv_row, &ctx);
    if (ctx.chunk.length()) {
        s_server.sendContent(ctx.chunk);
    }
    s_server.sendContent("");   /* terminating zero-length chunk */
}

/*
 * The only mutating endpoint in the firmware. It sets one flag, which the protection loop
 * consumes to clear advisory alert bits. It cannot clear a MANUAL_LOCKOUT, change a
 * threshold, or close the contact — there is no code here that could.
 */
static void handle_ack(void)
{
    saw_runtime_request_alert_clear();
    s_server.send(200, "application/json", "{\"ok\":true,\"cleared\":\"alerts\"}");
}

/* Offline error-code bundle from LittleFS, gzip copies preferred. */
static bool serve_file(const String &path)
{
    String gz = path + ".gz";
    if (LittleFS.exists(gz)) {
        File f = LittleFS.open(gz, "r");
        if (f) {
            s_server.sendHeader("Content-Encoding", "gzip");
            s_server.streamFile(f, "text/html");
            f.close();
            return true;
        }
    }
    if (LittleFS.exists(path)) {
        File f = LittleFS.open(path, "r");
        if (f) {
            s_server.streamFile(f, "text/html");
            f.close();
            return true;
        }
    }
    return false;
}

static void handle_not_found(void)
{
    String uri = s_server.uri();

    /* Only ever serves out of /codes/, and only names built from [A-Za-z0-9._-]. A
     * request is untrusted input; it does not get to walk the filesystem. */
    if (uri.startsWith("/codes/") && uri.indexOf("..") < 0) {
        bool clean = true;
        for (unsigned i = 7; i < uri.length(); i++) {
            char ch = uri[i];
            if (!isalnum((int)ch) && ch != '.' && ch != '_' && ch != '-') {
                clean = false;
                break;
            }
        }
        if (uri.endsWith("/")) {
            uri += "index.html";
        }
        if (clean && serve_file(uri)) {
            return;
        }
    }

    s_server.send(404, "text/plain",
                  "Not found.\n\n"
                  "  /               dashboard\n"
                  "  /api/state      current state as JSON\n"
                  "  /api/history    in-RAM chart data\n"
                  "  /api/events     recent event lines\n"
                  "  /api/codes      the compiled-in error code registry\n"
                  "  /api/log.csv    the long-term log\n"
                  "  /codes/...      offline operator pages, if flashed\n");
}

/* --------------------------------------------------------------------------- */
/* Task                                                                        */
/* --------------------------------------------------------------------------- */

static void net_task(void *arg)
{
    (void)arg;

    WiFi.mode(WIFI_AP);
    /* An empty password would still work; WPA2 is here so the dashboard is not a shop-wide
     * open network. Nothing behind it can alter protection either way (SR-8). */
    bool up = WiFi.softAP(SAW_AP_SSID, SAW_AP_PASSWORD);
    if (up) {
        Serial.printf("AP \"%s\" at http://%s/\n", SAW_AP_SSID,
                      WiFi.softAPIP().toString().c_str());
        if (MDNS.begin(SAW_MDNS_HOST)) {
            MDNS.addService("http", "tcp", SAW_HTTP_PORT);
            Serial.printf("also http://%s.local/\n", SAW_MDNS_HOST);
        }
    } else {
        Serial.println("softAP failed — the dashboard is down, protection is not");
    }

    s_server.on("/", HTTP_GET, handle_root);
    s_server.on("/api/state", HTTP_GET, handle_state);
    s_server.on("/api/history", HTTP_GET, handle_history);
    s_server.on("/api/events", HTTP_GET, handle_events);
    s_server.on("/api/codes", HTTP_GET, handle_codes);
    s_server.on("/api/log.csv", HTTP_GET, handle_log_csv);
    s_server.on("/api/ack", HTTP_POST, handle_ack);
    s_server.onNotFound(handle_not_found);
    s_server.begin();
    s_ready = up;

#if SAW_OTA_ENABLED
    ArduinoOTA.setHostname(SAW_OTA_HOSTNAME);
    ArduinoOTA.setPassword(SAW_OTA_PASSWORD);
    ArduinoOTA.begin();
#endif

    for (;;) {
        s_server.handleClient();

#if SAW_OTA_ENABLED
        /*
         * OTA is serviced only while the saw is NOT armed. An update reboots the ESP32,
         * which opens the contact — fail-safe, but it would stop the motor mid-cut, and a
         * supervisor that can be interrupted from the network during a cut is not a
         * supervisor. Trip, cool down, or power-cycle first, then flash.
         */
        SawSnapshot d = saw_runtime_snapshot();
        if (d.state != (uint8_t)SAW_ARMED) {
            ArduinoOTA.handle();
        }
#endif

        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

void saw_net_begin(void)
{
#if SAW_NET_ENABLED
    xTaskCreatePinnedToCore(net_task, "saw_net", 8192, NULL, 1, NULL, 1);
#endif
}

bool saw_net_ready(void)
{
    return s_ready;
}
