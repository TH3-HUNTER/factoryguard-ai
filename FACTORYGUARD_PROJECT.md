# FactoryGuard AI — Complete Project Documentation

> **Hackathon:** Google Cloud Rapid Agent Hackathon 2026
> **Track:** Dynatrace Partner Track
> **Deadline:** June 11, 2026 @ 10:00 PM GMT+1
> **Prize target:** $5,000 (1st place — Dynatrace track)
> **Developer:** Hamza Manai — Electrical Engineering / Industry 4.0
> **Last updated:** June 8, 2026 — v5

---

## 1. Project Summary

**FactoryGuard AI** is an intelligent real-time monitoring and diagnostic agent for 3-phase industrial motors. It simulates a 400V / 7.5kW / 1450 RPM induction motor, collects live sensor data every second, and uses **Google Gemini 1.5 Flash AI** to perform multi-step engineering diagnosis — detecting faults, identifying root causes, and recommending specific maintenance actions with urgency rankings.

The project targets predictive maintenance in Industry 4.0 environments. The developer has direct academic and professional expertise: Electrical Engineering degree, Industry 4.0 Master's studies, PFE in predictive maintenance, and resistance welding machine experience.

---

## 2. The Problem We Solve

Industrial motors fail unexpectedly in factories. A single unplanned shutdown can cost thousands of euros per hour. Traditional systems only alarm when the fault has already occurred. FactoryGuard AI predicts failures BEFORE they happen by:

- Continuously reading 6 sensor channels every second
- Applying 15 rule-based fault conditions with real motor physics
- Using Gemini AI to reason about root causes like an expert engineer
- Recommending specific actions ranked by urgency (IMMEDIATE / THIS WEEK / NEXT MAINTENANCE)
- Estimating time to failure so maintenance can be scheduled proactively

---

## 3. System Architecture

```
COMPUTER (local)
│
├── motor_simulator.py  (Terminal 1)
│   ├── Tkinter dark GUI
│   ├── 3 sliders: Load % / RPM setpoint / Supply voltage
│   ├── 4 fault injection buttons
│   ├── Live 6-sensor display
│   └── Writes motor_data.csv every 1 second
│
├── motor_data.csv  (shared file, updated live)
│
└── motor_agent.py  (Terminal 2)
    ├── Reads CSV every 1 second
    ├── Shows live color-coded sensor bar with countdown
    ├── Rule engine: detects 15 fault conditions
    ├── Every 8 seconds: sends data + faults to Gemini AI
    ├── Retry logic: up to 2 retries on timeout (30s each)
    └── Prints complete structured diagnosis

CLOUD (Gemini API)
└── gemini-1.5-flash
    ├── Receives: 12 rows history + trends + pre-detected faults
    ├── Prompt: expert electrical engineer role
    ├── Output: STATUS / WHAT I SEE / ROOT CAUSE / ACTIONS / PREDICTION
    ├── Temperature: 0.1 (deterministic)
    └── Max tokens: 400 (fast, never cut off)
```

---

## 4. Motor Physics Model

All sensor values are calculated from real electrical engineering equations.

### RPM
```
rpm = rpm_setpoint x (1 - slip)
slip = 0.05 x load_fraction
bearing_fault: rpm x 0.93  (7% reduction from friction)
```

### Current (KEY EQUATION — explains voltage-current relationship)
```
I = P_shaft / (0.91 x sqrt(3) x V x PF)  then multiplied by (V_rated / V_actual)
```
This is why voltage drop causes overcurrent: at 300V the motor draws ~20A instead of 15.2A to maintain torque. This is real motor behavior, not a simulation trick.

### Temperature (Joule heating model)
```
T = T_ambient + k x I^2
k = (T_rated - T_ambient) / I_rated^2
```
Temperature is driven by I²R losses. High current = high temperature. This is why voltage drop also causes overheating.

### Vibration (ISO 10816 standard)
```
vib = 0.5 + 1.8 x load  [mm/s]
bearing_fault adds: +8.5 mm/s + sinusoidal component
low_voltage adds: +(360-V)/60  (unbalanced magnetic pull)
```

### Power
```
P = sqrt(3) x V x I x PF / 1000  [kW]   PF = 0.85
```

