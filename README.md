# PostureFix for Windows

A real-time posture correction tool for Windows that uses your webcam and AI (MediaPipe Face Landmarker) to detect when you slouch and alert you to sit up straight.

Inspired by the original macOS PostureFix app, but completely rebuilt for Windows without requiring specialized hardware like AirPods.

## Features
- **Real-time AI Head Tracking:** Uses MediaPipe Tasks API to accurately track your 3D head pose via any standard webcam.
- **Smart Filtering:** Uses an IIR low-pass filter to smooth out sudden movements and prevent false alarms.
- **Multi-channel Alerts:** Configurable sound effects, voice TTS ("Sit up straight"), and Windows toast notifications.
- **Live Dashboard:** Dark-themed UI with real-time pitch display, progress bars, and a 60-second live chart.
- **Session Stats & History:** Tracks good posture percentage and saves a 7-day history chart.
- **Privacy First:** All AI processing happens completely locally on your machine. No images are ever saved or sent anywhere.

## Installation
1. Clone this repository.
2. Ensure you have Python 3.10+ installed.
3. Create a virtual environment and install the requirements:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```

## Usage
Double-click `run.bat` to launch the app.
Click **Start Monitoring**, sit up straight, and click **Calibrate**. The app will now run in the background (or system tray) and nudge you if you slouch!
