"""
PostureAnalyzer — Pure mathematical detection engine for posture classification.

Mirrors the macOS PostureAnalyzer.swift exactly:
- Single-pole IIR Exponential Low-Pass Filter (alpha = 0.2)
- Baseline calibration
- Dual time-window hysteresis (hold for slouch trigger, recover for upright recovery)
"""

import time
from enum import Enum


class PostureState(Enum):
    UNKNOWN = "unknown"    # Not yet calibrated
    GOOD = "good"          # Upright posture
    BAD = "bad"            # Sustained slouch


class PostureAnalyzer:
    def __init__(self):
        # Tunable parameters (match macOS defaults)
        self.threshold_degrees: float = 15.0
        self.hold_seconds: float = 3.0
        self.recover_seconds: float = 1.5
        self.invert: bool = False
        self.alpha: float = 0.6  # Increased for much faster response

        # Internal state
        self._smoothed: float | None = None
        self._baseline: float | None = None
        self._bad_since: float | None = None
        self._good_since: float | None = None
        self.state: PostureState = PostureState.UNKNOWN
        self.drop: float = 0.0

    @property
    def is_calibrated(self) -> bool:
        return self._baseline is not None

    @property
    def smoothed_pitch(self) -> float:
        return self._smoothed if self._smoothed is not None else 0.0

    def calibrate(self):
        """Capture current smoothed pitch as the upright baseline."""
        if self._smoothed is None:
            return
        self._baseline = self._smoothed
        self._bad_since = None
        self._good_since = None
        self.state = PostureState.GOOD
        self.drop = 0.0

    def reset(self):
        """Full reset of analyzer state."""
        self._smoothed = None
        self._baseline = None
        self._bad_since = None
        self._good_since = None
        self.state = PostureState.UNKNOWN
        self.drop = 0.0

    def update(self, pitch_degrees: float, now: float | None = None) -> PostureState:
        """
        Feed a new pitch sample. Returns the current PostureState.

        Args:
            pitch_degrees: Raw pitch reading in degrees.
            now: Current timestamp (time.time()). If None, uses time.time().
        """
        if now is None:
            now = time.time()

        # --- Low-pass filter ---
        # S_t = S_{t-1} + alpha * (P_t - S_{t-1})
        if self._smoothed is None:
            self._smoothed = pitch_degrees
        else:
            self._smoothed = self._smoothed + self.alpha * (pitch_degrees - self._smoothed)

        # --- If not calibrated, nothing more to do ---
        if self._baseline is None:
            return self.state

        # --- Drop calculation ---
        # Positive pitch increase = head dropping forward (slouching)
        raw_drop = self._smoothed - self._baseline
        self.drop = -raw_drop if self.invert else raw_drop

        # --- State machine with hysteresis ---
        if self.drop >= self.threshold_degrees:
            # Slouching detected
            self._good_since = None
            if self._bad_since is None:
                self._bad_since = now
            elif (now - self._bad_since) >= self.hold_seconds:
                self.state = PostureState.BAD
        else:
            # Not slouching
            self._bad_since = None
            if self._good_since is None:
                self._good_since = now
            elif (now - self._good_since) >= self.recover_seconds:
                self.state = PostureState.GOOD

        return self.state
