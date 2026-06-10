import csv, random
from datetime import datetime, timedelta
import os

t = datetime.now()
rows = []
for i in range(60):
    volt = 400 + random.uniform(-4, 4)
    curr = 10.8 + random.uniform(-0.3, 0.3)
    temp = 57.0 + random.uniform(-1, 1)
    vib  = 1.8 + random.uniform(-0.05, 0.05)
    rpm  = 1422.0 + random.uniform(-8, 8)
    pw   = round((1.732 * volt * curr * 0.85) / 1000, 3)
    rows.append([
        t.strftime('%Y-%m-%d %H:%M:%S'),
        round(rpm, 1), round(temp, 1), round(vib, 3),
        round(curr, 2), round(volt, 1), pw, 'NORMAL'
    ])
    t += timedelta(seconds=1)

os.makedirs('simulator', exist_ok=True)
with open('simulator/motor_data.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['timestamp','rpm','temperature_c','vibration_mm_s',
                'current_a','voltage_v','power_kw','status'])
    w.writerows(rows)
print('Sample CSV generated OK')
