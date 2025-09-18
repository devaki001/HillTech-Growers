from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, abort
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote
from dotenv import load_dotenv
import pandas as pd
import requests
import os
import random
import schedule
import threading
import time
import sqlite3

"""
Smart Agriculture (Merged)
-------------------------
- Merges both of your Flask codes into a single web-only app.
- **All SMS/Twilio functionality removed** (no imports, no env, no calls, no DB columns).
- Keeps: auth (register/login), multilingual UI (Babel), dashboards, crop water calculator,
  crop-detail page (with yield/profit + water calc), sensor simulation, alert logic,
  REST APIs, daily scheduler, and SQLite persistence.
- Uses .env for config like API keys, host/port, etc.

Templates expected in ./templates:
  login.html, register.html, dashboard.html, dashboard2.html, alerts.html, water.html, crop_detail.html
Static assets (CSS/JS) can go in ./static as usual.
"""

# ---------- ENV ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

def env_bool(name, default="false"):
    return (os.getenv(name, default) or "").strip().lower() in ("1", "true", "yes", "y")

# Flask / Server
SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "smart_agriculture_2025_sikkim")
DEBUG      = env_bool("FLASK_DEBUG", "true")
HOST       = os.getenv("FLASK_HOST", "0.0.0.0")
PORT       = int(os.getenv("FLASK_PORT", "5000"))
# ESP32
# config.py (or near the top of your app)
ESP32_ENDPOINT   = "http://10.64.119.95/data"   # <-- absolute, not a relative path
ESP32_TIMEOUT_S  = 2.5
TANK_H1_CM = 9.5
TANK_R_CM  = 4.85
PI_CONST   = 22/7


# Weather config (env preferred; falls back to prior values)
OWM_API_KEY = os.getenv("OWM_API_KEY", "a8833213c3647ad53e97b2d30ff7c4ef")
CITY        = os.getenv("OWM_CITY", "Jorethang,IN")

# Schedules (HH:MM, 24h)
DAILY_WEATHER_ALERT_TIME = os.getenv("DAILY_WEATHER_ALERT_TIME", "07:00")
TANK_ALERT_TIME_MORNING  = os.getenv("TANK_ALERT_TIME_MORNING", "06:00")
TANK_ALERT_TIME_EVENING  = os.getenv("TANK_ALERT_TIME_EVENING", "18:00")

SQLITE_PATH = os.getenv("SQLITE_PATH", "smart_agri.db")

# ---------- APP ----------
app = Flask(__name__)
app.secret_key = SECRET_KEY

# Simple context vars
@app.context_processor
def inject_common_vars():
    return dict(
        current_year=datetime.now().year,
        _=_,
        current_lang='en',
    )

# No-op translation helper to keep existing calls working
def _(text, **kwargs):
    try:
        return text % kwargs if kwargs else text
    except Exception:
        return text

# ---------- GLOBALS / DATA ----------
FARMER_ALERTS: list[dict] = []
CROPS_DF = pd.read_csv(os.path.join(BASE_DIR, "cropsnew.csv"), encoding="cp1252")
CROPS_DF.columns = (CROPS_DF.columns.str.strip().str.replace("\u00a0", " ", regex=False))
for col in ["Crop", "Soil Type", "Soil Moisture"]:
    if col in CROPS_DF.columns:
        CROPS_DF[col] = CROPS_DF[col].astype(str).str.strip()

CURRENT_TANK_LEVEL = 45  # simulated starting level

# ---------- DB ----------
def init_db():
    conn = sqlite3.connect(SQLITE_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS users (
            userid TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            password TEXT NOT NULL,
            phone TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS user_crops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            userid TEXT NOT NULL,
            crop_name TEXT NOT NULL,
            soil_type TEXT NOT NULL,
            water_requirement REAL NOT NULL,
            start_date TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (userid) REFERENCES users (userid)
        )"""
    )
    # NOTE: no sms_sent column (SMS removed)
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS alert_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            userid TEXT,
            alert_type TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            severity TEXT NOT NULL,
            category TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (userid) REFERENCES users (userid)
        )"""
    )
    conn.commit()
    conn.close()


def save_alert_to_db(alert_data: dict, userid: str | None = None):
    conn = sqlite3.connect(SQLITE_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO alert_history 
           (userid, alert_type, title, message, severity, category, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            userid,
            alert_data.get("type", "unknown"),
            alert_data["title"],
            alert_data["message"],
            alert_data["severity"],
            alert_data["category"],
            alert_data["timestamp"],
        ),
    )
    conn.commit()
    conn.close()


init_db()

# ---------- HELPERS ----------

def now_utc_iso():
    return datetime.now(timezone.utc).isoformat()


