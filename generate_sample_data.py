"""
Generates 120 rows of realistic motor data showing:
- Normal operation for 60s
- Gradual bearing fault developing over 30s  
- Voltage drop fault for 30s
This makes the hosted dashboard look like a real motor in action.
"""
import csv, random, math
from datetime import datetime, timedelta

t = datetime.now() - timedelta(seconds=120)
rows = []

for i in range(120):
    load = 0.70 + random.uniform(-0.02, 0.02)

    # Phase 1 (0-59s): Normal operation
    if i < 60:
        volt = 400 + random.uniform(-4, 4)
        bearing_vib = 0
        bearing_temp = 0
        status = "NORMAL"

    # Phase 2 (60-89s): Bearing fault developing
    elif i < 90:
        volt = 400 + random.uniform(-4, 4)
        severity = (i - 60) / 30.0
        bearing_vib = severity * 8.5 + 2 * math.sin(i * 3.2) * severity
        bearing_temp = severity * 12
        status = "WARNING_BEARING_FAULT" if severity > 0.3 else "NORMAL"

    # Phase 3 (90-119s): Voltage drop
    else:
        volt = 340 + random.uniform(-5, 5)
        bearing_vib = 0
        bearing_temp = 0
        status = "WARNING_LOW_VOLTAGE"

    # Physics calculations
    curr = (7500 * load / 0.91) / (1.732 * volt * 0.85) * (400 / volt)
    curr += random.uniform(-0.2, 0.2)
    k    = 50 / (15.2 ** 2)
    temp = 25 + k * curr ** 2 + bearing_temp + random.uniform(-0.5, 0.5)
    slip = 0.05 * load
    rpm  = 1450 * (1 - slip) * (0.93 if bearing_vib > 3 else 1.0)
    rpm += random.uniform(-6, 6)
    vib  = 0.5 + 1.8 * load + bearing_vib + random.uniform(-0.05, 0.05)
    pw   = round((1.732 * volt * curr * 0.85) / 1000, 3)

    if temp > 100: status = "CRITICAL_OVERTEMPERATURE"
    elif curr > 20: status = "CRITICAL_OVERCURRENT"

    rows.append([
        t.strftime('%Y-%m-%d %H:%M:%S'),
        round(rpm, 1), round(temp, 1), round(max(0, vib), 3),
        round(curr, 2), round(volt, 1), pw, status
    ])
    t += timedelta(seconds=1)

import os
os.makedirs('simulator', exist_ok=True)
with open('simulator/motor_data.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['timestamp','rpm','temperature_c','vibration_mm_s',
                'current_a','voltage_v','power_kw','status'])
    w.writerows(rows)
print(f'Generated {len(rows)} rows with 3 phases: NORMAL → BEARING FAULT → VOLTAGE DROP')
