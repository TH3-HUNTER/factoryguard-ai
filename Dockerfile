FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create simulator folder and pre-generate sample CSV so dashboard works on Cloud Run
RUN mkdir -p simulator && python3 -c "
import csv, random
from datetime import datetime, timedelta
t = datetime.now()
rows = []
for i in range(60):
    load = 0.70
    volt = 400 + random.uniform(-4,4)
    curr = (7500*load/0.91)/(1.732*volt*0.85)*(400/volt) + random.uniform(-0.2,0.2)
    temp = 25 + ((50/15.2**2)*curr**2) + random.uniform(-0.3,0.3)
    vib  = 0.5 + 1.8*load + random.uniform(-0.08,0.08)
    pw   = (1.732*volt*curr*0.85)/1000
    rows.append([t.strftime('%Y-%m-%d %H:%M:%S'),round(1422+random.uniform(-8,8),1),round(temp,1),round(vib,3),round(curr,2),round(volt,1),round(pw,3),'NORMAL'])
    t += timedelta(seconds=1)
with open('simulator/motor_data.csv','w',newline='') as f:
    w = csv.writer(f)
    w.writerow(['timestamp','rpm','temperature_c','vibration_mm_s','current_a','voltage_v','power_kw','status'])
    w.writerows(rows)
print('CSV ready')
"

EXPOSE 8080

CMD ["streamlit", "run", "web/app.py", \
     "--server.port=8080", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