def get_weather_data():
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={CITY}&appid={OWM_API_KEY}&units=metric"
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        w = resp.json()
        return {
            "temperature": round(w["main"]["temp"]),
            "humidity": round(w["main"]["humidity"]),
            "rainfall": round(w.get("rain", {}).get("1h", 0) or 0, 1),
            "wind_speed": round(w["wind"]["speed"]),
        }
    except Exception as e:
        print("Weather API error:", e)
        return {"temperature": 22, "humidity": 70, "rainfall": 0, "wind_speed": 5}


def get_weather_forecast():
    try:
        url = f"http://api.openweathermap.org/data/2.5/forecast?q={CITY}&appid={OWM_API_KEY}&units=metric"
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        forecast = resp.json()
        today = datetime.now().date()
        today_forecast = []
        for item in forecast["list"]:
            dt = datetime.fromtimestamp(item["dt"])
            if dt.date() == today:
                today_forecast.append(
                    {
                        "time": dt.strftime("%H:%M"),
                        "rain": item.get("rain", {}).get("3h", 0) or 0,
                        "description": item["weather"][0]["description"],
                        "humidity": item["main"]["humidity"],
                    }
                )
        return today_forecast
    except Exception as e:
        print("Weather forecast API error:", e)
        return []

def get_soil_data():
    """
    Read live values from ESP32 /data.
    Returns dict or None if sensor unreachable.
    """
    try:
        r = requests.get(ESP32_ENDPOINT, timeout=ESP32_TIMEOUT_S)
        r.raise_for_status()
        j = r.json()
        return {
            "moisture": float(j.get("soil_pct", 0) or 0),
            "temperature": float(j.get("temp_c", 0) or 0),
            "humidity": float(j.get("humidity_pct", 0) or 0),
        }
    except Exception as e:
        print("ESP32 read failed in get_soil_data():", e)
        return None   # <-- important

def get_irrigation_data():
    return {"schedule": "Active", "next_watering": "14:30", "duration": 25, "pressure": 2.8}

# Tank geometry (set real values!)
TANK_RADIUS_CM   = float(os.getenv("TANK_RADIUS_CM", "4.85"))   # cylinder radius
TANK_HEIGHT_CM   = float(os.getenv("TANK_HEIGHT_CM", "9.5"))    # internal height

def get_tank_snapshot():
    """
    Read ESP32 ultrasonic and compute the same values as the tank card.
    Returns dict:
      { ultrasonic_cm, height_cm, volume_cm3, capacity_cm3, percent }
    Raises on failure.
    """
    r = requests.get(ESP32_ENDPOINT, timeout=ESP32_TIMEOUT_S)
    r.raise_for_status()
    j = r.json()
    u = float(j.get("ultrasonic_cm"))

    H1 = TANK_H1_CM
    R  = TANK_R_CM
    PI = PI_CONST

    H = max(0.0, min(H1, H1 - u))        # water height (cm)
    base_area = PI * R * R               # cm²
    vol_cm3   = base_area * H            # cm³
    cap_cm3   = base_area * H1           # cm³
    percent   = (H / H1) * 100.0

    return {
        "ultrasonic_cm": round(u, 2),
        "height_cm": round(H, 2),
        "volume_cm3": int(round(vol_cm3)),
        "capacity_cm3": int(round(cap_cm3)),
        "percent": int(round(percent)),   # match gauge rounding
    }

def get_tank_level():
    global CURRENT_TANK_LEVEL
    change = random.uniform(-2, 2)
    CURRENT_TANK_LEVEL = max(0, min(100, CURRENT_TANK_LEVEL + change))
    sensor = max(0, min(100, CURRENT_TANK_LEVEL + random.uniform(-1, 1)))
    return round(sensor, 1)


def simulate_sensor_scenarios():
    global CURRENT_TANK_LEVEL
    scenario = random.choice(["normal", "irrigation_use", "refill", "leak", "stable"])
    if scenario == "irrigation_use":
        CURRENT_TANK_LEVEL -= random.uniform(0.5, 2.0)
    elif scenario == "refill":
        CURRENT_TANK_LEVEL += random.uniform(1.0, 3.0)
    elif scenario == "leak":
        CURRENT_TANK_LEVEL -= random.uniform(0.1, 0.5)
    elif scenario == "stable":
        CURRENT_TANK_LEVEL += random.uniform(-0.2, 0.2)
    CURRENT_TANK_LEVEL = max(0, min(100, CURRENT_TANK_LEVEL))


# ---------- ALERT LOGIC ----------

def add_alert(alert: dict, save_for_user: str | None = None):
    if not alert:
        return
    FARMER_ALERTS.append(alert)
    save_alert_to_db(alert, userid=save_for_user)

