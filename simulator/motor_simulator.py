"""
FactoryGuard AI — Motor Simulator v4
Corrected physics: voltage drop → overcurrent (real motor behavior)
All logical constraints enforced
"""

import tkinter as tk
import csv, time, math, random, threading, os
from datetime import datetime

CSV_FILE = os.path.join(os.path.dirname(__file__), "motor_data.csv")

# Rated values — 400V 7.5kW 3-phase induction motor
V_RATED   = 400.0
I_RATED   = 15.2
RPM_RATED = 1450
P_RATED   = 7500   # watts
T_AMBIENT = 25
T_RATED   = 75     # at full load
PF        = 0.85

class MotorSimulator:
    def __init__(self, root):
        self.root = root
        self.root.title("FactoryGuard AI — Motor Simulator v4")
        self.root.geometry("820x720")
        self.root.configure(bg="#0f1117")
        self.root.resizable(False, False)
        self.running = True

        self.fault_overtemp     = tk.BooleanVar(value=False)
        self.fault_bearing      = tk.BooleanVar(value=False)
        self.fault_voltage_drop = tk.BooleanVar(value=False)
        self.fault_overcurrent  = tk.BooleanVar(value=False)

        self._init_csv()
        self._build_ui()
        threading.Thread(target=self._loop, daemon=True).start()

    def _init_csv(self):
        with open(CSV_FILE, "w", newline="") as f:
            csv.writer(f).writerow([
                "timestamp","rpm","temperature_c",
                "vibration_mm_s","current_a","voltage_v","power_kw","status"
            ])

    def _build_ui(self):
        tk.Label(self.root, text="⚙  FACTORYGUARD — MOTOR SIMULATOR v4",
                 bg="#0f1117", fg="#00d4ff", font=("Consolas",14,"bold")).pack(pady=(16,2))
        tk.Label(self.root, text="3-Phase 400V | 7.5kW | 1450 RPM | Real Physics Model",
                 bg="#0f1117", fg="#555", font=("Consolas",9)).pack()
        tk.Frame(self.root, bg="#1e2230", height=2).pack(fill="x", pady=8)

        sf = tk.Frame(self.root, bg="#0f1117")
        sf.pack(fill="x", padx=30)

        # Load slider
        tk.Label(sf, text="MOTOR LOAD  (% of rated mechanical load)",
                 bg="#0f1117", fg="#aaa", font=("Consolas",10)).grid(row=0,column=0,sticky="w")
        self.load_var = tk.DoubleVar(value=70)
        tk.Scale(sf, from_=0, to=100, orient="horizontal", variable=self.load_var,
                 length=720, bg="#0f1117", fg="#00d4ff", troughcolor="#1e2230",
                 highlightthickness=0, font=("Consolas",9)).grid(row=1,column=0,sticky="ew")

        # RPM setpoint
        tk.Label(sf, text="RPM SETPOINT  (speed command to drive/VFD)",
                 bg="#0f1117", fg="#aaa", font=("Consolas",10)).grid(row=2,column=0,sticky="w",pady=(10,0))
        self.rpm_var = tk.DoubleVar(value=1450)
        tk.Scale(sf, from_=0, to=1500, orient="horizontal", variable=self.rpm_var,
                 length=720, bg="#0f1117", fg="#ff6b35", troughcolor="#1e2230",
                 highlightthickness=0, font=("Consolas",9)).grid(row=3,column=0,sticky="ew")

        # Voltage slider — full range to show fault effect clearly
        tk.Label(sf, text="SUPPLY VOLTAGE  (V) — move below 380V to trigger fault",
                 bg="#0f1117", fg="#aaa", font=("Consolas",10)).grid(row=4,column=0,sticky="w",pady=(10,0))
        self.volt_var = tk.DoubleVar(value=400)
        tk.Scale(sf, from_=280, to=440, orient="horizontal", variable=self.volt_var,
                 length=720, bg="#0f1117", fg="#00ff88", troughcolor="#1e2230",
                 highlightthickness=0, font=("Consolas",9)).grid(row=5,column=0,sticky="ew")

        tk.Frame(self.root, bg="#1e2230", height=2).pack(fill="x", pady=8)

        # Fault buttons
        tk.Label(self.root, text="FAULT INJECTION",
                 bg="#0f1117", fg="#ff6b35", font=("Consolas",11,"bold")).pack()
        ff = tk.Frame(self.root, bg="#0f1117")
        ff.pack(pady=6)
        for i,(lbl,var,col) in enumerate([
            ("🌡  Overtemperature", self.fault_overtemp,    "#ff4444"),
            ("🔩  Bearing Fault",   self.fault_bearing,     "#ffaa00"),
            ("⚡  Voltage Drop",    self.fault_voltage_drop,"#ff6b35"),
            ("⚠   Overcurrent",    self.fault_overcurrent,  "#cc44ff"),
        ]):
            tk.Checkbutton(ff, text=lbl, variable=var,
                           bg="#0f1117", fg=col, selectcolor="#1e2230",
                           activebackground="#0f1117", font=("Consolas",10),
                           padx=14).grid(row=0,column=i,padx=10)

        tk.Frame(self.root, bg="#1e2230", height=2).pack(fill="x", pady=8)

        # Live readings
        tk.Label(self.root, text="LIVE SENSOR READINGS",
                 bg="#0f1117", fg="#00ff88", font=("Consolas",11,"bold")).pack()
        rf = tk.Frame(self.root, bg="#0f1117")
        rf.pack(pady=8)
        self.lbl = {}
        for i,(label,key,color) in enumerate([
            ("RPM",        "rpm", "#00d4ff"),
            ("TEMP (°C)",  "tmp", "#ff6b35"),
            ("VIBRATION",  "vib", "#ffaa00"),
            ("CURRENT (A)","cur", "#cc44ff"),
            ("VOLTAGE (V)","vlt", "#00ff88"),
            ("POWER (kW)", "pow", "#ffffff"),
        ]):
            fr = tk.Frame(rf, bg="#1e2230", padx=18, pady=10)
            fr.grid(row=i//3, column=i%3, padx=8, pady=6, ipadx=10)
            tk.Label(fr, text=label, bg="#1e2230", fg="#555", font=("Consolas",9)).pack()
            l = tk.Label(fr, text="---", bg="#1e2230", fg=color,
                         font=("Consolas",18,"bold"), width=8)
            l.pack()
            self.lbl[key] = l

        tk.Frame(self.root, bg="#1e2230", height=2).pack(fill="x", pady=6)
        self.status_lbl = tk.Label(self.root, text="● NORMAL OPERATION",
                                   bg="#0f1117", fg="#00ff88", font=("Consolas",11,"bold"))
        self.status_lbl.pack()
        tk.Label(self.root, text=f"📄 {CSV_FILE}",
                 bg="#0f1117", fg="#333", font=("Consolas",8)).pack(pady=(2,8))

    def _compute(self):
        load    = self.load_var.get() / 100.0      # 0.0 – 1.0
        rpm_sp  = self.rpm_var.get()               # commanded RPM
        voltage = self.volt_var.get()

        # ── Fault modifier: voltage drop button forces -22%
        if self.fault_voltage_drop.get():
            voltage = voltage * 0.78 + random.uniform(-4, 4)

        # ── RPM: slip increases with load; bearing fault reduces by 7%
        slip = 0.05 * load
        rpm  = rpm_sp * (1.0 - slip)
        if self.fault_bearing.get():
            rpm *= 0.93
        rpm = max(0, rpm + random.uniform(-6, 6))

        # ── CURRENT: derived from power balance (real motor physics)
        # P = √3 × V × I × cosφ  →  I = P / (√3 × V × cosφ)
        # Shaft power scales with load fraction
        shaft_power = P_RATED * load * (rpm_sp / RPM_RATED) if rpm_sp > 0 else 0
        # Electrical input power accounts for efficiency (~91%)
        elec_power  = shaft_power / 0.91
        denom = (math.sqrt(3) * max(voltage, 1) * PF)
        current = elec_power / denom

        # Logical constraint: if voltage drops, current rises proportionally
        # This is the KEY fix — low voltage = high current (real motor behavior)
        voltage_ratio = V_RATED / max(voltage, 1)
        current = current * voltage_ratio  # overcurrent from voltage drop

        if self.fault_overcurrent.get():
            current *= 1.45
        current = max(0, current + random.uniform(-0.2, 0.2))

        # ── LOGICAL CONSTRAINT: cap impossible states
        # High RPM + very high current = driven load issue (not just load slider)
        if rpm > 1400 and current > 22:
            current = 22 + random.uniform(0, 1)  # physical limit of motor

        # ── TEMPERATURE: I²R losses are dominant
        # T = T_ambient + k × I² (joule heating model)
        k_thermal = (T_RATED - T_AMBIENT) / (I_RATED ** 2)
        temp = T_AMBIENT + k_thermal * (current ** 2)
        if self.fault_overtemp.get():
            temp += 35 + random.uniform(0, 8)
        if self.fault_bearing.get():
            temp += 12 + random.uniform(0, 4)
        temp = max(T_AMBIENT, temp + random.uniform(-0.4, 0.4))

        # ── VIBRATION: mechanical + load component
        vib = 0.5 + 1.8 * load
        if self.fault_bearing.get():
            vib += 8.5 + random.uniform(0, 2.5) + 1.8 * math.sin(time.time() * 3.2)
        # Low voltage can cause slight vibration increase (unbalanced magnetic pull)
        if voltage < 360:
            vib += (360 - voltage) / 60
        vib = max(0.1, vib + random.uniform(-0.08, 0.08))

        # ── POWER
        power = (math.sqrt(3) * voltage * current * PF) / 1000

        # ── STATUS LOGIC (priority order)
        status = "NORMAL"
        if   self.fault_overcurrent.get() or current > 20: status = "CRITICAL_OVERCURRENT"
        elif self.fault_overtemp.get()    or temp > 102:   status = "CRITICAL_OVERTEMPERATURE"
        elif self.fault_bearing.get()     or vib > 7.1:    status = "WARNING_BEARING_FAULT"
        elif voltage < 340:                                 status = "CRITICAL_UNDERVOLTAGE"
        elif voltage < 370:                                 status = "WARNING_LOW_VOLTAGE"
        elif temp > 82:                                     status = "WARNING_HIGH_TEMP"
        elif current > 17:                                  status = "WARNING_HIGH_CURRENT"
        elif rpm_sp < 50:                                   status = "IDLE"

        return dict(
            rpm=round(rpm, 1), tmp=round(temp, 1), vib=round(vib, 3),
            cur=round(current, 2), vlt=round(voltage, 1),
            pow=round(power, 3), status=status
        )

    def _update_ui(self, d):
        for key in ["rpm","tmp","vib","cur","vlt","pow"]:
            self.lbl[key].config(text=str(d[key]))

        cmap = {
            "NORMAL":                   ("#00ff88", "● NORMAL OPERATION"),
            "IDLE":                     ("#888888", "● MOTOR IDLE"),
            "WARNING_LOW_VOLTAGE":      ("#ffaa00", "⚠  WARNING — LOW VOLTAGE"),
            "CRITICAL_UNDERVOLTAGE":    ("#ff4444", "🔴 CRITICAL — UNDERVOLTAGE"),
            "WARNING_BEARING_FAULT":    ("#ffaa00", "⚠  WARNING — BEARING FAULT"),
            "WARNING_HIGH_TEMP":        ("#ff6b35", "⚠  WARNING — HIGH TEMPERATURE"),
            "WARNING_HIGH_CURRENT":     ("#ffaa00", "⚠  WARNING — HIGH CURRENT"),
            "CRITICAL_OVERTEMPERATURE": ("#ff4444", "🔴 CRITICAL — OVERTEMPERATURE"),
            "CRITICAL_OVERCURRENT":     ("#cc44ff", "🔴 CRITICAL — OVERCURRENT"),
        }
        col, txt = cmap.get(d["status"], ("#00ff88","● NORMAL"))
        self.status_lbl.config(fg=col, text=txt)

    def _write_csv(self, d):
        with open(CSV_FILE, "a", newline="") as f:
            csv.writer(f).writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                d["rpm"], d["tmp"], d["vib"],
                d["cur"], d["vlt"], d["pow"], d["status"]
            ])

    def _loop(self):
        while self.running:
            d = self._compute()
            self._write_csv(d)
            self.root.after(0, self._update_ui, d)
            time.sleep(1)

if __name__ == "__main__":
    root = tk.Tk()
    MotorSimulator(root)
    root.mainloop()
