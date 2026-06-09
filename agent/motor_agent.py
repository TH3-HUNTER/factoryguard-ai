"""
FactoryGuard AI — Motor Intelligence Agent v7
- Prompt completely rewritten: no formatting instructions, clean system+user separation
- Gemini gets data only, responds naturally as an engineer
- All previous fixes kept (30s cooldown, 45s timeout, 429 handler, min 10 rows)
"""

import csv, time, os, json, urllib.request, urllib.error
from datetime import datetime
import threading

CSV_FILE          = os.path.join(os.path.dirname(__file__), "..", "simulator", "motor_data.csv")
GEMINI_API_KEY    = "YOUR_GEMINI_API_KEY_HERE"
MODEL             = "gemini-3.5-flash"
GEMINI_URL        = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={GEMINI_API_KEY}"
ANALYSIS_COOLDOWN = 30
HISTORY_SIZE      = 20
API_TIMEOUT       = 45
MAX_RETRIES       = 2
MIN_ROWS          = 10

R="\033[91m"; Y="\033[93m"; G="\033[92m"; C="\033[96m"
M="\033[95m"; W="\033[97m"; DIM="\033[90m"; RST="\033[0m"; BOLD="\033[1m"

last_analysis_time = 0
analysis_count     = 0
ai_running         = False

def read_csv_tail(n=20):
    try:
        with open(CSV_FILE, "r") as f:
            rows = list(csv.DictReader(f))
            return rows[-n:] if rows else []
    except FileNotFoundError:
        return []

def detect_faults(rows):
    if not rows or len(rows) < 3:
        return []
    faults = []
    l    = rows[-1]
    volt = float(l["voltage_v"])
    curr = float(l["current_a"])
    temp = float(l["temperature_c"])
    vib  = float(l["vibration_mm_s"])
    rpm  = float(l["rpm"])
    temps = [float(r["temperature_c"])  for r in rows]
    vibs  = [float(r["vibration_mm_s"]) for r in rows]
    rpms  = [float(r["rpm"])            for r in rows]

    if volt < 360:  faults.append(f"LOW VOLTAGE {volt:.0f}V (rated 400V)")
    if volt < 340:  faults.append(f"CRITICAL UNDERVOLTAGE {volt:.0f}V")
    if volt > 430:  faults.append(f"OVERVOLTAGE {volt:.0f}V")
    if curr > 18:   faults.append(f"OVERCURRENT {curr:.1f}A (rated 15.2A)")
    if curr > 22:   faults.append(f"CRITICAL OVERCURRENT {curr:.1f}A")
    if volt < 370 and curr > 16:
        faults.append(f"VOLTAGE DROP CAUSING OVERCURRENT: V={volt:.0f}V I={curr:.1f}A")
    if temp > 80:   faults.append(f"HIGH TEMPERATURE {temp:.1f}C")
    if temp > 100:  faults.append(f"CRITICAL TEMPERATURE {temp:.1f}C")
    exp_t = 25 + 50*(curr/15.2)
    if temp > exp_t + 20:
        faults.append(f"COOLING FAILURE: measured {temp:.1f}C expected {exp_t:.0f}C")
    if vib > 4.5:   faults.append(f"HIGH VIBRATION {vib:.3f} mm/s")
    if vib > 7.1:   faults.append(f"CRITICAL VIBRATION {vib:.3f} mm/s")
    if len(rpms)>=5 and (rpms[0]-rpms[-1])>80 and curr<18:
        faults.append(f"UNEXPLAINED RPM DROP -{rpms[0]-rpms[-1]:.0f} RPM")
    if len(temps)>=5 and temps[-1]-temps[0]>8:
        faults.append(f"TEMPERATURE RISING +{temps[-1]-temps[0]:.1f}C in {len(temps)}s")
    if len(vibs)>=5 and vibs[-1]-vibs[0]>2:
        faults.append(f"VIBRATION RISING +{vibs[-1]-vibs[0]:.3f} mm/s in {len(vibs)}s")
    return faults

