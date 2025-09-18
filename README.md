# HillTech-Growers


-- **Login Credentials**
User Id : 001
password :12345

-- **Arduino code** is inside : hillTech.ino

# 🌱 Smart Agriculture Platform

A Flask-based smart agriculture web application for farmers, integrating:
- **Weather forecasts** (OpenWeatherMap API)
- **ESP32 sensor data** (soil moisture, tank ultrasonic sensor)
- **Crop recommendations** from CSV dataset
- **Water requirement calculator**
- **Profit & yield analysis per crop**
- **Alerts & notifications** (weather, irrigation, water tank)
- **User authentication** (register/login/logout)
- **SQLite database** for persistence
- **Daily background scheduler** for automatic alerts

⚡ This version removes **all Twilio/SMS functionality** — web-only app.

---

## 📂 Project Structure
```
smart-agriculture/
│
├── app.py                 # Main Flask application
├── cropsnew.csv           # Crop dataset (CSV)
├── .env                   # Environment variables
├── smart_agri.db          # SQLite database (auto-created)
│
├── templates/             # HTML templates
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html
│   ├── dashboard2.html
│   ├── alerts.html
│   ├── water.html
│   └── crop_detail.html
│
├── static/                # Static assets (CSS, JS, images)
```

---

## ⚙️ Requirements

Install dependencies:

```bash
pip install flask python-dotenv pandas requests schedule
```

---

## 🔑 Environment Variables

Create a **`.env`** file in the root folder:

```ini
# Flask
FLASK_SECRET_KEY=smart_agriculture_2025_sikkim
FLASK_DEBUG=true
FLASK_HOST=0.0.0.0
FLASK_PORT=5000

# OpenWeatherMap
OWM_API_KEY=your_openweathermap_api_key
OWM_CITY=Jorethang,IN

# ESP32
ESP32_ENDPOINT=http://10.64.119.95/data
ESP32_TIMEOUT_S=3

# Tank geometry (cm)
TANK_HEIGHT_CM=9.5
TANK_RADIUS_CM=4.85

# Scheduler times (24h format)
DAILY_WEATHER_ALERT_TIME=07:00
TANK_ALERT_TIME_MORNING=06:00
TANK_ALERT_TIME_EVENING=18:00

# SQLite DB
SQLITE_PATH=smart_agri.db
```

---

## ▶️ Running the App

```bash
python app.py
```

Access the app at: [http://localhost:5000](http://localhost:5000)

---

## 🧑‍🌾 Features

### 1. Authentication
- Register/login/logout
- Basic validation (numeric UserID, 10-digit phone)

### 2. Dashboards
- **Dashboard 1:** Live soil sensor data, weather, irrigation status, tank level, crop recommendations
- **Dashboard 2:** User list overview

### 3. Crop Tools
- **Water Calculator:** Estimate liters needed for a crop by acreage
- **Crop Detail Page:** Yield, price, profit calculator, water needs

### 4. Alerts
- Daily weather alerts (rain risk, irrigation advice)
- Water tank alerts (low/medium/full)
- Irrigation recommendations
- Alerts stored in SQLite + displayed in UI

### 5. APIs
REST endpoints for sensor data, alerts, crop management, and water control (mock).

Examples:
- `/api/esp32/data`
- `/api/run_alerts`
- `/api/user_crops`
- `/api/water_tank_alert`

### 6. Scheduler
Background thread runs daily tasks:
- Weather alert
- Tank alert (morning & evening)

---

## 🚜 Crop Dataset (`cropsnew.csv`)

Your CSV should contain at least:

- `Crop`
- `Soil Type`
- `Soil Moisture`
- `Min Temp`, `Max temp`
- `Min Humidity`, `Max Humidity`
- `Total Water ( mm )`
- `Yield`, `Price`

---

## 🔒 Notes & Improvements
- Passwords are stored as plain text (⚠️ replace with hashing for production).
- Scheduler runs in a background thread (suitable for demo; consider APScheduler or cron for production).
- Ensure ESP32 device is reachable at `ESP32_ENDPOINT`.

---

## 📸 Screens (expected)
- **Login/Register**
- <img width="1902" height="888" alt="image" src="https://github.com/user-attachments/assets/7a5c0e57-62cc-45e7-a2c3-bfa2f1cf8f69" />

- **Dashboard** with soil/weather/tank/crops
- <img width="1047" height="830" alt="Screenshot 2025-09-18 170517" src="https://github.com/user-attachments/assets/f79a83a3-5483-44f1-abf0-ca67a1e96e99" />

- <img width="1209" height="849" alt="Screenshot 2025-09-18 170345" src="https://github.com/user-attachments/assets/d98d690a-19b7-4057-a610-bf1a5d28c37c" />

- **Alerts Page**
- <img width="1074" height="760" alt="Screenshot 2025-09-18 170541" src="https://github.com/user-attachments/assets/6089db7a-dad4-43bb-934f-3c22460a1e33" />

- **Water Calculator**
- <img width="1143" height="860" alt="Screenshot 2025-09-18 170833" src="https://github.com/user-attachments/assets/ac298dfa-4ad5-4f2d-a330-615ac8c38dbb" />

- **Crop Detail with profit/water analysis**
- <img width="1184" height="892" alt="Screenshot 2025-09-18 170815" src="https://github.com/user-attachments/assets/fabd2672-b572-4884-b822-f3900c693f7d" />

