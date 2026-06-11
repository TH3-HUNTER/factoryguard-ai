import csv, time, os, json, urllib.request, urllib.error, math
from datetime import datetime
import threading

CSV_FILE          = os.path.join(os.path.dirname(__file__), "..", "simulator", "motor_data.csv")
GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY", "API_token_here")
MODEL             = "gemini-3.1-flash-lite"
GEMINI_URL        = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={GEMINI_API_KEY}"

DT_URL            = os.environ.get("DT_URL",   "https://ywo70142.live.dynatrace.com")
DT_TOKEN          = os.environ.get("DT_TOKEN", "token_here")

ANALYSIS_COOLDOWN = 30
HISTORY_SIZE      = 20
API_TIMEOUT       = 30
MAX_RETRIES       = 2
MIN_ROWS          = 10

V_RATED   = 400.0
I_RATED   = 15.2
RPM_RATED = 1450
P_RATED   = 7500
PF        = 0.85
EFF       = 0.91
T_AMBIENT = 25.0
T_RATED   = 75.0
SLIP_RATED = 0.05

R="\033[91m"; Y="\033[93m"; G="\033[92m"; C="\033[96m"
M="\033[95m"; W="\033[97m"; DIM="\033[90m"; RST="\033[0m"; BOLD="\033[1m"

last_analysis_time = 0
analysis_count     = 0
ai_running         = False
rate_limit_penalty = 0


def read_csv_tail(n=20):
    try:
        with open(CSV_FILE, "r") as f:
            rows = list(csv.DictReader(f))
            return rows[-n:] if rows else []
    except FileNotFoundError:
        return []

