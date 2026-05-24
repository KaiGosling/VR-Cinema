# VR Cinema Mirror
### Poco C65 · Spacedesk · VR Box

Mirrors your PC screen to your Poco C65 in a side-by-side VR cinema layout — 
designed for VR Box headsets with dual lenses.

---

## Setup (one time)

### 1. Install Python
https://python.org — version 3.9 or newer

### 2. Install dependencies
```
pip install -r requirements.txt
```

### 3. Set up Spacedesk
- Install **Spacedesk Driver** on your PC: https://www.spacedesk.net
- Install **Spacedesk app** on your Poco C65 (Play Store)
- Connect Poco C65 to PC via USB cable
- Open Spacedesk app on phone → tap your PC → select **USB**

### 4. Run the app
```
python vr_cinema.py
```

---

## How to Use

1. Connect Poco C65 via USB + Spacedesk (phone becomes second monitor)
2. App auto-detects it and enables mirror mode
3. Click **LAUNCH VR CINEMA**
4. A fullscreen side-by-side window opens — drag it to your Poco C65 screen
5. Maximize it on the phone screen
6. Put phone in VR Box
7. Your PC screen appears as a cinema screen in each eye 🎬

---

## What the Cinema View Looks Like

```
┌────────────────────┬────────────────────┐
│                    │                    │
│    ┌──────────┐    │    ┌──────────┐    │
│    │ PC screen│    │    │ PC screen│    │
│    │  (live)  │    │    │  (live)  │    │
│    └──────────┘    │    └──────────┘    │
│   dark room/vig    │   dark room/vig    │
│    LEFT EYE        │    RIGHT EYE       │
└────────────────────┴────────────────────┘
```

Each eye sees: dark background + vignette border + your live PC screen in the center.
Through VR Box lenses = immersive cinema feel.

---

## Controls
- **ESC** — close cinema window
- **↻ refresh** — re-scan for displays
- **Auto-mirror checkbox** — automatically mirrors when phone connects

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Phone not detected | Open Spacedesk app on phone first, then refresh |
| Black screen in cinema | Make sure Mirror is ON before launching cinema |
| Laggy capture | Normal over USB, close other heavy apps |
| pip install fails | Run as Administrator |