def build_messages(rows, faults):
    """
    Use system+user message format.
    System: who Gemini is and the motor specs (no formatting instructions).
    User: the actual data and a plain question.
    """
    rpms  = [float(r["rpm"])            for r in rows]
    temps = [float(r["temperature_c"])  for r in rows]
    vibs  = [float(r["vibration_mm_s"]) for r in rows]
    currs = [float(r["current_a"])      for r in rows]
    volts = [float(r["voltage_v"])      for r in rows]
    tr    = lambda v: "rising" if v[-1]>v[0]*1.05 else ("falling" if v[-1]<v[0]*0.95 else "stable")

    data = "\n".join(
        f"{r['timestamp']}  RPM={r['rpm']}  Temp={r['temperature_c']}C  "
        f"Vib={r['vibration_mm_s']}mm/s  Current={r['current_a']}A  Voltage={r['voltage_v']}V"
        for r in rows[-15:]
    )

    fault_summary = (
        "The rule engine flagged these issues:\n" +
        "\n".join(f"- {f}" for f in faults)
    ) if faults else "The rule engine found no threshold violations."

    system_text = """You are FactoryGuard AI, a senior electrical engineer. You write in plain text only, never use asterisks, never use bold or italic markdown, never use symbols like ** or *. Write like a technical report.

Motor under analysis: 3-phase induction motor, 400V nominal, 7.5kW, 1450 RPM rated speed, 15.2A rated current, insulation class F (max 155C), power factor 0.85.

Normal operating ranges: voltage 380-420V, current below 14A at partial load up to 15.2A at full load, temperature below 80C, vibration below 4.5 mm/s (ISO 10816).
Warning thresholds: voltage below 360V or above 430V, current above 17A, temperature above 80C, vibration above 4.5 mm/s.
Critical thresholds: voltage below 340V, current above 20A, temperature above 100C, vibration above 7.1 mm/s.

You give direct, specific, useful engineering diagnoses. You always reference the actual sensor numbers. You explain root causes using real electrical engineering principles. You give maintenance actions with specific tools and locations. You are never vague."""

    user_text = f"""Here is the real-time sensor data from the motor over the last {len(rows)} seconds:

{data}

Sensor trends: RPM is {tr(rpms)}, temperature is {tr(temps)}, vibration is {tr(vibs)}, current is {tr(currs)}, voltage is {tr(volts)}.

{fault_summary}

Give me a complete engineering diagnosis with these four sections:

STATUS: state HEALTHY, WARNING, or CRITICAL and give one sentence explaining why.

OBSERVATIONS: describe in 2 sentences what you see in the sensor data, with specific numbers and how much they deviate from rated values.

ROOT CAUSE: explain in 2-3 sentences what is physically happening in the motor and why, using electrical engineering principles such as the relationship between voltage, current and torque.

RECOMMENDED ACTIONS: give 3 specific actions the maintenance engineer should take, ranked by urgency. For each action state whether it is immediate, within this week, or at next scheduled maintenance, and mention the specific tool or location.

RISK ASSESSMENT: state the estimated time to failure if no action is taken, whether immediate shutdown is recommended, and the safety risk level for personnel."""

    return system_text, user_text

def call_gemini(system_text, user_text):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            payload = json.dumps({
                "system_instruction": {"parts": [{"text": system_text}]},
                "contents": [{"role": "user", "parts": [{"text": user_text}]}],
                "generationConfig": {
                    "temperature": 0.15,
                    "maxOutputTokens": 500,
                }
            }).encode("utf-8")
            req = urllib.request.Request(
                GEMINI_URL, data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=API_TIMEOUT) as resp:
                data = json.loads(resp.read().decode())
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            if e.code == 429:
                print(f"\n{Y}  Rate limit hit. Waiting 65s...{RST}")
                time.sleep(65)
                continue
            return f"API Error {e.code}: {body[:200]}"
        except Exception as e:
            if attempt < MAX_RETRIES:
                print(f"\n{Y}  Attempt {attempt} failed: {e}. Retrying in 5s...{RST}")
                time.sleep(5)
            else:
                return f"Failed after {MAX_RETRIES} attempts: {e}"