### Fault Thresholds
| Parameter    | Normal      | Warning       | Critical     |
|-------------|-------------|---------------|--------------|
| Temperature  | < 80°C      | 80 – 100°C    | > 100°C      |
| Vibration    | < 4.5 mm/s  | 4.5 – 7.1 mm/s | > 7.1 mm/s  |
| Current      | < 14A       | 14 – 18A      | > 18A        |
| Voltage      | 380 – 420V  | 340 – 380V    | < 340V       |

---

## 5. Rule Engine — 15 Fault Conditions

The agent detects faults BEFORE sending to AI, giving Gemini more context:

| # | Condition | Logic |
|---|-----------|-------|
| 1 | Low voltage | V < 360V |
| 2 | Critical undervoltage | V < 340V |
| 3 | Overvoltage | V > 430V |
| 4 | Overcurrent | I > 18A |
| 5 | Critical overcurrent | I > 22A |
| 6 | Voltage-current mismatch | V < 370V AND I > 16A |
| 7 | Overload at high speed | RPM > 1400 AND I > 20A |
| 8 | High temperature | T > 80°C |
| 9 | Critical temperature | T > 100°C |
| 10 | Cooling anomaly | T > expected(I) + 20°C |
| 11 | High vibration | Vib > 4.5 mm/s |
| 12 | Critical vibration | Vib > 7.1 mm/s |
| 13 | Vibration at low speed | Vib > 5 AND RPM < 800 |
| 14 | Unexplained RPM drop | RPM drop > 80 without current rise |
| 15 | Temperature/vibration trend | Rising +8°C or +2mm/s over 20s |

---

## 6. AI Agent — Gemini Reasoning

The AI is NOT if/else logic. Gemini receives the sensor history, trends, and pre-detected faults, then reasons like an expert engineer through 5 sections:

**Prompt output format (plain text, no markdown — v5 fix):**
```
STATUS: CRITICAL

WHAT I SEE:
Voltage is 342V which is 14.5 percent below the rated 400V. Current is 19.7A
which is 29.6 percent above the rated 15.2A.

ROOT CAUSE:
When supply voltage drops, the motor must draw more current to maintain its
output torque, following the equation I = P divided by root3 times V times
power factor. At 342V the motor draws 19.7A causing I-squared-R losses that
raise winding temperature to 109°C, dangerously close to insulation failure.

ACTIONS:
Action 1 IMMEDIATE: Measure all three phase voltages at the motor terminal
box with a multimeter to confirm the drop and identify which phase is affected.
Action 2 IMMEDIATE: Check the main contactor and cable connections for
loose terminals or oxidation between the distribution panel and the motor.
Action 3 NEXT MAINTENANCE: Inspect the upstream transformer tap settings
and verify cable cross-section is adequate for the motor rated current.

PREDICTION:
Without action, winding insulation failure is expected within 4 to 6 hours
due to sustained overcurrent; immediate shutdown is recommended; personnel
safety risk is MEDIUM due to potential arc flash at the distribution panel.
```

---

## 7. Version History

| Version | Date | Changes |
|---------|------|---------|
| v1 | June 7 | Basic simulator + terminal agent, 10s interval |
| v2 | June 7 | Added RPM slider, improved AI prompt |
| v3 | June 8 | Fixed output cutoff, reduced to 5s interval |
| v4 | June 8 | Fixed voltage physics (V-I relationship), 15 fault conditions, time-based trigger |
| v5 | June 8 | Fixed timeout (retry x2, 30s), fixed cutoff (no markdown prompt), complete output guaranteed |

---

## 8. Current Project Status

### Done
| Component | Status |
|-----------|--------|
| Motor Simulator GUI | Done — 3 sliders, 4 faults, live display |
| Motor Physics Model | Done — real equations, V-I relationship correct |
| CSV Export | Done — every 1 second, 8 columns |
| Rule Engine | Done — 15 fault conditions |
| Gemini AI Integration | Done — working, retry on timeout |
| AI Diagnosis | Done — 5 sections, plain text, never cut off |
| Countdown display | Done — live bar shows AI in Xs |
| Python on Windows | Done — Python 3.10 |

