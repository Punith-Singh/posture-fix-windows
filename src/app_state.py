"""
AppState — Central coordinator and state manager.

Wires together:
- WebcamService (head pose via MediaPipe)
- PostureAnalyzer (IIR filter + hysteresis state machine)
- AlertManager (sound, voice, notifications)
- HistoryStore (persistent daily stats)

Maintains live session counters, 60-second chart window, and settings.
"""

import time
import json
import os
import threading
from dataclasses import dataclass
from typing import Optional
from .posture_analyzer import PostureAnalyzer, PostureState
from .alert_manager import AlertManager
from .history_store import HistoryStore
from .webcam_service import WebcamService


CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config.json")
CHART_WINDOW_SECONDS = 60.0
CHART_SAMPLE_INTERVAL = 0.2  # 5 Hz downsampled


@dataclass
class DeviationSample:
    t: float      # Relative time (seconds since monitoring start)
    drop: float   # Head drop in degrees


class AppState:
    def __init__(self):
        # Sub-services
        self.analyzer = PostureAnalyzer()
        self.alerts = AlertManager()
        self.history = HistoryStore()
        self.webcam = WebcamService()

        # Monitoring state
        self.is_monitoring: bool = False
        self.posture_state: PostureState = PostureState.UNKNOWN
        self.live_pitch: float = 0.0
        self.deviation: float = 0.0
        self.is_calibrated: bool = False

        # Session stats
        self.good_seconds: float = 0.0
        self.bad_seconds: float = 0.0
        self.slouch_events: int = 0
        self._session_start: float = 0.0
        self._last_sample_time: float = 0.0
        self._last_chart_time: float = 0.0
        self._prev_state: PostureState = PostureState.UNKNOWN

        # Chart data — 60-second sliding window
        self.recent_samples: list[DeviationSample] = []
        self._sample_index: int = 0

        # UI callback
        self.on_state_change: Optional[callable] = None

        # Settings (loaded from config)
        self._settings = {
            "threshold": 15.0,
            "hold_seconds": 3.0,
            "cooldown": 20.0,
            "sound_enabled": True,
            "sound_name": "SystemExclamation",
            "voice_enabled": False,
            "notification_enabled": True,
            "invert": False,
            "camera_index": 0,
        }
        self._load_settings()
        self._apply_settings()

        # Wire webcam pitch callback
        self.webcam.on_pitch = self._handle_pitch

    # ── Settings ──────────────────────────────────────────────
    def _load_settings(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as f:
                    saved = json.load(f)
                self._settings.update(saved)
        except Exception as e:
            print(f"Config load error: {e}")

    def save_settings(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self._settings, f, indent=2)
        except Exception as e:
            print(f"Config save error: {e}")

    def _apply_settings(self):
        """Push current settings into sub-services."""
        s = self._settings
        self.analyzer.threshold_degrees = s["threshold"]
        self.analyzer.hold_seconds = s["hold_seconds"]
        self.analyzer.invert = s["invert"]
        self.alerts.cooldown = s["cooldown"]
        self.alerts.sound_enabled = s["sound_enabled"]
        self.alerts.sound_name = s["sound_name"]
        self.alerts.voice_enabled = s["voice_enabled"]
        self.alerts.notification_enabled = s["notification_enabled"]
        self.webcam.camera_index = s["camera_index"]

    def get_setting(self, key: str):
        return self._settings.get(key)

    def set_setting(self, key: str, value):
        self._settings[key] = value
        self._apply_settings()
        self.save_settings()

    def update_settings(self, new_settings: dict):
        self._settings.update(new_settings)
        self._apply_settings()
        self.save_settings()

    # ── Monitoring Controls ───────────────────────────────────
    def start_monitoring(self):
        if self.is_monitoring:
            return
        self.is_monitoring = True
        self._session_start = time.time()
        self._last_sample_time = time.time()
        self._last_chart_time = time.time()
        self.webcam.start()
        self._notify_ui()

    def stop_monitoring(self):
        if not self.is_monitoring:
            return
        self.is_monitoring = False
        self.webcam.stop()
        self._flush_session()
        self.posture_state = PostureState.UNKNOWN
        self._notify_ui()

    def calibrate(self):
        if not self.webcam.is_connected:
            return False
        if not self.webcam.face_detected:
            return False
        self._flush_session()  # Save current session before recalibrating
        self.analyzer.calibrate()
        self.is_calibrated = True
        self.alerts.reset_cooldown()
        self._reset_session()
        self._notify_ui()
        return True

    # ── Pitch Processing Pipeline ─────────────────────────────
    def _handle_pitch(self, pitch: float):
        """Called by webcam service on every new pitch sample."""
        if not self.is_monitoring:
            return

        now = time.time()
        self.live_pitch = pitch

        # Run through analyzer
        prev_state = self.posture_state
        self.posture_state = self.analyzer.update(pitch, now)
        self.deviation = self.analyzer.drop
        self.is_calibrated = self.analyzer.is_calibrated

        # Accumulate session time
        dt = now - self._last_sample_time
        self._last_sample_time = now
        if dt < 2.0 and self.is_calibrated:  # Ignore gaps > 2s
            if self.posture_state == PostureState.BAD:
                self.bad_seconds += dt
            elif self.posture_state == PostureState.GOOD:
                self.good_seconds += dt

        # Track state transitions
        if self.posture_state == PostureState.BAD and prev_state != PostureState.BAD:
            self.slouch_events += 1

        # Downsample chart data at 5 Hz
        if (now - self._last_chart_time) >= CHART_SAMPLE_INTERVAL:
            self._last_chart_time = now
            t = now - self._session_start
            sample = DeviationSample(t=t, drop=max(0.0, self.deviation))
            self.recent_samples.append(sample)

            # Trim to 60-second window
            cutoff = t - CHART_WINDOW_SECONDS
            self.recent_samples = [s for s in self.recent_samples if s.t >= cutoff]

        # Fire alert if slouching
        if self.posture_state == PostureState.BAD:
            self.alerts.trigger_slouch_alert(deviation=self.deviation, now=now)

        self._notify_ui()

    # ── Session Management ────────────────────────────────────
    def _reset_session(self):
        self.good_seconds = 0.0
        self.bad_seconds = 0.0
        self.slouch_events = 0
        self.recent_samples = []
        self._session_start = time.time()
        self._last_sample_time = time.time()
        self._last_chart_time = time.time()

    def _flush_session(self):
        """Save session data to history store. Discard sessions < 5 seconds."""
        total = self.good_seconds + self.bad_seconds
        if total < 5.0:
            return
        self.history.record(
            good=self.good_seconds,
            bad=self.bad_seconds,
            slouches=self.slouch_events,
        )

    @property
    def session_elapsed(self) -> float:
        if not self.is_monitoring:
            return 0.0
        return time.time() - self._session_start

    @property
    def good_percent(self) -> float:
        total = self.good_seconds + self.bad_seconds
        if total <= 0:
            return 0.0
        return (self.good_seconds / total) * 100.0

    @property
    def slouch_fraction(self) -> float:
        """Fraction of threshold reached (0.0 to 1.0+)."""
        if self.analyzer.threshold_degrees <= 0:
            return 0.0
        return max(0.0, min(1.0, self.deviation / self.analyzer.threshold_degrees))

    # ── UI Notification ───────────────────────────────────────
    def _notify_ui(self):
        if self.on_state_change:
            try:
                self.on_state_change()
            except Exception:
                pass