def push_metrics_to_dynatrace(row, fault_count, status):
    try:
        volt     = float(row.get("voltage_v", 0))
        curr     = float(row.get("current_a", 0))
        temp     = float(row.get("temperature_c", 0))
        vib      = float(row.get("vibration_mm_s", 0))
        rpm      = float(row.get("rpm", 0))
        power_kw = float(row.get("power_kw", 0))
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
        req = urllib.request.Request(
            f"{DT_URL}/api/v2/metrics/ingest",
            data=lines.encode("utf-8"),
            headers={
                "Content-Type": "text/plain; charset=utf-8",
                "Authorization": f"Api-Token {DT_TOKEN}"
            }
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            code = resp.status
            if code == 202:
                print(f"\n  {C}[Dynatrace] 8 metrics pushed ✓{RST}")
            else:
                print(f"\n  {Y}[Dynatrace] HTTP {code}{RST}")
    except Exception as e:
        print(f"\n  {Y}[Dynatrace] Push failed: {e}{RST}")

def push_event_to_dynatrace(fault_list, status, curr, temp, vib):
    if not fault_list: return
    if "CRITICAL" not in status and "WARNING" not in status: return
    event_body = {
        "eventType": "CUSTOM_ALERT",
        "title": f"FactoryGuard: {status} — {len(fault_list)} fault(s)",
        "entitySelector": "type(CUSTOM_DEVICE)",
        "properties": {
            "faults":      "; ".join(fault_list[:3]),
            "current_a":   str(round(curr, 2)),
            "temperature": str(round(temp, 1)),
            "vibration":   str(round(vib, 3)),
            "source":      "FactoryGuard AI v8",
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
            if resp.status in (200, 201, 202):
                print(f"  {C}[Dynatrace] Event pushed: {status}{RST}")
    except Exception as e:
        print(f"  {Y}[Dynatrace] Event failed: {e}{RST}")

def detect_faults(rows):
    if not rows or len(rows) < 3: return []
    faults = []
    l      = rows[-1]
    volt   = float(l["voltage_v"])
    curr   = float(l["current_a"])
    temp   = float(l["temperature_c"])
    vib    = float(l["vibration_mm_s"])
    rpm    = float(l["rpm"])
    pow_kw = float(l.get("power_kw", 0))
    temps  = [float(r["temperature_c"])  for r in rows]
    vibs   = [float(r["vibration_mm_s"]) for r in rows]
    rpms   = [float(r["rpm"])            for r in rows]
    currs  = [float(r["current_a"])      for r in rows]

    if volt < 360:  faults.append(f"LOW VOLTAGE {volt:.0f}V (rated 400V)")
    if volt < 340:  faults.append(f"CRITICAL UNDERVOLTAGE {volt:.0f}V")
    if volt > 430:  faults.append(f"OVERVOLTAGE {volt:.0f}V")
    if curr > 18:   faults.append(f"OVERCURRENT {curr:.1f}A (rated 15.2A)")
    if curr > 22:   faults.append(f"CRITICAL OVERCURRENT {curr:.1f}A")
    if volt < 370 and curr > 16:
        faults.append(f"VOLTAGE DROP CAUSING OVERCURRENT: V={volt:.0f}V I={curr:.1f}A")
    if temp > 80:   faults.append(f"HIGH TEMPERATURE {temp:.1f}C")
    if temp > 100:  faults.append(f"CRITICAL TEMPERATURE {temp:.1f}C")
    k_th  = (T_RATED - T_AMBIENT) / (I_RATED ** 2)
    exp_t = T_AMBIENT + k_th * (curr ** 2)
    if temp > exp_t + 20:
        faults.append(f"COOLING FAILURE: {temp:.1f}C expected {exp_t:.0f}C (+{temp-exp_t:.0f}C above I\u00b2R model)")
    if vib > 4.5:   faults.append(f"HIGH VIBRATION {vib:.3f} mm/s")
    if vib > 7.1:   faults.append(f"CRITICAL VIBRATION {vib:.3f} mm/s (ISO 10816 zone D)")
    if vib > 5.0 and rpm < 800:
        faults.append(f"VIBRATION AT LOW SPEED {vib:.3f} mm/s @ {rpm:.0f} RPM — resonance/imbalance")
    if len(rpms)>=5 and (rpms[0]-rpms[-1])>80 and curr<18:
        faults.append(f"UNEXPLAINED RPM DROP -{rpms[0]-rpms[-1]:.0f} RPM (no current rise)")
    if len(temps)>=5 and temps[-1]-temps[0]>8:
        faults.append(f"TEMPERATURE RISING +{temps[-1]-temps[0]:.1f}C in {len(temps)}s")
    if len(vibs)>=5 and vibs[-1]-vibs[0]>2:
        faults.append(f"VIBRATION RISING +{vibs[-1]-vibs[0]:.3f} mm/s in {len(vibs)}s")

    if rpm > 100 and curr > 2:
        actual_slip = (1500.0 - rpm) / 1500.0
        load_frac   = min(curr / I_RATED, 1.5)
        exp_slip    = SLIP_RATED * load_frac
        if actual_slip > exp_slip * 2.5 and actual_slip > 0.12:
            faults.append(
                f"HIGH SLIP {actual_slip*100:.1f}% (expected {exp_slip*100:.1f}%) "
                f"— rotor bar fault or mechanical drag"
            )
        if actual_slip < 0.005 and curr > I_RATED * 0.8:
            faults.append(
                f"ABNORMAL LOW SLIP {actual_slip*100:.2f}% with I={curr:.1f}A "
                f"— VFD over-frequency or capacitor bank fault"
            )
    if pow_kw > 0.1 and curr > 1.0:
        s_app    = math.sqrt(3) * volt * curr / 1000
        p_exp    = s_app * PF
        dev      = abs(pow_kw - p_exp) / max(p_exp, 0.1)
        if dev > 0.30:
            faults.append(
                f"POWER FACTOR ANOMALY: {pow_kw:.2f}kW measured vs {p_exp:.2f}kW expected "
                f"({dev*100:.0f}% deviation) — phase loss or capacitor fault"
            )
    if len(temps)>=8 and len(currs)>=8:
        dt_actual  = temps[-1] - temps[0]
        di_squared = currs[-1]**2 - currs[0]**2
        if dt_actual > 12 and di_squared < 5:
            faults.append(
                f"THERMAL ANOMALY: +{dt_actual:.1f}C without current increase "
                f"— blocked ventilation or degraded cooling"
            )
    if rpm < 30 and curr > 3.0:
        faults.append(
            f"POSSIBLE STALL: RPM={rpm:.0f} with I={curr:.1f}A "
            f"— locked rotor; stall current can reach {I_RATED*7:.0f}A"
        )
    if volt > 430 and curr > I_RATED * 0.85 and rpm > 1000:
        faults.append(
            f"OVERVOLTAGE SATURATION: V={volt:.0f}V I={curr:.1f}A at medium load "
            f"— magnetic core saturating, iron losses increasing"
        )
    if curr > 3.0 and rpm > 200 and pow_kw > 0.2:
        load_est    = min(curr / I_RATED, 1.5)
        speed_frac  = rpm / RPM_RATED
        p_shaft_exp = P_RATED * load_est * speed_frac / 1000
        p_elec_exp  = p_shaft_exp / EFF
        if pow_kw > p_elec_exp * 1.35:
            eff_act = (p_shaft_exp / pow_kw) * 100
            faults.append(
                f"EFFICIENCY DEGRADATION: {pow_kw:.2f}kW consumed vs {p_elec_exp:.2f}kW expected "
                f"(est. efficiency {eff_act:.0f}% vs rated 91%) — winding or friction loss"
            )
    if volt > 370 and curr > I_RATED * 1.2 and rpm < RPM_RATED * 0.85 and rpm > 100:
        faults.append(
            f"POSSIBLE PHASE IMBALANCE: I={curr:.1f}A ({curr/I_RATED*100:.0f}% of rated) "
            f"with V={volt:.0f}V at RPM={rpm:.0f} — check all 3 phases with clamp meter"
        )

    return faults


# PROMPT BUILDER
def build_messages(rows, faults):
    rpms  = [float(r["rpm"])            for r in rows]
    temps = [float(r["temperature_c"])  for r in rows]
    vibs  = [float(r["vibration_mm_s"]) for r in rows]
    currs = [float(r["current_a"])      for r in rows]
    volts = [float(r["voltage_v"])      for r in rows]
    tr    = lambda v: "rising" if v[-1]>v[0]*1.05 else ("falling" if v[-1]<v[0]*0.95 else "stable")

    data = "\n".join(
        f"{r['timestamp']}  RPM={r['rpm']}  Temp={r['temperature_c']}C  "
        f"Vib={r['vibration_mm_s']}mm/s  I={r['current_a']}A  V={r['voltage_v']}V  P={r.get('power_kw','?')}kW"
        for r in rows[-15:]
    )
    fault_summary = (
        "Rule engine flagged:\n" + "\n".join(f"- {f}" for f in faults)
    ) if faults else "Rule engine: no threshold violations."

    system_text = (
        "You are FactoryGuard AI, a senior electrical engineer. "
        "Write in plain text only, never use asterisks or markdown. Write like a technical maintenance report.\n\n"
        "Motor: 3-phase induction motor, 400V, 7.5kW, 1450 RPM (4-pole 50Hz, sync 1500 RPM), "
        "15.2A rated, insulation class F, PF=0.85, efficiency 91%.\n"
        "Normal: V 380-420V, I < 15.2A, T < 80C, vib < 4.5 mm/s ISO 10816, slip 3-6%.\n"
        "Warning: V < 360V or > 430V, I > 17A, T > 80C, vib > 4.5 mm/s.\n"
        "Critical: V < 340V, I > 20A, T > 100C, vib > 7.1 mm/s."
    )
    user_text = (
        f"Sensor data (last {len(rows)} seconds):\n{data}\n\n"
        f"Trends: RPM {tr(rpms)}, temp {tr(temps)}, vib {tr(vibs)}, current {tr(currs)}, voltage {tr(volts)}.\n\n"
        f"{fault_summary}\n\n"
        "Give a complete engineering diagnosis:\n\n"
        "STATUS: HEALTHY, WARNING, or CRITICAL — one sentence why.\n\n"
        "OBSERVATIONS: 2 sentences with specific numbers and deviations from rated.\n\n"
        "ROOT CAUSE: 2-3 sentences explaining the physics (voltage-current-torque-slip-I2R).\n\n"
        "RECOMMENDED ACTIONS:\n"
        "Action 1 IMMEDIATE or THIS WEEK: specific tool or location.\n"
        "Action 2 IMMEDIATE or THIS WEEK: specific tool or location.\n"
        "Action 3 NEXT MAINTENANCE: preventive action.\n\n"
        "RISK ASSESSMENT: time to failure, shutdown recommendation, safety risk level."
    )
    return system_text, user_text


# GEMINI 
def call_gemini(system_text, user_text):
    global rate_limit_penalty
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            payload = json.dumps({
                "system_instruction": {"parts": [{"text": system_text}]},
                "contents": [{"role": "user", "parts": [{"text": user_text}]}],
                "generationConfig": {"temperature": 0.15, "maxOutputTokens": 600}
            }).encode("utf-8")
            req = urllib.request.Request(
                GEMINI_URL, data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=API_TIMEOUT) as resp:
                data = json.loads(resp.read().decode())
                rate_limit_penalty = 0
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            if e.code == 429:
                rate_limit_penalty = 120
                print(f"\n{Y}  Rate limit (429). Waiting 90s...{RST}")
                time.sleep(90)
                continue
            return f"API Error {e.code}: {body[:200]}"
        except Exception as e:
            if attempt < MAX_RETRIES:
                print(f"\n{Y}  Attempt {attempt} failed: {e}. Retrying in 8s...{RST}")
                time.sleep(8)

    return (
        "STATUS: UNAVAILABLE\n\n"
        "OBSERVATIONS: Gemini API did not respond after all retry attempts. "
        "Sensor data is still being collected and Dynatrace metrics are still being pushed.\n\n"
        "ROOT CAUSE: API timeout or rate limit exhausted on the free tier (15 req/min). "
        "The agent will retry at the next cooldown interval.\n\n"
        "RECOMMENDED ACTIONS:\n"
        "Action 1 IMMEDIATE: Review the live sensor readings above manually.\n"
        "Action 2 THIS WEEK: Consider a paid Gemini API key to avoid rate limits.\n"
        "Action 3 NEXT MAINTENANCE: Inspect motor physically if any reading exceeds critical threshold.\n\n"
        "RISK ASSESSMENT: Cannot assess automatically. If any reading exceeds critical threshold, shut down immediately."
    )


# OUTPUT RENDERER 
def print_analysis(text, faults, count):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n\n{C}{'━'*68}{RST}")
    print(f"{BOLD}{C}  AI DIAGNOSIS #{count}   [{ts}]{RST}")
    if faults:
        print(f"{R}  {len(faults)} fault(s) flagged:{RST}")
        for f in faults:
            print(f"  {R}  > {f}{RST}")
    else:
        print(f"{G}  No faults detected{RST}")
    print(f"{C}{'━'*68}{RST}\n")

    for line in text.split("\n"):
        s   = line.rstrip()
        if not s.strip(): print(); continue
        low = s.lower()
        su  = s.upper()
        if   low.startswith("status"):
            col = R+BOLD if "CRITICAL" in su else (Y+BOLD if "WARNING" in su else (DIM if "UNAVAILABLE" in su else G+BOLD))
            print(f"\n  {col}{s}{RST}")
        elif low.startswith("observ"):    print(f"\n  {C+BOLD}{s}{RST}")
        elif low.startswith("root"):      print(f"\n  {M+BOLD}{s}{RST}")
        elif low.startswith("recommend"): print(f"\n  {Y+BOLD}{s}{RST}")
        elif low.startswith("risk"):      print(f"\n  {R+BOLD}{s}{RST}")
        elif s.strip().lower().startswith("action"):
            ac = R if "IMMEDIATE" in su else (Y if "THIS WEEK" in su else DIM)
            print(f"    {ac}{s}{RST}")
        else:
            print(f"  {s}")

    print(f"\n{DIM}{'─'*68}")
    print(f"Next analysis in {ANALYSIS_COOLDOWN}s  |  Ctrl+C to stop{RST}\n")

def print_live(row, countdown, n_faults, dt_ok):
    ts   = datetime.now().strftime("%H:%M:%S")
    temp = float(row["temperature_c"])
    vib  = float(row["vibration_mm_s"])
    curr = float(row["current_a"])
    volt = float(row["voltage_v"])
    st   = row["status"]
    tc   = R if temp>100 else (Y if temp>80  else G)
    vc   = R if vib >7.1 else (Y if vib >4.5 else G)
    ic   = R if curr>18  else (Y if curr>14  else G)
    vc2  = R if volt<340 else (Y if volt<380 else G)
    sc   = R+BOLD if "CRITICAL" in st else (Y+BOLD if "WARNING" in st else (DIM if "IDLE" in st else G))
    fs   = f"{R}[{n_faults} FAULT{'S' if n_faults!=1 else ''}]{RST}" if n_faults else f"{G}[OK]{RST}"
    cd   = f"{C}AI RUNNING{RST}" if countdown<=0 else f"{DIM}AI in {countdown}s{RST}"
    dt   = f"{C}DT✓{RST}" if dt_ok else f"{DIM}DT-{RST}"
    print(
        f"\r{DIM}[{ts}]{RST} "
        f"RPM:{C}{row['rpm']:>7}{RST} "
        f"T:{tc}{temp:>6.1f}C{RST} "
        f"Vib:{vc}{vib:>5.3f}{RST} "
        f"I:{ic}{curr:>5.2f}A{RST} "
        f"V:{vc2}{volt:>6.1f}V{RST} "
        f"|{sc}{st}{RST} {fs} {cd} {dt}   ",
        end="", flush=True
    )


def run_analysis(rows):
    global ai_running, analysis_count, last_analysis_time, rate_limit_penalty
    ai_running = True
    analysis_count += 1
    cnt    = analysis_count
    faults = detect_faults(rows)
    print(f"\n\n{C}Analysing {len(rows)} readings ({len(faults)} faults)...{RST}")

    # Push to Dynatrace before AI call
    push_metrics_to_dynatrace(rows[-1], len(faults), rows[-1].get("status","NORMAL"))
    if faults:
        push_event_to_dynatrace(
            faults, rows[-1].get("status","NORMAL"),
            float(rows[-1]["current_a"]),
            float(rows[-1]["temperature_c"]),
            float(rows[-1]["vibration_mm_s"])
        )

    sys_text, usr_text = build_messages(rows, faults)
    result = call_gemini(sys_text, usr_text)
    print_analysis(result, faults, cnt)
    last_analysis_time = time.time() + rate_limit_penalty
    ai_running = False


def main():
    global last_analysis_time
    print(f"\n{C+BOLD}FACTORYGUARD AI v8 — Motor Intelligence Agent{RST}")
    print(f"{G}Model: {MODEL} | Cooldown: {ANALYSIS_COOLDOWN}s | 23 fault rules | Dynatrace: {DT_URL[:30]}...{RST}\n")
    print(f"{DIM}Start motor_simulator.py in another terminal...{RST}\n")
    last_analysis_time = time.time()
    dt_ok = False
    dt_push_tick = 0

    while True:
        rows      = read_csv_tail(HISTORY_SIZE)
        now       = time.time()
        elapsed   = now - last_analysis_time
        countdown = max(0, int(ANALYSIS_COOLDOWN - elapsed))

        if not rows:
            print(f"\r{DIM}Waiting for simulator...{RST}", end="", flush=True)
            time.sleep(1)
            continue

        faults = detect_faults(rows)

        dt_push_tick += 1
        if dt_push_tick >= 30:
            try:
                push_metrics_to_dynatrace(rows[-1], len(faults), rows[-1].get("status","NORMAL"))
                dt_ok = True
            except Exception:
                dt_ok = False
            dt_push_tick = 0

        print_live(rows[-1], countdown, len(faults), dt_ok)

        if len(rows) >= MIN_ROWS and elapsed >= ANALYSIS_COOLDOWN and not ai_running:
            threading.Thread(target=run_analysis, args=(list(rows),), daemon=True).start()

        time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{DIM}Agent stopped.{RST}\n")