def check_rain_alert():
    forecast = get_weather_forecast()
    if not forecast:
        return None

    total_rain = sum(item["rain"] for item in forecast)
    max_rain = max((item["rain"] for item in forecast), default=0)

    current_weather = get_weather_data()
    soil = get_soil_data()
    soil_moisture = (soil or {}).get("moisture")  # may be None

    t = current_weather.get("temperature", 22)
    h = current_weather.get("humidity", 70)
    r = current_weather.get("rainfall", 0)
    w = current_weather.get("wind_speed", 5)
    ts = now_utc_iso()

    if total_rain > 5.0 or max_rain > 2.0:
        return {
            "type": "rain_alert",
            "title": _("🌧 Heavy Rain Alert"),
            "message": _(
                "Warning! Heavy rainfall expected today. Current: %(t)s°C, %(h)s%%, %(r)smm, %(w)s km/h.",
                t=t, h=h, r=r, w=w,
            ),
            "severity": "high",
            "category": "weather",
            "timestamp": ts,
            "recommendation": _("Cover young plants; delay irrigation."),
            "icon": "🌧",
        }
    elif total_rain > 1.0 or max_rain > 0.5:
        return {
            "type": "rain_alert",
            "title": _("☔ Rain Expected Today"),
            "message": _(
                "Rain expected. Conditions: %(t)s°C, %(h)s%%, %(r)smm, %(w)s km/h.",
                t=t, h=h, r=r, w=w,
            ),
            "severity": "medium",
            "category": "weather",
            "timestamp": ts,
            "recommendation": _("Skip irrigation today; recheck tomorrow."),
            "icon": "☔",
        }
    elif total_rain > 0.1:
        return {
            "type": "rain_alert",
            "title": _("🌫 Uncertain Weather"),
            "message": _("Light rain chance.") if soil_moisture is None
                       else _("Light rain chance. Soil %(m)s%%.", m=int(soil_moisture)),
            "severity": "low",
            "category": "weather",
            "timestamp": ts,
            "recommendation": _("Check soil before irrigating."),
            "icon": "🌫",
        }
    else:
        # Only make irrigation-needed call if we DO have soil data
        if soil_moisture is not None and soil_moisture < 40:
            return {
                "type": "irrigation_alert",
                "title": _("🌤 No Rain, Irrigation Needed"),
                "message": _("No rain expected. Soil %(m)s%%.", m=int(soil_moisture)),
                "severity": "medium",
                "category": "irrigation",
                "timestamp": ts,
                "recommendation": _("Follow normal irrigation schedule."),
                "icon": "🌤",
            }
        else:
            return {
                "type": "weather_update",
                "title": _("🌤 Good Weather Day"),
                "message": _("Clear weather.") if soil_moisture is None
                           else _("Clear weather; soil moisture adequate."),
                "severity": "low",
                "category": "weather",
                "timestamp": ts,
                "recommendation": _("Continue regular activities."),
                "icon": "🌤",
            }

# at top of your module (if not already present)
import os, requests

ESP32_ENDPOINT    = os.getenv("ESP32_ENDPOINT", "http://10.64.119.95/data")
ESP32_TIMEOUT_S   = float(os.getenv("ESP32_TIMEOUT_S", "3"))

def check_water_tank_alert():
    """
    Build alert from LIVE ultrasonic reading using the same geometry/rounding
    as the tank card.
    """
    try:
        snap = get_tank_snapshot()
    except Exception as e:
        print("check_water_tank_alert(): ESP32 read failed:", e)
        return None

    p = snap["percent"]
    a_cm3 = snap["volume_cm3"]
    c_cm3 = snap["capacity_cm3"]
    ts = now_utc_iso()

    # If you prefer liters in alerts, convert here (uncomment these 2 lines
    # and switch the msg line below).
    # a_l = round(a_cm3 / 1000.0, 1)
    # c_l = round(c_cm3 / 1000.0, 1)

    # Message in cm³ to match your tank card labels:
    msg = _("Water tank is at %(p)s%% (%(a)s cm³ / %(c)s cm³).", p=p, a=a_cm3, c=c_cm3)
    # Or in liters if you want:
    # msg = _("Water tank is at %(p)s%% (%(a).1fL / %(c).1fL).", p=p, a=a_l, c=c_l)

    base = {
        "type": "water_alert",
        "category": "water",
        "timestamp": ts,
        "message": msg,
        "icon": "💧",
    }

    if p >= 90:
        return {**base,
                "title": _("💧 Water Tank Full"),
                "severity": "high",
                "recommendation": _("Turn off supply; check for leaks.")}

    if p <= 20:
        return {**base,
                "title": _("⚠️ Water Tank Low"),
                "severity": "high",
                "recommendation": _("Refill immediately.")}

    if p <= 40:
        return {**base,
                "title": _("🔔 Water Tank Getting Low"),
                "severity": "medium",
                "recommendation": _("Plan a refill soon.")}

    # No threshold: return a low-priority status update that still uses live values
    return {**base,
            "title": _("💧 Water Tank Status Update"),
            "severity": "low",
            "recommendation": _("No immediate action required.")}


