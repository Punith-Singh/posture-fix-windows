"""
WebcamService — Real-time head pose estimation using MediaPipe Tasks API.

Uses MediaPipe Face Landmarker to directly get the 3D facial transformation matrix,
extracts pitch (head drop/tilt) and feeds it to the posture analyzer.
"""

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import threading
import time
import os
import logging
from typing import Callable, Optional


class WebcamService:
    def __init__(self):
        self.logger = logging.getLogger("PostureFix")
        self.is_connected: bool = False
        self.status_text: str = "Camera Off"
        self.on_pitch: Optional[Callable[[float], None]] = None
        self.on_status_change: Optional[Callable[[str], None]] = None
        self.camera_index: int = 0

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._cap = None

        # Head pose output (for UI display)
        self.current_pitch: float = 0.0
        self.current_yaw: float = 0.0
        self.current_roll: float = 0.0
        self.face_detected: bool = False

    def _set_status(self, text: str):
        self.status_text = text
        if self.on_status_change:
            self.on_status_change(text)

    def start(self):
        """Start webcam capture and head tracking."""
        if self._running:
            self.logger.info("WebcamService.start() called but already running")
            return
        self.logger.info("WebcamService.start() — launching capture thread")
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        self.logger.info("WebcamService capture thread started")

    def stop(self):
        """Stop webcam capture."""
        self._running = False
        self.is_connected = False
        self.face_detected = False
        self._set_status("Camera Off")

    def _capture_loop(self):
        """Main capture loop — runs in a background thread."""
        self._set_status("Opening camera...")
        self.logger.info("Starting webcam capture...")

        # Initialize MediaPipe Face Landmarker
        try:
            model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "face_landmarker.task")
            base_options = python.BaseOptions(model_asset_path=model_path)
            options = vision.FaceLandmarkerOptions(
                base_options=base_options,
                output_face_blendshapes=False,
                output_facial_transformation_matrixes=True,
                num_faces=1,
            )
            detector = vision.FaceLandmarker.create_from_options(options)
            self.logger.info("MediaPipe Face Landmarker initialized")
        except Exception as e:
            import traceback
            self.logger.error(f"MediaPipe init failed: {e}")
            traceback.print_exc()
            self._set_status(f"MediaPipe error: {e}")
            self.is_connected = False
            return

        # Open camera
        try:
            self._cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            if not self._cap.isOpened():
                self.logger.warning("Camera failed to open with DSHOW! Falling back to default backend...")
                self._cap = cv2.VideoCapture(self.camera_index)
                if not self._cap.isOpened():
                    self.logger.error("Camera failed to open entirely!")
                    self._set_status("Camera not found! Check Settings.")
                    self.is_connected = False
                    return
            self.logger.info(f"Camera {self.camera_index} opened successfully")
        except Exception as e:
            self.logger.error(f"Camera open error: {e}")
            self._set_status(f"Camera error: {e}")
            self.is_connected = False
            return

        # Set camera properties for performance
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self._cap.set(cv2.CAP_PROP_FPS, 30)

        self.is_connected = True
        self._set_status("Camera active — tracking head")

        last_process_time = 0
        process_interval = 1.0 / 30.0  # Process at 30 FPS for immediate response

        try:
            while self._running:
                ret, frame = self._cap.read()
                if not ret:
                    self._set_status("Camera read error, retrying...")
                    time.sleep(0.5)
                    continue

                now = time.time()
                if now - last_process_time < process_interval:
                    time.sleep(0.01)
                    continue
                last_process_time = now

                # Convert to RGB for MediaPipe
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                
                # Detect face and pose
                detection_result = detector.detect(mp_image)

                if detection_result.facial_transformation_matrixes:
                    self.face_detected = True
                    # Get the 4x4 transformation matrix
                    matrix = detection_result.facial_transformation_matrixes[0]
                    # Extract 3x3 rotation matrix
                    R = matrix[:3, :3]
                    
                    # Decompose rotation matrix to Euler angles
                    pitch, yaw, roll = self._rotation_matrix_to_euler(R)

                    self.current_pitch = pitch
                    self.current_yaw = yaw
                    self.current_roll = roll

                    # Feed pitch to the posture analyzer
                    if self.on_pitch:
                        self.on_pitch(pitch)
                else:
                    self.face_detected = False
                    if self.is_connected:
                        self._set_status("No face detected — look at camera")

        except Exception as e:
            import traceback
            self.logger.error(f"Webcam error: {e}")
            traceback.print_exc()
            self._set_status(f"Error: {e}")
        finally:
            self.logger.info("Webcam capture stopped")
            if self._cap:
                self._cap.release()
            self.is_connected = False
            self.face_detected = False

    @staticmethod
    def _rotation_matrix_to_euler(R: np.ndarray) -> tuple[float, float, float]:
        """
        Convert a 3x3 rotation matrix to Euler angles (pitch, yaw, roll) in degrees.

        Returns:
            (pitch, yaw, roll) in degrees.
            Pitch: positive = looking down (head tilting forward = slouching)
            Yaw: positive = looking right
            Roll: positive = tilting right
        """
        sy = np.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)

        if sy > 1e-6:
            pitch = np.degrees(np.arctan2(R[2, 1], R[2, 2]))  # Rotation around X
            yaw = np.degrees(np.arctan2(-R[2, 0], sy))         # Rotation around Y
            roll = np.degrees(np.arctan2(R[1, 0], R[0, 0]))    # Rotation around Z
        else:
            pitch = np.degrees(np.arctan2(-R[1, 2], R[1, 1]))
            yaw = np.degrees(np.arctan2(-R[2, 0], sy))
            roll = 0.0

        return pitch, yaw, roll
