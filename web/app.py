
"""
FactoryGuard AI — Streamlit Web Dashboard v3
Changes from v2:
- Dynatrace metrics push (every refresh cycle)
- Dynatrace event push on fault detection
- Dynatrace status badge in sidebar
- Model string corrected to gemini-3.5-flash
- Subtitle corrected
- API key via env var with fallback hardcode
"""

import streamlit as st
import pandas as pd
import time
import os
import json
import urllib.request
import urllib.error
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────────
CSV_FILE       = os.path.join(os.path.dirname(__file__), "..", "simulator", "motor_data.csv")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "token_here")
MODEL          = "gemini-3.1-flash-lite"
GEMINI_URL     = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={GEMINI_API_KEY}"

DT_URL         = os.environ.get("DT_URL",   "https://ywo70142.live.dynatrace.com")
DT_TOKEN       = os.environ.get("DT_TOKEN", "token_here")
DT_PLATFORM_TOKEN = os.environ.get("DT_PLATFORM_TOKEN", "") 

REFRESH_RATE   = 2
ANALYSIS_EVERY = 30
HISTORY_ROWS   = 60
MIN_ROWS       = 10
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="FactoryGuard AI", page_icon="⚙", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0f1117; color: #e0e0e0; }
    .metric-card {
        background: #1e2230; border-radius: 12px;
        padding: 16px 20px; text-align: center;
        border: 1px solid #2a2f45; margin-bottom: 8px;
    }
    .metric-value { font-size: 2.2rem; font-weight: 700; font-family: monospace; }
    .metric-label { font-size: 0.75rem; color: #888; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 4px; }
    .status-healthy  { background:#0d2b1a; border:1px solid #00ff88; border-radius:10px; padding:16px; margin-bottom:16px; }
    .status-warning  { background:#2b2000; border:1px solid #ffaa00; border-radius:10px; padding:16px; margin-bottom:16px; }
    .status-critical { background:#2b0000; border:1px solid #ff4444; border-radius:10px; padding:16px; margin-bottom:16px; }
    .fault-tag {
        display:inline-block; background:#3a1a1a; color:#ff6b6b;
        border:1px solid #ff4444; border-radius:6px;
        padding:3px 10px; margin:3px; font-size:0.8rem; font-family:monospace;
    }
    .ai-box {
        background:#121a2e; border:1px solid #1d4ed8;
        border-radius:12px; padding:20px; margin-top:10px;
        font-family: monospace; font-size:0.9rem; line-height:1.8;
        min-height: 200px;
    }
    .section-header { color:#00d4ff; font-weight:700; margin-top:14px; font-size:1rem; }
    .dt-badge { background:#1a1a2e; border:1px solid #00b4e6; border-radius:8px; padding:10px 14px; margin-bottom:10px; font-size:0.8rem; }
    h1 { color:#00d4ff !important; }
    h2, h3 { color:#e0e0e0 !important; }
</style>
""", unsafe_allow_html=True)

# ─── SESSION STATE ────────────────────────────────────────────────────────────
for key, default in [
    ("last_analysis", ""),
    ("last_analysis_time", 0.0),
    ("analysis_count", 0),
    ("ai_running", False),
    ("dt_last_push", 0.0),
    ("dt_last_status", ""),
    ("dt_push_count", 0),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ─── DATA HELPERS ─────────────────────────────────────────────────────────────
def read_csv(n=HISTORY_ROWS):
    try:
        df = pd.read_csv(CSV_FILE)
        if df.empty: return pd.DataFrame()
        return df.tail(n).reset_index(drop=True)
    except Exception:
        return pd.DataFrame()

def detect_faults(df):
    if df.empty or len(df) < 3: return []
    row    = df.iloc[-1]
    faults = []
    volt   = float(row.get("voltage_v", 400))
    curr   = float(row.get("current_a", 0))
    temp   = float(row.get("temperature_c", 25))
    vib    = float(row.get("vibration_mm_s", 0))
    rpm    = float(row.get("rpm", 0))
    temps  = df["temperature_c"].astype(float).tolist()
    vibs   = df["vibration_mm_s"].astype(float).tolist()
    rpms   = df["rpm"].astype(float).tolist()
    currs  = df["current_a"].astype(float).tolist()

    if volt < 360:  faults.append(f"LOW VOLTAGE {volt:.0f}V (rated 400V)")
    if volt < 340:  faults.append(f"CRITICAL UNDERVOLTAGE {volt:.0f}V")
    if volt > 430:  faults.append(f"OVERVOLTAGE {volt:.0f}V")
    if curr > 18:   faults.append(f"OVERCURRENT {curr:.1f}A (rated 15.2A)")
    if curr > 22:   faults.append(f"CRITICAL OVERCURRENT {curr:.1f}A")
    if volt < 370 and curr > 16:
        faults.append(f"VOLTAGE DROP + OVERCURRENT V={volt:.0f}V I={curr:.1f}A")
    if temp > 80:   faults.append(f"HIGH TEMPERATURE {temp:.1f}C")
    if temp > 100:  faults.append(f"CRITICAL TEMPERATURE {temp:.1f}C")
    exp_t = 25 + 50*(curr/15.2)
    if temp > exp_t + 20:
        faults.append(f"COOLING FAILURE: {temp:.1f}C expected {exp_t:.0f}C")
    if vib > 4.5:   faults.append(f"HIGH VIBRATION {vib:.3f} mm/s")
    if vib > 7.1:   faults.append(f"CRITICAL VIBRATION {vib:.3f} mm/s")
    if len(rpms)>=5 and (rpms[0]-rpms[-1])>80 and curr<18:
        faults.append(f"UNEXPLAINED RPM DROP -{rpms[0]-rpms[-1]:.0f} RPM")
    if len(temps)>=5 and temps[-1]-temps[0]>8:
        faults.append(f"TEMPERATURE RISING +{temps[-1]-temps[0]:.1f}C in {len(temps)}s")
    if len(vibs)>=5 and vibs[-1]-vibs[0]>2:
        faults.append(f"VIBRATION RISING +{vibs[-1]-vibs[0]:.3f} mm/s")
    # Slip anomaly
    if rpm > 100 and curr > 2:
        actual_slip = (1500.0 - rpm) / 1500.0
        if actual_slip > 0.15:
            faults.append(f"HIGH SLIP {actual_slip*100:.1f}% — possible rotor bar fault or mechanical drag")
    # Stall detection
    if rpm < 30 and curr > 3.0:
        faults.append(f"POSSIBLE STALL: RPM={rpm:.0f} with current={curr:.1f}A — locked rotor risk")
    # Phase imbalance proxy
    if volt > 370 and curr > 15.2*1.2 and rpm < 1450*0.85 and rpm > 100:
        faults.append(f"POSSIBLE PHASE IMBALANCE: I={curr:.1f}A with V={volt:.0f}V at RPM={rpm:.0f}")
    return faults

def get_metric_color(key, val):
    try: v = float(val)
    except: return "#00d4ff"
    rules = {
        "temperature_c":  [(v>=100,"#ff4444"),(v>=80,"#ffaa00")],
        "vibration_mm_s": [(v>=7.1,"#ff4444"),(v>=4.5,"#ffaa00")],
        "current_a":      [(v>=18, "#ff4444"),(v>=14, "#ffaa00")],
        "voltage_v":      [(v<=340,"#ff4444"),(v<=380,"#ffaa00")],
    }
    if key not in rules: return "#00d4ff"
    for condition, color in rules[key]:
        if condition: return color
    return "#00ff88"

# ─── DYNATRACE INTEGRATION ────────────────────────────────────────────────────
def push_metrics_to_dynatrace(volt, curr, temp, vib, rpm, power_kw, fault_count, status):
    """Push motor metrics to Dynatrace via Metrics Ingest API v2."""
    severity = 2 if "CRITICAL" in status else (1 if "WARNING" in status else 0)
    lines = "\n".join([
        f"factoryguard.motor.voltage_v,motor=unit1,location=factory1 {volt}",
        f"factoryguard.motor.current_a,motor=unit1,location=factory1 {curr}",
        f"factoryguard.motor.temperature_c,motor=unit1,location=factory1 {temp}",
        f"factoryguard.motor.vibration_mm_s,motor=unit1,location=factory1 {vib}",
        f"factoryguard.motor.rpm,motor=unit1,location=factory1 {rpm}",
        f"factoryguard.motor.power_kw,motor=unit1,location=factory1 {power_kw}",
        f"factoryguard.motor.fault_count,motor=unit1,location=factory1 {fault_count}",
        f"factoryguard.motor.severity,motor=unit1,location=factory1 {severity}",
    ])
    try:
        req = urllib.request.Request(
            f"{DT_URL}/api/v2/metrics/ingest",
            data=lines.encode("utf-8"),
            headers={
                "Content-Type": "text/plain; charset=utf-8",
                "Authorization": f"Api-Token {DT_TOKEN}"
            }
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status  # 202 = accepted
    except Exception as e:
        return f"error: {e}"

def push_event_to_dynatrace(fault_list, status, curr, temp, vib):
    """Push a problem event to Dynatrace when faults are detected."""
    if not fault_list:
        return
    severity_map = {"CRITICAL": "ERROR", "WARNING": "WARN"}
    dt_severity  = severity_map.get(
        "CRITICAL" if "CRITICAL" in status else ("WARNING" if "WARNING" in status else ""),
        "INFO"
    )
    if dt_severity == "INFO":
        return  # Only push events for actual problems

    event_body = {
        "eventType": "CUSTOM_ALERT",
        "title": f"FactoryGuard: {status} — {len(fault_list)} fault(s) detected",
        "entitySelector": "type(CUSTOM_DEVICE)",
        "properties": {
            "faults":      "; ".join(fault_list[:3]),
            "current_a":   str(round(curr, 2)),
            "temperature":  str(round(temp, 1)),
            "vibration":   str(round(vib, 3)),
            "source":      "FactoryGuard AI",
        }
    }
    try:
        req = urllib.request.Request(
            f"{DT_URL}/api/v2/events/ingest",
            data=json.dumps(event_body).encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Api-Token {DT_TOKEN}"
            }
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status
    except Exception:
        pass  # Non-critical — don't break the dashboard

# ─── GEMINI CALL ─────────────────────────────────────────────────────────────
def call_gemini(df, faults):
    rows  = df.to_dict("records")
    rpms  = df["rpm"].astype(float).tolist()
    temps = df["temperature_c"].astype(float).tolist()
    vibs  = df["vibration_mm_s"].astype(float).tolist()
    currs = df["current_a"].astype(float).tolist()
    volts = df["voltage_v"].astype(float).tolist()
    tr    = lambda v: "rising" if v[-1]>v[0]*1.05 else ("falling" if v[-1]<v[0]*0.95 else "stable")

    data_str = "\n".join(
        f"{r.get('timestamp','')} RPM={r.get('rpm',0)} T={r.get('temperature_c',0)}C "
        f"Vib={r.get('vibration_mm_s',0)}mm/s I={r.get('current_a',0)}A V={r.get('voltage_v',0)}V"
        for r in rows[-15:]
    )
    ftext = "\n".join(f"- {f}" for f in faults) if faults else "No threshold violations."

    system_text = """You are FactoryGuard AI, a senior electrical engineer. Write in plain text only, no asterisks, no bold, no markdown symbols.

Motor: 3-phase induction motor, 400V nominal, 7.5kW, 1450 RPM rated, 15.2A rated current, insulation class F, power factor 0.85.
Normal ranges: voltage 380-420V, current below 15.2A full load, temperature below 80C, vibration below 4.5 mm/s ISO 10816."""

    user_text = f"""Sensor data (last {len(rows)} seconds):
{data_str}

Trends: RPM {tr(rpms)}, temperature {tr(temps)}, vibration {tr(vibs)}, current {tr(currs)}, voltage {tr(volts)}.

Rule engine flagged:
{ftext}

Give a complete engineering diagnosis using these exact section headers:

STATUS: HEALTHY or WARNING or CRITICAL and one sentence why.

OBSERVATIONS: 2 sentences with specific values and percent deviations from rated.

ROOT CAUSE: 2-3 sentences explaining the physics with actual numbers.

RECOMMENDED ACTIONS:
Action 1 IMMEDIATE or THIS WEEK: specific action with tool or location.
Action 2 IMMEDIATE or THIS WEEK: specific action with tool or location.
Action 3 NEXT MAINTENANCE: preventive action.

RISK ASSESSMENT: one sentence with time to failure, shutdown recommendation, safety risk level."""

    try:
        payload = json.dumps({
            "system_instruction": {"parts": [{"text": system_text}]},
            "contents": [{"role": "user", "parts": [{"text": user_text}]}],
            "generationConfig": {"temperature": 0.15, "maxOutputTokens": 500}
        }).encode("utf-8")
        req = urllib.request.Request(
            GEMINI_URL, data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode())
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code == 429: return "Rate limit reached. Wait 60s and the page will retry automatically."
        return f"API Error {e.code}: {body[:150]}"
    except Exception as e:
        return f"Connection error: {e}"

# ─── AI DIAGNOSIS RENDERER ────────────────────────────────────────────────────
def render_diagnosis(text, status):
    if not text:
        return "<div class='ai-box' style='color:#555;text-align:center;padding-top:60px'>Waiting for first analysis — this takes up to 30 seconds after the simulator starts.</div>"

    sc   = "#ff4444" if "CRITICAL" in status else ("#ffaa00" if "WARNING" in status else "#00ff88")
    html = "<div class='ai-box'>"
    for line in text.split("\n"):
        s   = line.strip()
        if not s: html += "<br>"; continue
        low = s.lower()
        su  = s.upper()
        if   low.startswith("status"):
            col = "#ff4444" if "CRITICAL" in su else ("#ffaa00" if "WARNING" in su else "#00ff88")
            html += f"<div class='section-header' style='color:{col};font-size:1.15rem'>{s}</div>"
        elif low.startswith("observ"):    html += f"<div class='section-header'>OBSERVATIONS</div>"
        elif low.startswith("root"):      html += f"<div class='section-header' style='color:#cc88ff'>ROOT CAUSE</div>"
        elif low.startswith("recommend"): html += f"<div class='section-header' style='color:#ffcc44'>RECOMMENDED ACTIONS</div>"
        elif low.startswith("risk"):      html += f"<div class='section-header' style='color:{sc}'>RISK ASSESSMENT</div>"
        elif s.startswith("Action"):
            ac = "#ff4444" if "IMMEDIATE" in su else ("#ffaa00" if "THIS WEEK" in su else "#888")
            html += f"<div style='margin:5px 0 5px 16px;color:{ac}'>{s}</div>"
        else:
            html += f"<div style='margin:2px 0;color:#b8b8b8'>{s}</div>"
    html += "</div>"
    return html

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    st.markdown("# ⚙ FactoryGuard AI")
    st.markdown("`3-Phase 400V Industrial Motor  |  Real-Time Predictive Maintenance  |  Gemini 3.5 Flash  +  Dynatrace`")
    st.markdown("---")

    df = read_csv()

    if df.empty:
        st.warning("⚠ No sensor data found. Start `motor_simulator.py` first.")
        st.code("cd simulator\npython motor_simulator.py", language="bash")
        time.sleep(2); st.rerun(); return

    latest    = df.iloc[-1]
    faults    = detect_faults(df)
    status    = str(latest.get("status", "NORMAL"))
    volt      = float(latest.get("voltage_v", 400))
    curr      = float(latest.get("current_a", 0))
    temp      = float(latest.get("temperature_c", 25))
    vib       = float(latest.get("vibration_mm_s", 0))
    rpm       = float(latest.get("rpm", 0))
    power_kw  = float(latest.get("power_kw", 0))

    sc     = "#ff4444" if "CRITICAL" in status else ("#ffaa00" if "WARNING" in status else ("#888" if "IDLE" in status else "#00ff88"))
    sclass = "status-critical" if "CRITICAL" in status else ("status-warning" if "WARNING" in status else "status-healthy")
    ftags  = "".join(f"<span class='fault-tag'>{f}</span>" for f in faults) or "<span style='color:#00ff88'>All parameters normal</span>"

    # ── Push metrics to Dynatrace (every 10s max to avoid hammering free tier)
    now = time.time()
    if now - st.session_state.dt_last_push >= 10:
        dt_result = push_metrics_to_dynatrace(volt, curr, temp, vib, rpm, power_kw, len(faults), status)
        if faults:
            push_event_to_dynatrace(faults, status, curr, temp, vib)
        st.session_state.dt_last_push   = now
        st.session_state.dt_last_status = "✅ Sent" if dt_result == 202 else f"⚠ {dt_result}"
        if dt_result == 202:
            st.session_state.dt_push_count += 1

    # Status banner
    st.markdown(f"""
    <div class='{sclass}'>
        <span style='color:{sc};font-size:1.4rem;font-weight:700'>● {status}</span>
        <span style='color:#555;font-size:0.82rem;margin-left:16px'>{latest.get('timestamp','')}</span>
        <div style='margin-top:8px'>{ftags}</div>
    </div>""", unsafe_allow_html=True)

    # 6 metric cards
    cols = st.columns(6)
    sensors = [
        ("RPM",       "rpm",            "",     "#00d4ff"),
        ("TEMP",      "temperature_c",  "°C",   None),
        ("VIBRATION", "vibration_mm_s", "mm/s", None),
        ("CURRENT",   "current_a",      "A",    None),
        ("VOLTAGE",   "voltage_v",      "V",    None),
        ("POWER",     "power_kw",       "kW",   "#ffffff"),
    ]
    for i, (label, key, unit, fixed) in enumerate(sensors):
        val   = latest.get(key, "--")
        color = fixed if fixed else get_metric_color(key, val)
        with cols[i]:
            st.markdown(f"""
            <div class='metric-card'>
                <div class='metric-label'>{label}</div>
                <div class='metric-value' style='color:{color}'>{val}{unit}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Charts
    st.markdown("### 📈 Sensor Trends")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Temperature & Current**")
        chart = df[["timestamp","temperature_c","current_a"]].rename(
            columns={"temperature_c":"Temp (°C)","current_a":"Current (A)"}
        ).set_index("timestamp").apply(pd.to_numeric, errors="coerce")
        st.line_chart(chart, height=200)
    with c2:
        st.markdown("**Voltage & RPM/10**")
        df2 = df[["timestamp","voltage_v"]].copy()
        df2["RPM/10"] = pd.to_numeric(df["rpm"], errors="coerce") / 10
        df2 = df2.rename(columns={"voltage_v":"Voltage (V)"}).set_index("timestamp").apply(pd.to_numeric, errors="coerce")
        st.line_chart(df2, height=200)

    st.markdown("<br>", unsafe_allow_html=True)

    # AI + Dynatrace columns
    ai_col, spec_col = st.columns([3, 1])

    elapsed = now - st.session_state.last_analysis_time
    cd      = max(0, int(ANALYSIS_EVERY - elapsed))

    should_run = (
        len(df) >= MIN_ROWS
        and elapsed >= ANALYSIS_EVERY
        and not st.session_state.ai_running
    )

    with ai_col:
        if st.session_state.analysis_count == 0:
            hdr = f"🤖 First analysis in {cd}s..." if cd > 0 else "🤖 Running first analysis..."
        else:
            hdr = f"🤖 AI Diagnosis #{st.session_state.analysis_count}"
            hdr += f"  —  next in {cd}s" if cd > 0 else "  —  updating..."

        st.markdown(f"### {hdr}")

        if should_run:
            st.session_state.ai_running = True
            with st.spinner("Gemini 3.5 Flash is analysing the motor data..."):
                result = call_gemini(df, faults)
            st.session_state.last_analysis      = result
            st.session_state.last_analysis_time = time.time()
            st.session_state.analysis_count    += 1
            st.session_state.ai_running         = False

        st.markdown(render_diagnosis(st.session_state.last_analysis, status), unsafe_allow_html=True)

    with spec_col:
        # Dynatrace status badge
        dt_status = st.session_state.dt_last_status or "Pending..."
        dt_count  = st.session_state.dt_push_count
        st.markdown(f"""
        <div class='dt-badge'>
            <div style='color:#00b4e6;font-weight:700;margin-bottom:4px'>
                📡 Dynatrace
            </div>
            <div style='color:#aaa'>Status: <span style='color:#00ff88'>{dt_status}</span></div>
            <div style='color:#aaa'>Pushes: <span style='color:#fff'>{dt_count}</span></div>
            <div style='color:#555;font-size:0.72rem;margin-top:4px'>
                8 metrics · every 10s
            </div>
        </div>""", unsafe_allow_html=True)

        st.markdown("### ℹ Motor Specs")
        st.markdown("""
| Parameter | Value |
|-----------|-------|
| Voltage | 400V |
| Power | 7.5 kW |
| Speed | 1450 RPM |
| Current | 15.2A |
| Insulation | Class F |
| PF | 0.85 |
        """)
        st.markdown("**Thresholds**")
        st.markdown("""
- Temp warn: **80°C**
- Temp crit: **100°C**
- Vib warn: **4.5 mm/s**
- Vib crit: **7.1 mm/s**
- Current max: **18A**
- Voltage min: **360V**
        """)

    # Auto-refresh
    render_agent_chat(df)
    time.sleep(REFRESH_RATE)
    st.rerun()

# ═══════════════════════════════════════════════════════════════════
# FACTORYGUARD AGENT CHAT — fetches from Dynatrace + Gemini analysis
# ═══════════════════════════════════════════════════════════════════

def fetch_dynatrace_metrics():
    """Fetch the latest motor metrics from Dynatrace Metrics API v2."""
    metrics_to_fetch = [
        "factoryguard.motor.voltage_v",
        "factoryguard.motor.current_a",
        "factoryguard.motor.temperature_c",
        "factoryguard.motor.vibration_mm_s",
        "factoryguard.motor.rpm",
        "factoryguard.motor.power_kw",
        "factoryguard.motor.fault_count",
        "factoryguard.motor.severity",
    ]
    selector = ",".join(metrics_to_fetch)
    url = f"{DT_URL}/api/v2/metrics/query?metricSelector={selector}&resolution=1m&from=now-5m"

    try:
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Api-Token {DT_PLATFORM_TOKEN or DT_TOKEN}"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        results = {}
        for item in data.get("resolution", {}) and data.get("result", []):
            metric_id = item.get("metricId", "")
            series    = item.get("data", [])
            if series:
                values = [v for v in series[0].get("values", []) if v is not None]
                if values:
                    short_name = metric_id.split(".")[-1]  # e.g. voltage_v
                    results[short_name] = round(values[-1], 3)

        return results if results else None

    except Exception as e:
        return {"error": str(e)}


def agent_ask_gemini(user_question: str, dt_data: dict, motor_df) -> str:
    """Send user question + Dynatrace context + CSV context to Gemini."""

    # Build Dynatrace context string
    if dt_data and "error" not in dt_data:
        dt_context = "LIVE DATA FROM DYNATRACE (last 5 minutes):\n"
        label_map = {
            "voltage_v": "Voltage",
            "current_a": "Current",
            "temperature_c": "Temperature",
            "vibration_mm_s": "Vibration",
            "rpm": "RPM",
            "power_kw": "Power",
            "fault_count": "Active Faults",
            "severity": "Severity Level (0=OK 1=WARN 2=CRIT)",
        }
        for k, v in dt_data.items():
            label = label_map.get(k, k)
            dt_context += f"  {label}: {v}\n"
    elif dt_data and "error" in dt_data:
        dt_context = f"Dynatrace query failed: {dt_data['error']}. Using local CSV data instead.\n"
    else:
        dt_context = "Dynatrace returned no data. Using local CSV data.\n"

    # Build CSV context (last 3 rows summary)
    csv_context = ""
    if motor_df is not None and not motor_df.empty:
        last = motor_df.iloc[-1]
        csv_context = (
            f"\nLOCAL SENSOR DATA (latest reading):\n"
            f"  Voltage: {last.get('voltage_v','N/A')} V\n"
            f"  Current: {last.get('current_a','N/A')} A\n"
            f"  Temperature: {last.get('temperature_c','N/A')} C\n"
            f"  Vibration: {last.get('vibration_mm_s','N/A')} mm/s\n"
            f"  RPM: {last.get('rpm','N/A')}\n"
            f"  Status: {last.get('status','N/A')}\n"
        )

    system_text = (
        "You are FactoryGuard AI, a senior industrial motor diagnostic agent. "
        "You monitor a 400V / 7.5kW / 1450 RPM 3-phase induction motor in a factory. "
        "You have access to real-time data from Dynatrace monitoring and local sensors. "
        "Normal ranges: voltage 380-420V, current below 15.2A, temperature below 80C, vibration below 4.5 mm/s. "
        "Always answer as a professional maintenance engineer: cite the exact sensor values, "
        "explain root causes using motor physics, and give specific recommended actions. "
        "Be concise and direct. Use plain text, no markdown symbols."
    )

    full_prompt = (
        f"{dt_context}"
        f"{csv_context}\n"
        f"Engineer question: {user_question}"
    )

    try:
        payload = json.dumps({
            "system_instruction": {"parts": [{"text": system_text}]},
            "contents": [{"role": "user", "parts": [{"text": full_prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 600}
        }).encode("utf-8")

        req = urllib.request.Request(
            GEMINI_URL, data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode())
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()

    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code == 429:
            return "Rate limit reached — wait 60 seconds and try again."
        return f"Gemini error {e.code}: {body[:200]}"
    except Exception as e:
        return f"Agent error: {e}"


def render_agent_chat(df):
    st.markdown("---")
    st.markdown("## 🤖 FactoryGuard Agent")
    st.markdown(
        "<span style='color:#555;font-size:0.82rem'>"
        "Agent fetches live data from Dynatrace · powered by Gemini AI"
        "</span>",
        unsafe_allow_html=True
    )

    # Init session state for chat
    if "agent_messages" not in st.session_state:
        st.session_state.agent_messages = []

    # Display chat history
    for msg in st.session_state.agent_messages:
        role_color = "#00d4ff" if msg["role"] == "user" else "#00ff88"
        role_label = "You" if msg["role"] == "user" else "FactoryGuard Agent"
        st.markdown(
            f"<div style='margin:8px 0;padding:12px 16px;"
            f"background:{"#1a1f35" if msg["role"]=="user" else "#0d2b1a"};"
            f"border-radius:10px;border-left:3px solid {role_color}'>"
            f"<div style='color:{role_color};font-size:0.75rem;font-weight:700;"
            f"margin-bottom:6px'>{role_label}</div>"
            f"<div style='color:#ccc;font-size:0.9rem;white-space:pre-wrap'>{msg['content']}</div>"
            f"</div>",
            unsafe_allow_html=True
        )

    # Suggested questions (only shown when chat is empty)
    if not st.session_state.agent_messages:
        st.markdown("<div style='color:#555;font-size:0.8rem;margin-bottom:8px'>Try asking:</div>", unsafe_allow_html=True)
        suggestions = [
            "What is the current motor status from Dynatrace?",
            "Is the temperature dangerous right now?",
            "Why is the current high?",
            "How many faults are active?",
        ]
        cols = st.columns(len(suggestions))
        for i, suggestion in enumerate(suggestions):
            with cols[i]:
                if st.button(suggestion, key=f"suggest_{i}", use_container_width=True):
                    st.session_state._agent_pending = suggestion
                    st.rerun()

    # Handle suggested question click
    pending = st.session_state.pop("_agent_pending", None)

    # Chat input
    user_input = st.chat_input("Ask the agent about motor health, faults, or Dynatrace data...")

    question = pending or user_input

    if question:
        # Add user message
        st.session_state.agent_messages.append({"role": "user", "content": question})

        # Fetch Dynatrace + call Gemini
        with st.spinner("Agent fetching Dynatrace data and analysing..."):
            dt_data  = fetch_dynatrace_metrics()
            response = agent_ask_gemini(question, dt_data, df)

        # Add agent response
        st.session_state.agent_messages.append({"role": "assistant", "content": response})
        st.rerun()

    # Clear button
    if st.session_state.agent_messages:
        if st.button("🗑 Clear chat", key="clear_agent_chat"):
            st.session_state.agent_messages = []
            st.rerun()



if __name__ == "__main__":
    main()

# ── CLOUD RUN LIVE DATA GENERATOR ─────────────────────────────────────────────
# When running on Cloud Run (no local simulator), regenerate CSV every refresh
# so the dashboard shows changing values instead of static data
import math as _math

def regenerate_live_data():
    """Generate fresh 120 rows ending at NOW so values change on every refresh."""
    import random, csv
    from datetime import datetime, timedelta
    t = datetime.now() - timedelta(seconds=120)
    rows = []
    seed = int(datetime.now().timestamp()) // 30  # changes every 30s
    random.seed(seed)

    for i in range(120):
        load = 0.70 + random.uniform(-0.03, 0.03)
        if i < 60:
            volt = 400 + random.uniform(-5, 5)
            bvib, btemp, status = 0, 0, "NORMAL"
        elif i < 90:
            volt = 400 + random.uniform(-5, 5)
            sev = (i - 60) / 30.0
            bvib = sev * 8.5 + 2 * _math.sin(i * 3.2) * sev
            btemp = sev * 12
            status = "WARNING_BEARING_FAULT" if sev > 0.3 else "NORMAL"
        else:
            volt = 340 + random.uniform(-6, 6)
            bvib, btemp = 0, 0
            status = "WARNING_LOW_VOLTAGE"

        curr = (7500 * load / 0.91) / (1.732 * volt * 0.85) * (400 / volt) + random.uniform(-0.2, 0.2)
        temp = 25 + (50 / 15.2**2) * curr**2 + btemp + random.uniform(-0.5, 0.5)
        rpm  = 1450 * (1 - 0.05 * load) * (0.93 if bvib > 3 else 1.0) + random.uniform(-8, 8)
        vib  = max(0, 0.5 + 1.8 * load + bvib + random.uniform(-0.05, 0.05))
        pw   = round((1.732 * volt * curr * 0.85) / 1000, 3)
        if temp > 100: status = "CRITICAL_OVERTEMPERATURE"
        elif curr > 20: status = "CRITICAL_OVERCURRENT"
        rows.append([t.strftime('%Y-%m-%d %H:%M:%S'), round(rpm,1), round(temp,1),
                     round(vib,3), round(curr,2), round(volt,1), pw, status])
        t += timedelta(seconds=1)

    os.makedirs(os.path.dirname(CSV_FILE), exist_ok=True)
    with open(CSV_FILE, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['timestamp','rpm','temperature_c','vibration_mm_s','current_a','voltage_v','power_kw','status'])
        w.writerows(rows)

# Call on every Streamlit rerun when running on Cloud Run (no local simulator present)
_is_cloud = os.environ.get("K_SERVICE") is not None   # Cloud Run sets K_SERVICE
if _is_cloud:
    regenerate_live_data()