def check_weather_irrigation_recommendation():
    try:
        weather = get_weather_data()
        soil = get_soil_data()
        forecast = get_weather_forecast()
        total_rain = sum((i["rain"] for i in forecast), 0) if forecast else 0
        max_rain = max((i["rain"] for i in forecast), default=0)
        t, h = weather["temperature"], weather["humidity"]
        curr_rain, wind = weather["rainfall"], weather["wind_speed"]
        sm = (soil or {}).get("moisture")
        st = (soil or {}).get("temperature")
        sh = (soil or {}).get("humidity")
        ts = now_utc_iso()

        # Heavy/medium rain branches don't need soil
        if total_rain > 5.0 or max_rain > 2.0 or curr_rain > 1.0:
            return {
                "type": "irrigation_recommendation",
                "title": _("🌧 Heavy Rain Alert - No Irrigation"),
                "message": _("Heavy rain expected. Wx: %(t)s°C, %(h)s%%, %(w)s km/h.", t=t, h=h, w=wind)
                           if sm is None else
                           _("Heavy rain expected. Wx: %(t)s°C, %(h)s%%, %(w)s km/h. "
                             "Soil: %(sm)s%%, %(st)s°C, %(sh)s%%.",
                             t=t, h=h, w=wind, sm=int(sm), st=int(st), sh=int(sh)),
                "severity": "high",
                "category": "irrigation",
                "timestamp": ts,
                "recommendation": _("Skip irrigation today."),
                "icon": "🌧",
            }
        elif total_rain > 1.0 or max_rain > 0.5 or curr_rain > 0.1:
            return {
                "type": "irrigation_recommendation",
                "title": _("🌦️ Medium Rain - Limited Irrigation"),
                "message": _("May rain today. Reduce irrigation by ~50%%. Wx: %(t)s°C, %(h)s%%, %(w)s km/h.",
                             t=t, h=h, w=wind),
                "severity": "medium",
                "category": "irrigation",
                "timestamp": ts,
                "recommendation": _("Use minimal irrigation and monitor."),
                "icon": "🌦️",
            }

        # For the "perfect" or "normal" cases, only use soil if present
        if sm is None:
            return {
                "type": "irrigation_recommendation",
                "title": _("🌤️ Normal Weather - Sensor Offline"),
                "message": _("Normal conditions. Soil sensor data unavailable. Wx: %(t)s°C, %(h)s%%, %(w)s km/h.",
                             t=t, h=h, w=wind),
                "severity": "low",
                "category": "irrigation",
                "timestamp": ts,
                "recommendation": _("Check sensor and follow your usual schedule."),
                "icon": "🌤️",
            }

        if total_rain == 0 and curr_rain == 0 and t > 25 and h < 60:
            return {
                "type": "irrigation_recommendation",
                "title": _("☀️ Perfect Irrigation Day"),
                "message": _("Sunny and dry. Wx: %(t)s°C, %(h)s%%, %(w)s km/h.", t=t, h=h, w=wind),
                "severity": "low",
                "category": "irrigation",
                "timestamp": ts,
                "recommendation": _("Proceed with normal schedule."),
                "icon": "☀️",
            }
        else:
            return {
                "type": "irrigation_recommendation",
                "title": _("🌤️ Normal Weather - Regular Irrigation"),
                "message": _("Normal conditions. Wx: %(t)s°C, %(h)s%%, %(w)s km/h.", t=t, h=h, w=wind),
                "severity": "low",
                "category": "irrigation",
                "timestamp": ts,
                "recommendation": _("Follow your regular schedule."),
                "icon": "🌤️",
            }
    except Exception as e:
        print("Irrigation recommendation error:", e)
        return {
            "type": "irrigation_recommendation",
            "title": _("⚠️ Weather Data Unavailable"),
            "message": _("Unable to fetch weather data."),
            "severity": "medium",
            "category": "irrigation",
            "timestamp": now_utc_iso(),
            "recommendation": _("Check conditions manually."),
            "icon": "⚠️",
        }

# ---------- SCHEDULER ----------

def generate_daily_weather_alert():
    ra = check_rain_alert()
    if ra:
        add_alert(ra)
    else:
        w = get_weather_data()
        upd = {
            "type": "weather_update",
            "title": _("Daily Weather Update"),
            "message": _(
                "Today's weather: %(t)s°C, %(h)s%% humidity. No significant rain expected.",
                t=w["temperature"], h=w["humidity"],
            ),
            "severity": "low",
            "category": "weather",
            "timestamp": now_utc_iso(),
            "recommendation": _("Normal irrigation schedule can be followed."),
        }
        add_alert(upd)

    wa = check_water_tank_alert()
    if wa:
        add_alert(wa)

