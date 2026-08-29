"""
AlertManager — Multi-channel notification and alert dispatcher.

Mirrors macOS AlertManager.swift:
- Windows system sound
- Voice cue via pyttsx3 (text-to-speech)
- Windows toast notification
- Rate-limiting cooldown
"""

import time
import threading
import winsound


class AlertManager:
    AVAILABLE_SOUNDS = [
        "SystemAsterisk", "SystemExclamation", "SystemHand", "SystemQuestion", "SystemDefault"
    ]

    def __init__(self):
        self.sound_enabled: bool = True
        self.voice_enabled: bool = False
        self.notification_enabled: bool = True
        self.cooldown: float = 20.0  # seconds between alerts
        self.sound_name: str = "SystemExclamation"

        self._last_alert: float | None = None
        self._tts_engine = None
        self._tts_lock = threading.Lock()

    def _get_tts_engine(self):
        """Lazy-initialize pyttsx3 engine (must be created in the thread that uses it)."""
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty('rate', 150)
            return engine
        except Exception as e:
            print(f"TTS init error: {e}")
            return None

    def trigger_slouch_alert(self, deviation: float, now: float | None = None):
        """
        Fire a slouch alert across all enabled channels.
        Respects cooldown to prevent alert fatigue.
        """
        if now is None:
            now = time.time()

        # Check cooldown
        if self._last_alert is not None and (now - self._last_alert) < self.cooldown:
            return

        self._last_alert = now

        # Sound cue
        if self.sound_enabled:
            self._play_sound()

        # Voice cue
        if self.voice_enabled:
            threading.Thread(target=self._speak, args=("Sit up straight",), daemon=True).start()

        # Windows notification
        if self.notification_enabled:
            threading.Thread(target=self._notify, args=(deviation,), daemon=True).start()

    def preview_sound(self):
        """Play the currently selected sound for preview."""
        self._play_sound()

    def reset_cooldown(self):
        """Clear cooldown timer (e.g. after fresh calibration)."""
        self._last_alert = None

    def _play_sound(self):
        """Play a Windows system sound."""
        try:
            sound_map = {
                "SystemAsterisk": winsound.MB_ICONASTERISK,
                "SystemExclamation": winsound.MB_ICONEXCLAMATION,
                "SystemHand": winsound.MB_ICONHAND,
                "SystemQuestion": winsound.MB_ICONQUESTION,
                "SystemDefault": winsound.MB_OK,
            }
            flag = sound_map.get(self.sound_name, winsound.MB_ICONEXCLAMATION)
            winsound.MessageBeep(flag)
        except Exception as e:
            print(f"Sound error: {e}")

    def _speak(self, text: str):
        """Speak text using pyttsx3 text-to-speech."""
        with self._tts_lock:
            try:
                engine = self._get_tts_engine()
                if engine:
                    engine.say(text)
                    engine.runAndWait()
                    engine.stop()
            except Exception as e:
                print(f"TTS error: {e}")

    def _notify(self, deviation: float):
        """Send a Windows toast notification."""
        try:
            from plyer import notification
            notification.notify(
                title="Fix your posture",
                message=f"Your head dropped {deviation:.0f}° below your baseline — straighten your neck.",
                timeout=5,
            )
        except Exception as e:
            print(f"Notification error: {e}")
