# ⚙ FactoryGuard AI

**Real-time AI diagnostic agent for 3-phase industrial motors**

Built for the [Google Cloud Rapid Agent Hackathon 2026](https://googlecloudagenthackathon.devpost.com) — Dynatrace Partner Track

---

## What It Does

FactoryGuard AI monitors a **400V / 7.5kW / 1450 RPM 3-phase induction motor** in real time. It reads live sensor data every second, detects faults using a physics-based rule engine, and sends the data to **Google Gemini AI** for a full engineering diagnosis — explaining root causes and recommending specific maintenance actions.

This is predictive maintenance: catching failures **before** they happen.

---

## Demo

![FactoryGuard Demo](docs/demo.png)

**Simulator** (left) — control motor load, RPM, voltage, inject faults  
**AI Agent** (right) — live diagnosis every 30 seconds

---

## Features

- **Real motor physics** — current, temperature, vibration and power calculated from real electrical engineering equations
- **6 live sensors** — RPM, temperature (°C), vibration (mm/s ISO 10816), current (A), voltage (V), power (kW)
- **15 fault conditions** — voltage drop, overcurrent, bearing fault, cooling failure, overtemperature, and more
- **Gemini AI diagnosis** — 5-section structured report: status, observations, root cause, actions, risk
- **Fault injection** — simulate overtemperature, bearing fault, voltage drop, overcurrent with one click
- **Real-time CSV export** — sensor log updated every second

---

## Architecture

```
Motor Simulator (Python + Tkinter)
         │
         │  writes every 1 second
         ▼
    motor_data.csv
         │
         │  reads every second
         ▼
  AI Agent (Python)
  ├── Rule Engine (15 fault conditions)
  └── Google Gemini 3.5 Flash API
            │
            ▼
  Engineering Diagnosis
  STATUS / OBSERVATIONS / ROOT CAUSE / ACTIONS / RISK
```

---

## Motor Physics Model

All sensor values use real electrical engineering equations:

| Sensor | Formula |
|--------|---------|
| Current | `I = P / (√3 × V × cosφ)` — rises when voltage drops |
| Temperature | `T = T_ambient + k × I²` — Joule heating model |
| Vibration | ISO 10816 standard — spikes on bearing fault |
| Power | `P = √3 × V × I × cosφ / 1000` kW |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Simulation | Python 3.10 + Tkinter |
| AI Reasoning | Google Gemini 3.5 Flash |
| Orchestration | Google Cloud Agent Builder |
| Monitoring | Dynatrace MCP Server |
| Web Dashboard | Streamlit |
| Deployment | Google Cloud Run |

---

## Quick Start

### Requirements
```
Python 3.10+
```

### Install dependencies
```bash
pip install tk
```

### Get a free Gemini API key
Go to [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) and create a key (free, starts with `AIza...`)

### Add your key
Open `agent/motor_agent.py` line 12 and replace:
```python
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"
```
with your actual key.

### Run — open two terminals

**Terminal 1 — Motor Simulator:**
```bash
cd simulator
python motor_simulator.py
```

**Terminal 2 — AI Agent:**
```bash
cd agent
python motor_agent.py
```

---

## How to Use

| Control | Effect |
|---------|--------|
| Load slider (0-100%) | Scales current, temperature, power |
| RPM setpoint (0-1500) | Controls motor speed |
| Voltage slider (280-440V) | Simulates supply voltage issues |
| Overtemperature button | Adds +35°C to simulate cooling failure |
| Bearing Fault button | Spikes vibration to >8 mm/s + RPM drop |
| Voltage Drop button | Forces voltage to 78% of set value |
| Overcurrent button | Multiplies current by 1.45× |

---

## Fault Scenarios for Demo

| Scenario | How to trigger | What AI detects |
|----------|---------------|-----------------|
| Voltage drop | Move voltage slider to 310V | Overcurrent, winding overload risk |
| Bearing failure | Check Bearing Fault | Vibration >8 mm/s, RPM drop, thermal rise |
| Overtemperature | Check Overtemperature | Cooling failure, insulation degradation risk |
| Combined fault | Low voltage + Overtemperature | Multiple cascading failure chain |

---

## Project Structure

```
factoryguard-ai/
├── simulator/
│   └── motor_simulator.py    # Tkinter GUI — real-time motor simulation
├── agent/
│   └── motor_agent.py        # Gemini AI diagnostic agent
├── README.md                 # This file
└── FACTORYGUARD_PROJECT.md   # Full technical documentation
```

---

## About

Built by **Hamza Manai** — Electrical Engineering graduate, Industry 4.0 Master's student, Tunisia.

Domain expertise: predictive maintenance, resistance welding machines, 3-phase motor protection systems.

---

## License

MIT License — see [LICENSE](LICENSE) for details.