def generate_water_tank_alert():
    wa = check_water_tank_alert()
    if wa:
        add_alert(wa)
        return
    # If check returned None (ESP32 error), fall back with a harmless notice
    upd = {
        "type": "water_status",
        "title": _("💧 Water Tank Status"),
        "message": _("Sensor offline. Unable to read tank just now."),
        "severity": "low",
        "category": "water",
        "timestamp": now_utc_iso(),
        "recommendation": _("Check the device connection."),
        "icon": "💧",
    }
    add_alert(upd)

def schedule_daily_alerts():
    schedule.every().day.at(DAILY_WEATHER_ALERT_TIME).do(generate_daily_weather_alert)
    schedule.every().day.at(TANK_ALERT_TIME_MORNING).do(generate_water_tank_alert)
    schedule.every().day.at(TANK_ALERT_TIME_EVENING).do(generate_water_tank_alert)
    while True:
        schedule.run_pending()
        time.sleep(60)


def start_alert_scheduler():
    t = threading.Thread(target=schedule_daily_alerts, daemon=True)
    t.start()
    print("Alert scheduler started.")


# ---------- ROUTES ----------

@app.route("/")
def home():
    if "username" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


# --- Auth ---
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        userid = request.form["userid"].strip()
        name = request.form["name"].strip()
        password = request.form["password"].strip()
        phone = request.form["phone"].strip()

        if not userid.isdigit():
            flash(_("UserID must contain only numbers."), "error")
            return redirect(url_for("register"))
        if not phone.isdigit() or len(phone) != 10:
            flash(_("Phone number must be exactly 10 digits."), "error")
            return redirect(url_for("register"))
        if not name or not password:
            flash(_("Name and Password cannot be empty."), "error")
            return redirect(url_for("register"))

        conn = sqlite3.connect(SQLITE_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO users (userid, name, password, phone) VALUES (?, ?, ?, ?)",
                (userid, name, password, phone),
            )
            conn.commit()
            flash(_("Registration successful! Please login."), "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash(_("UserID already exists. Try another one."), "error")
        finally:
            conn.close()
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        userid = request.form["userid"]
        password = request.form["password"]

        conn = sqlite3.connect(SQLITE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE userid=? AND password=?", (userid, password))
        user = cursor.fetchone()
        conn.close()

        if user:
            session["userid"] = user[0]
            session["username"] = user[1]
            session["password"] = user[2]
            session["phone"] = user[3]
            flash(_("Login successful!"), "success")
            return redirect(url_for("dashboard"))
        else:
            flash(_("Invalid UserID or Password"), "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("username", None)
    flash(_("You have been logged out."), "success")
    return redirect(url_for("login"))

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if "username" not in session:
        flash(_("Please login first."), "error")
        return redirect(url_for("login"))

    soil = get_soil_data()             # may be None
    weather = get_weather_data()
    selected_soil = None

    if request.method == "POST":
        selected_soil = (request.form.get("soil_type") or "").strip() or None

    # ---- If no soil data: don't recommend anything ----
    if soil is None:
        recommended = []
        moisture_category = "Unknown"
        session['recommended_crops'] = []
        data = {
            'soil': None,
            'weather': weather,
            'irrigation': get_irrigation_data(),
            'tank_level': get_tank_level(),
            'current_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'crops': recommended,
            'soil_category': moisture_category
        }
        flash(_("No live soil sensor data. Connect ESP32 to see crop recommendations."), "warning")
        return render_template('dashboard.html', username=session["username"], data=data, selected_soil=selected_soil)

    # ========== Robust recommendation logic (self-contained) ==========
    import re
    import numpy as np
    import pandas as pd

    def _num(x):
        """Coerce to float. Supports simple ranges like '20-30' by using the midpoint."""
        if x is None:
            return np.nan
        s = str(x).strip()
        if not s:
            return np.nan
        m = re.match(r'^\s*(-?\d+(?:\.\d+)?)\s*[-–]\s*(-?\d+(?:\.\d+)?)\s*$', s)
        if m:
            a = float(m.group(1)); b = float(m.group(2))
            return (a + b) / 2.0
        try:
            return float(s)
        except Exception:
            return np.nan

    def _norm(s):
        return (str(s) if s is not None else "").strip().lower()

    def _tokenize_categories(cell):
        """Split 'Low / Medium' or 'low,medium' or 'flooded' into ['low','medium'] etc."""
        parts = re.split(r'[/,;|\-]+', str(cell) if cell is not None else "")
        return [_norm(p) for p in parts if _norm(p)]

    def _moisture_bucket_from_pct(pct):
        """Map live % to one of: low, medium, high, flooded, unknown."""
        try:
            v = float(pct)
        except Exception:
            return "unknown"
        if v >= 90:
            return "flooded"
        elif v > 70:
            return "high"
        elif v >= 40:
            return "medium"
        else:
            return "low"

    # Compute live moisture category for display
    live_bucket = _moisture_bucket_from_pct(soil.get("moisture"))
    moisture_category = "Unknown" if live_bucket == "unknown" else live_bucket.capitalize()

    try:
        df = CROPS_DF.copy()

        # Columns in your CSV (from the sample you shared)
        # Sl.no, Crop, Minimum Practical Area (acre), Total Water ( mm ), ..., Soil Type, Soil Moisture,
        # Min Temp, Max temp, ..., Min Humidity , Max Humidity , ...

        # Humidity columns sometimes have trailing spaces; handle both
        hum_min_cols = ["Min Humidity", "Min Humidity "]
        hum_max_cols = ["Max Humidity", "Max Humidity "]

        # Pick the first existing humidity column variant
        col_min_hum = next((c for c in hum_min_cols if c in df.columns), None)
        col_max_hum = next((c for c in hum_max_cols if c in df.columns), None)

        # Safely coerce numeric columns (also parses "20-30")
        for col in ["Min Temp", "Max temp", col_min_hum, col_max_hum, "Total Water ( mm )"]:
            if col and col in df.columns:
                df[col] = df[col].map(_num)

        # Start with allow-all mask, then constrain only when that column exists
        mask = pd.Series(True, index=df.index)

        # Temperature range
        if "Min Temp" in df.columns:
            mask &= (df["Min Temp"] <= _num(soil.get("temperature")))
        if "Max temp" in df.columns:
            mask &= (df["Max temp"] >= _num(soil.get("temperature")))

        # Humidity range
        live_h = _num(soil.get("humidity"))
        if col_min_hum:
            mask &= (df[col_min_hum] <= live_h)
        if col_max_hum:
            mask &= (df[col_max_hum] >= live_h)

        # Soil Moisture category (text) — only apply if the column exists and we know the bucket
        if "Soil Moisture" in df.columns and live_bucket != "unknown":
            sm_tokens = df["Soil Moisture"].apply(_tokenize_categories)
            want = live_bucket  # 'low'|'medium'|'high'|'flooded'
            mask &= sm_tokens.apply(lambda toks: any(t == want for t in toks))

        # Soil Type filter from the UI dropdown (optional)
        if selected_soil and "Soil Type" in df.columns:
            want_st = _norm(selected_soil)
            mask &= (df["Soil Type"].astype(str).str.strip().str.lower() == want_st)

        # Keep only rows with a crop name
        if "Crop" in df.columns:
            mask &= df["Crop"].notna()

        recommended = df.loc[mask].to_dict(orient="records")
    except Exception as e:
        print("Crop filter error:", e)
        recommended = []

    # ================================================================

    session['recommended_crops'] = [c.get("Crop") for c in recommended if c.get("Crop")]

    data = {
        'soil': soil,
        'weather': weather,
        'irrigation': get_irrigation_data(),
        'tank_level': get_tank_level(),
        'current_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'crops': recommended,
        'soil_category': moisture_category
    }
    return render_template('dashboard.html', username=session["username"], data=data, selected_soil=selected_soil)

@app.route("/dashboard2")
def dashboard2():
    username = session.get("username", "Guest")
    conn = sqlite3.connect(SQLITE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT userid, name, phone FROM users")
    users = cursor.fetchall()
    conn.close()
    return render_template("dashboard2.html", username=username, users=users)


@app.route('/water_calc', methods=['GET', 'POST'])
def water_calc():
    crop_options = session.get('recommended_crops', sorted(CROPS_DF["Crop"].dropna().unique().tolist()))
    selected_crop, result, water_mm = None, None, None
    if request.method == 'POST':
        selected_crop = request.form['crop']
        acres = float(request.form['acres'])
        row = CROPS_DF.loc[CROPS_DF["Crop"] == selected_crop]
        if not row.empty:
            water_mm = float(row.iloc[0]["Total Water ( mm )"])
            result = acres * 4046.86 * water_mm  # L = mm * m² ; 1 acre = 4046.86 m²
    return render_template("water.html", crop_options=crop_options, selected_crop=selected_crop, water_mm=water_mm, result=result)


@app.route('/alerts')
def alerts():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('alerts.html', alerts=FARMER_ALERTS)


# --- Crop detail page (merged from first app) ---
@app.route('/crop/<path:crop_name>', methods=['GET', 'POST'])
def crop_detail(crop_name):
    name = unquote(crop_name).strip()
    row = CROPS_DF.loc[CROPS_DF['Crop'].str.strip().str.casefold() == name.casefold()]
    if row.empty:
        abort(404)
    crop = row.iloc[0].to_dict()

    water_mm = float(crop.get('Total Water ( mm )', 0) or 0)

    # Yield (kg/acre)
    yield_kg_per_acre = None
    for k in ['Yield(Kg)', 'Yield (Kg)', 'Yield', 'Yield_per_acre']:
        if k in crop:
            try:
                yield_kg_per_acre = float(crop.get(k) or 0)
                break
            except Exception:
                pass
    if yield_kg_per_acre is None:
        yield_kg_per_acre = 0.0

    # Price (₹/kg)
    price = None
    for k in ['Price', 'Prize(Summer)', 'Prize', 'Price (₹/kg)']:
        if k in crop:
            try:
                price = float(crop.get(k) or 0)
                break
            except Exception:
                pass
    if price is None:
        price = 0.0

    which = request.form.get("which")  # "profit" or None
    acres = request.form.get("acres", type=float)
    total_litres = None
    water_mm_display = None

    acres_profit = request.form.get("acres_profit", type=float)
    other_expenses = request.form.get("other_expenses", type=float)
    revenue = profit = None

    if which == "profit":
        if acres_profit and acres_profit > 0:
            other_expenses = other_expenses or 0.0
            revenue = acres_profit * yield_kg_per_acre * price
            profit = revenue - other_expenses
        acres = None
        total_litres = None
        water_mm_display = None
    else:
        if acres is not None:
            if acres <= 0:
                total_litres = 0
                water_mm_display = 0
            else:
                total_litres = acres * 4046.86 * water_mm  # 1 mm = 1 L/m² ; 1 acre = 4046.86 m²
                water_mm_display = water_mm

    return render_template(
        'crop_detail.html',
        crop=crop,
        acres=acres,
        water_mm=water_mm,
        water_mm_display=water_mm_display,
        total_litres=total_litres,
        price=price,
        yield_kg_per_acre=yield_kg_per_acre,
        acres_profit=acres_profit,
        other_expenses=other_expenses,
        revenue=revenue,
        profit=profit
    )


# --- APIs ---
@app.route('/api/esp32/data')
def esp32_data():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        r = requests.get(ESP32_ENDPOINT, timeout=ESP32_TIMEOUT_S)
        r.raise_for_status()
        d = r.json()
        # Normalize to your dashboard's IDs/fields
        return jsonify({
            "soil_raw": d.get("soil_raw"),
            "soil_pct": d.get("soil_pct"),
            "ultrasonic_cm": d.get("ultrasonic_cm"),
            "temp_c": d.get("temp_c"),
            "humidity_pct": d.get("humidity_pct"),
            "pump_on": d.get("pump_on"),
            "auto_mode": d.get("auto_mode"),
            "soil_threshold_raw": d.get("soil_threshold_raw"),
            "ip": d.get("ip"),
            "uptime_s": d.get("uptime_s"),
            "wifi_ssid": d.get("wifi_ssid"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 502

@app.route('/api/run_alerts', methods=['POST'])
def api_run_alerts():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    created = []
    ra = check_rain_alert()
    if ra:
        add_alert(ra)
        created.append(ra)
    wa = check_water_tank_alert()
    if wa:
        add_alert(wa)
        created.append(wa)
    ir = check_weather_irrigation_recommendation()
    if ir:
        add_alert(ir)
        created.append(ir)
    return jsonify({'status': 'ok', 'created': created})


@app.route('/api/weather_alert', methods=['POST'])
def manual_weather_alert():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    alert = check_rain_alert()
    if alert:
        add_alert(alert)
        return jsonify({'status': 'success', 'alert': alert})
    return jsonify({'status': 'no_alert', 'message': 'No rain alert needed'})

@app.route('/api/water_tank_alert', methods=['POST'])
def manual_water_tank_alert():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    alert = check_water_tank_alert()
    if alert:
        add_alert(alert)
        return jsonify({'status': 'success', 'alert': alert})

    # No threshold; still return a live status payload for the UI
    try:
        snap = get_tank_snapshot()
        return jsonify({
            'status': 'no_alert',
            'message': _('Water tank is at %(p)s%% (%(a)s cm³ / %(c)s cm³).',
                         p=snap['percent'], a=snap['volume_cm3'], c=snap['capacity_cm3']),
            'tank_percent': snap['percent'],
            'water_height_cm': snap['height_cm'],
            'volume_cm3': snap['volume_cm3'],
            'capacity_cm3': snap['capacity_cm3']
        })
    except Exception:
        return jsonify({
            'status': 'error',
            'message': 'Sensor offline. Unable to read tank.'
        }), 502

@app.route('/api/weather_irrigation_recommendation', methods=['POST'])
def manual_weather_irrigation_recommendation():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    alert = check_weather_irrigation_recommendation()
    if alert:
        add_alert(alert)
        return jsonify({'status': 'success', 'alert': alert})
    return jsonify({'status': 'no_alert', 'message': 'No specific irrigation recommendation needed'})


@app.route('/api/add_crop_to_irrigation', methods=['POST'])
def add_crop_to_irrigation():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json or {}
    crop_name = (data.get('crop_name') or '').strip()
    soil_type = (data.get('soil_type') or '').strip()
    start_date = (data.get('start_date') or '').strip()

    wr_raw = data.get('water_requirement', 0)
    try:
        water_requirement = float(wr_raw or 0)
    except Exception:
        water_requirement = 0.0

    if not crop_name or not soil_type or not start_date:
        return jsonify({'error': 'Missing required fields'}), 400

    conn = sqlite3.connect(SQLITE_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO user_crops (userid, crop_name, soil_type, water_requirement, start_date, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session['userid'], crop_name, soil_type, water_requirement, start_date, 'active')
        )
        conn.commit()
        crop_id = cursor.lastrowid
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': f'Database error: {str(e)}'}), 500
    finally:
        conn.close()

    irrigation_alert = {
        'type': 'irrigation_alert',
        'title': _('🌱 Growing %(crop)s', crop=crop_name),
        'message': _('You are now growing %(crop)s in %(soil)s soil. Water requirement: %(wr)s mm. Started on %(d)s.',
                     crop=crop_name, soil=soil_type, wr=water_requirement, d=start_date),
        'severity': 'medium',
        'category': 'irrigation',
        'timestamp': now_utc_iso(),
        'recommendation': _('Monitor soil moisture regularly. Water requirement: %(wr)s mm per cycle.', wr=water_requirement),
        'icon': '🌱',
        'crop_name': crop_name,
        'soil_type': soil_type,
        'water_requirement': water_requirement,
        'start_date': start_date,
        'crop_id': crop_id
    }
    add_alert(irrigation_alert, save_for_user=session['userid'])
    return jsonify({'status': 'success', 'message': _('%(crop)s added to irrigation alerts', crop=crop_name), 'alert': irrigation_alert})


@app.route('/api/alerts')
def get_alerts():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    return jsonify({'alerts': FARMER_ALERTS})


@app.route('/api/user_crops')
def get_user_crops():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = sqlite3.connect(SQLITE_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """SELECT id, crop_name, soil_type, water_requirement, start_date, status, created_at 
           FROM user_crops WHERE userid = ? ORDER BY created_at DESC""",
        (session['userid'],)
    )
    crops = cursor.fetchall()
    conn.close()
    crop_list = [{
        'id': c[0], 'crop_name': c[1], 'soil_type': c[2], 'water_requirement': c[3],
        'start_date': c[4], 'status': c[5], 'created_at': c[6]
    } for c in crops]
    return jsonify({'crops': crop_list})


@app.route('/api/user_profile')
def get_user_profile():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = sqlite3.connect(SQLITE_PATH)
    cursor = conn.cursor()
    cursor.execute("""SELECT userid, name, phone, created_at FROM users WHERE userid = ?""", (session['userid'],))
    user = cursor.fetchone()
    conn.close()
    if user:
        return jsonify({'userid': user[0], 'name': user[1], 'phone': user[2], 'created_at': user[3]})
    return jsonify({'error': 'User not found'}), 404


@app.route('/api/remove_crop/<int:crop_id>', methods=['DELETE'])
def remove_crop(crop_id):
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = sqlite3.connect(SQLITE_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM user_crops WHERE id = ? AND userid = ?", (crop_id, session['userid']))
        crop = cursor.fetchone()
        if not crop:
            return jsonify({'error': 'Crop not found or not authorized'}), 404
        cursor.execute("DELETE FROM user_crops WHERE id = ? AND userid = ?", (crop_id, session['userid']))
        conn.commit()
        return jsonify({'status': 'success', 'message': 'Crop deleted successfully'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': f'Database error: {str(e)}'}), 500
    finally:
        conn.close()

# --- Water sensor control ---
@app.route('/api/water_control', methods=['POST'])
def water_control():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    action = request.json.get('action')
    # No real hardware; echo action
    return jsonify({'status': 'success', 'action': action})


@app.route('/api/tank_sensor_data', methods=['GET'])
def get_tank_sensor_data():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    simulate_sensor_scenarios()
    level = get_tank_level()
    capacity = 5000
    available = int(capacity * level / 100)
    return jsonify({
        'status': 'success',
        'tank_level': level, 'tank_capacity': capacity, 'available_water': available,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'sensor_status': 'active'
    })

# ---------- MAIN ----------
if __name__ == '__main__':
    # Start scheduler and seed a couple alerts on boot
    start_alert_scheduler()
    generate_daily_weather_alert()
    generate_water_tank_alert()
    app.run(debug=DEBUG, host=HOST, port=PORT)