### Not Done (Critical for Hackathon)
| Component | Priority | Why Needed |
|-----------|----------|------------|
| Google Cloud Agent Builder | CRITICAL | Hackathon rule — required |
| Dynatrace MCP server | CRITICAL | Hackathon rule — required |
| Streamlit web dashboard | HIGH | Judges need hosted URL |
| Deploy on Google Cloud Run | HIGH | Submission requires live URL |
| Public GitHub repository | HIGH | Required for submission |
| Architecture diagram image | MEDIUM | Required in submission |
| 3-minute demo video | MEDIUM | Required for submission |
| Devpost submission form | MEDIUM | Must complete before deadline |

---

## 9. Next Steps — Day by Day

### Today June 8 (remaining hours)
- Create GitHub account and push code to public repo
- Create Dynatrace free trial at dynatrace.com/trial

### June 9 — Most Important Day
- Build Streamlit web dashboard (replaces terminal)
- Integrate Dynatrace MCP server
- Deploy to Google Cloud Run
- Connect through Google Cloud Agent Builder

### June 10 — Polish
- Test all 4 fault scenarios through web dashboard
- Create architecture diagram
- Record 3-minute demo video

### June 11 — Deadline Day
- Final submission on Devpost
- Verify GitHub repo is public
- Post in hackathon Discord for community votes (10% of score)

---

## 10. Demo Video Script (3 minutes)

```
0:00 - 0:20  INTRO
"FactoryGuard AI monitors 3-phase industrial motors in real time.
Motor failures cost factories thousands per hour. We prevent them."

0:20 - 0:50  NORMAL OPERATION
Set load 70%, RPM 1450, voltage 400V.
AI says HEALTHY. Show 5-section diagnosis on screen.

0:50 - 1:30  INJECT BEARING FAULT
Check Bearing Fault. Vibration jumps to 11 mm/s.
AI detects in 8 seconds, explains ISO 10816 exceedance,
recommends bearing replacement with urgency level.

1:30 - 2:10  INJECT VOLTAGE DROP
Drop voltage to 310V. Current jumps to 20A.
AI detects VOLTAGE-CURRENT MISMATCH, explains the physics,
recommends checking distribution panel and contactor.

2:10 - 2:40  SHOW ARCHITECTURE
Switch to architecture diagram.
"Google Cloud Agent Builder + Gemini + Dynatrace MCP."

2:40 - 3:00  CLOSE
"FactoryGuard AI — predicting failures before they happen."
```

---

## 11. Judging Criteria Score

| Criterion | Weight | Score | Reason |
|-----------|--------|-------|--------|
| Move Beyond Chat | High | 5/5 | Diagnoses, recommends, estimates risk |
| Multi-Step Mission | High | 5/5 | 5-step reasoning chain |
| Partner Power (Dynatrace) | Required | 0/5 | NOT YET INTEGRATED |
| Real-world relevance | High | 5/5 | Real physics, real industry problem |
| Demo quality | Medium | 3/5 | Needs web UI and video |

---

## 12. File Structure

```
factoryguard/
├── simulator/
│   ├── motor_simulator.py     (220 lines — Tkinter GUI)
│   └── motor_data.csv         (auto-generated, live data)
├── agent/
│   └── motor_agent.py         (215 lines — Gemini AI agent)
├── web/                       (TO CREATE — Streamlit dashboard)
├── cloud/                     (TO CREATE — Agent Builder + Dynatrace config)
├── docs/                      (TO CREATE — architecture diagram)
├── README.md                  (TO CREATE — for GitHub)
├── requirements.txt           (TO CREATE)
└── FACTORYGUARD_PROJECT.md    (this file)
```

---

## 13. Tech Stack

| Layer | Technology | Status |
|-------|-----------|--------|
| Simulation | Python 3.10 + Tkinter | Done |
| Data stream | CSV (1s updates) | Done |
| AI reasoning | Gemini 1.5 Flash API | Done |
| Orchestration | Google Cloud Agent Builder | To do |
| Monitoring | Dynatrace MCP Server | To do |
| Web UI | Streamlit | To do |
| Deployment | Google Cloud Run | To do |
| Repository | GitHub (public) | To do |
| Submission | Devpost | To do |

---

*Last updated: June 8, 2026 — v5*
*Total Python code: ~435 lines*
