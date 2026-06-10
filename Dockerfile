FROM python:3.10-slim

WORKDIR /app

# Install Python dependencies first (cached layer)
RUN pip install --no-cache-dir streamlit>=1.35.0 pandas>=2.0.0

# Copy project files
COPY . .

# Pre-generate sample CSV so the dashboard has data on startup
RUN mkdir -p simulator && python3 << 'PYEOF'
import csv, random
from datetime import datetime, timedelta
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
with open('simulator/motor_data.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['timestamp','rpm','temperature_c','vibration_mm_s',
                'current_a','voltage_v','power_kw','status'])
    w.writerows(rows)
print('Sample CSV generated OK')
PYEOF

EXPOSE 8080

CMD ["streamlit", "run", "web/app.py", \
     "--server.port=8080", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