def print_analysis(text, faults, count):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n\n{C}{'━'*68}{RST}")
    print(f"{BOLD}{C}  AI DIAGNOSIS #{count}   [{ts}]{RST}")
    if faults:
        print(f"{R}  Flagged faults: {len(faults)}{RST}")
        for f in faults:
            print(f"  {R}  > {f}{RST}")
    print(f"{C}{'━'*68}{RST}\n")

    # Print response — color section headers, print everything else as-is
    for line in text.split("\n"):
        s = line.rstrip()
        if not s.strip():
            print(); continue
        low = s.lower()
        if   low.startswith("status"):          print(f"\n  {R+BOLD if 'CRITICAL' in s.upper() else (Y+BOLD if 'WARNING' in s.upper() else G+BOLD)}{s}{RST}")
        elif low.startswith("observ"):          print(f"\n  {C+BOLD}{s}{RST}")
        elif low.startswith("root cause"):      print(f"\n  {M+BOLD}{s}{RST}")
        elif low.startswith("recommend"):       print(f"\n  {Y+BOLD}{s}{RST}")
        elif low.startswith("risk"):            print(f"\n  {R+BOLD}{s}{RST}")
        elif s.strip().startswith(("1.","2.","3.","-")): print(f"    {W}{s}{RST}")
        else:                                   print(f"  {s}")

    print(f"\n{DIM}{'─'*68}")
    print(f"Next analysis in {ANALYSIS_COOLDOWN}s  |  Ctrl+C to stop{RST}\n")

def print_live(row, countdown, n_faults):
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
    print(
        f"\r{DIM}[{ts}]{RST} "
        f"RPM:{C}{row['rpm']:>7}{RST} "
        f"T:{tc}{temp:>6.1f}C{RST} "
        f"Vib:{vc}{vib:>5.3f}{RST} "
        f"I:{ic}{curr:>5.2f}A{RST} "
        f"V:{vc2}{volt:>6.1f}V{RST} "
        f"|{sc}{st}{RST} {fs} {cd}   ",
        end="", flush=True
    )

def run_analysis(rows):
    global ai_running, analysis_count, last_analysis_time
    ai_running = True
    analysis_count += 1
    cnt    = analysis_count
    faults = detect_faults(rows)
    print(f"\n\n{C}Analysing {len(rows)} readings ({len(faults)} faults)...{RST}")
    sys_text, usr_text = build_messages(rows, faults)
    result = call_gemini(sys_text, usr_text)
    print_analysis(result, faults, cnt)
    last_analysis_time = time.time()
    ai_running = False

def main():
    global last_analysis_time
    if "YOUR_GEMINI_API_KEY" in GEMINI_API_KEY:
        print(f"{R}Paste your AIza... key on line 12!{RST}")
        return
    print(f"\n{C+BOLD}FACTORYGUARD AI v7 — Motor Intelligence Agent{RST}")
    print(f"{G}Gemini ready | {ANALYSIS_COOLDOWN}s cooldown | 429 handled | needs {MIN_ROWS} rows{RST}\n")
    print(f"{DIM}Start motor_simulator.py in another terminal...{RST}\n")
    last_analysis_time = time.time()

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
        print_live(rows[-1], countdown, len(faults))

        if len(rows) >= MIN_ROWS and elapsed >= ANALYSIS_COOLDOWN and not ai_running:
            threading.Thread(target=run_analysis, args=(list(rows),), daemon=True).start()

        time.sleep(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{DIM}Agent stopped.{RST}\n")
