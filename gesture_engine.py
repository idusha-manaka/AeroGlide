import cv2
import mediapipe as mp
import pyautogui
import math
import time
import sys
from smooth import AdaptiveSmoother

# Prevent pyautogui from adding artificial delays (used for fallback or shortcuts)
pyautogui.PAUSE = 0.0
pyautogui.FAILSAFE = False

# ================= LOW-LEVEL WINDOWS OS INPUT ACCELERATION =================
IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import ctypes
    try:
        # Crucial for Windows laptops: registers Python as DPI-aware so coordinates
        # match 1:1 with the physical screen pixels, bypassing Windows display scaling (125%/150%).
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

    # Windows user32 mouse flags
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_WHEEL = 0x0800
    MOUSEEVENTF_HWHEEL = 0x01000

    def move_mouse(x, y):
        ctypes.windll.user32.SetCursorPos(x, y)

    def click_left_down():
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)

    def click_left_up():
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    def click_left():
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.01)
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    def click_right():
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
        time.sleep(0.01)
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)

    def click_double():
        click_left()
        time.sleep(0.05)
        click_left()

    def scroll_vertical(amount):
        # amount is multiplied to scroll larger pages quickly and smoothly
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, int(amount), 0)

    def scroll_horizontal(amount):
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_HWHEEL, 0, 0, int(amount), 0)

else:
    # Cross-platform fallback using PyAutoGUI
    def move_mouse(x, y):
        pyautogui.moveTo(x, y)

    def click_left_down():
        pyautogui.mouseDown()

    def click_left_up():
        pyautogui.mouseUp()

    def click_left():
        pyautogui.click()

    def click_right():
        pyautogui.rightClick()

    def click_double():
        pyautogui.doubleClick()

    def scroll_vertical(amount):
        pyautogui.scroll(amount)

    def scroll_horizontal(amount):
        pyautogui.hscroll(amount)


class GestureEngine:
    def __init__(self):
        # Settings (can be dynamically updated from the GUI)
        self.smoothing_min = 0.12
        self.smoothing_max = 0.80
        self.v_scale = 15.0
        
        self.click_threshold = 0.032
        self.scroll_threshold = 0.04
        self.zoom_threshold = 0.06
        self.hysteresis = 0.015
        
        # Pointer speed/sensitivity
        self.pointer_sensitivity = 1.0
        
        self.active_zone_x_min = 0.15
        self.active_zone_x_max = 0.85
        self.active_zone_y_min = 0.15
        self.active_zone_y_max = 0.85

        # Feature toggles
        self.enable_zoom = True
        self.enable_volume = True
        self.enable_drag = True

        # Math filter
        self.smoother = AdaptiveSmoother(
            alpha_min=self.smoothing_min, 
            alpha_max=self.smoothing_max, 
            v_scale=self.v_scale
        )

        # Screen metrics (Always 100% accurate physical screen resolution using DPI awareness)
        self.screen_w, self.screen_h = pyautogui.size()

        # State tracking variables
        self.is_clicked = False
        self.drag_active = False
        self.click_start_time = 0
        self.last_click_release_time = 0
        self.double_click_cooldown = 0.35  # seconds
        self.drag_hold_delay = 0.40       # seconds (hold pinch to start drag)
        
        self.prev_scroll_y = None
        self.prev_scroll_x = None
        self.scroll_multiplier = 40  # scroll speed
        
        self.zoom_start_dist = None
        self.last_zoom_time = 0
        self.zoom_cooldown = 0.15  # seconds between zoom increments
        
        self.prev_vol_y = None
        self.last_vol_time = 0
        self.vol_cooldown = 0.15

        self.prev_mode = "None"
        
        # Initialize MediaPipe Hands
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            max_num_hands=1,
            min_detection_confidence=0.75,
            min_tracking_confidence=0.75
        )
        self.mp_draw = mp.solutions.drawing_utils

    def get_distance(self, p1, p2):
        """Calculates 2D Euclidean distance between two landmark points."""
        return math.hypot(p1.x - p2.x, p1.y - p2.y)

    def is_finger_open(self, tip_id, wrist_id, hand_scale, landmarks, threshold=1.30):
        """Orientation-independent finger state detector based on proportional distance to wrist."""
        tip = landmarks[tip_id]
        wrist = landmarks[wrist_id]
        dist = math.hypot(tip.x - wrist.x, tip.y - wrist.y)
        normalized_dist = dist / hand_scale
        return normalized_dist > threshold

    def update_settings(self, **kwargs):
        """Allows dynamically updating settings from the GUI."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        
        # Dynamically scale active tracking zone centered at 0.5 based on pointer_sensitivity
        # High sensitivity -> small active zone box -> fast cursor jumps
        # Low sensitivity -> large active zone box -> relaxed comfortable cursor mapping (reduces hand strain!)
        base_range = 0.65 # default tracking box size (65% of camera frame)
        scaled_range = base_range / self.pointer_sensitivity
        
        # Clamp scaled_range to [0.35, 0.95] to prevent box from disappearing or overflowing
        scaled_range = max(0.35, min(0.95, scaled_range))
        
        half_range = scaled_range / 2.0
        self.active_zone_x_min = 0.5 - half_range
        self.active_zone_x_max = 0.5 + half_range
        self.active_zone_y_min = 0.5 - half_range
        self.active_zone_y_max = 0.5 + half_range

        # Sync smoother settings if they were modified
        self.smoother.alpha_min = self.smoothing_min
        self.smoother.alpha_max = self.smoothing_max
        self.smoother.v_scale = self.v_scale

    def process_frame(self, frame):
        """
        Processes a single camera frame, tracks hand, recognizes gesture,
        and triggers corresponding mouse/keyboard actions.
        Returns: processed frame with HUD overlay, current gesture mode string
        """
        h, w, _ = frame.shape
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self.hands.process(rgb)

        gesture_mode = "None"
        
        # 1. Draw Active Bounding Box (Active Touchpad Zone) on HUD
        x_min_px = int(self.active_zone_x_min * w)
        x_max_px = int(self.active_zone_x_max * w)
        y_min_px = int(self.active_zone_y_min * h)
        y_max_px = int(self.active_zone_y_max * h)
        
        # Semi-transparent active zone bounding box with rounded corners design
        cv2.rectangle(frame, (x_min_px, y_min_px), (x_max_px, y_max_px), (0, 255, 128), 2, lineType=cv2.LINE_AA)
        cv2.putText(
            frame, 
            "AeroGlide Active Zone", 
            (x_min_px + 5, y_min_px - 8), 
            cv2.FONT_HERSHEY_SIMPLEX, 
            0.5, 
            (0, 255, 128), 
            1, 
            cv2.LINE_AA
        )

        if result.multi_hand_landmarks:
            for hand_landmarks in result.multi_hand_landmarks:
                landmarks = hand_landmarks.landmark
                
                # 2. Draw styled glowing hand landmarks
                self.mp_draw.draw_landmarks(
                    frame, 
                    hand_landmarks, 
                    self.mp_hands.HAND_CONNECTIONS,
                    self.mp_draw.DrawingSpec(color=(0, 255, 255), thickness=2, circle_radius=3),
                    self.mp_draw.DrawingSpec(color=(0, 128, 255), thickness=2)
                )

                # Fetch landmarks for key fingers
                wrist = landmarks[0]
                thumb_tip = landmarks[4]
                index_tip = landmarks[8]
                index_pip = landmarks[6]
                middle_tip = landmarks[12]
                middle_pip = landmarks[10]
                ring_tip = landmarks[16]
                ring_pip = landmarks[14]
                pinky_tip = landmarks[20]
                pinky_pip = landmarks[18]

                # Calculate palm size to normalize finger lengths (making it scale & orientation independent)
                hand_scale = self.get_distance(landmarks[0], landmarks[9]) # WRIST to MIDDLE_MCP
                if hand_scale == 0:
                    hand_scale = 0.1
                
                # Determine which fingers are open (Scale and Rotation Independent!)
                index_open = self.is_finger_open(8, 0, hand_scale, landmarks, threshold=1.30)
                middle_open = self.is_finger_open(12, 0, hand_scale, landmarks, threshold=1.30)
                ring_open = self.is_finger_open(16, 0, hand_scale, landmarks, threshold=1.30)
                pinky_open = self.is_finger_open(20, 0, hand_scale, landmarks, threshold=1.20)

                # Calculate distances
                index_thumb_dist = self.get_distance(index_tip, thumb_tip)
                middle_thumb_dist = self.get_distance(middle_tip, thumb_tip)
                index_middle_dist = self.get_distance(index_tip, middle_tip)

                # ================= GESTURE CLASSIFIER STATE MACHINE =================

                # --- 1. ZOOM GESTURE (All fingers open, scale using Index and Thumb distance) ---
                if self.enable_zoom and index_open and middle_open and ring_open and pinky_open:
                    gesture_mode = "Zoom Mode"
                    current_time = time.time()
                    
                    if self.zoom_start_dist is None:
                        self.zoom_start_dist = index_thumb_dist
                    else:
                        diff = index_thumb_dist - self.zoom_start_dist
                        if abs(diff) > 0.025:
                            if current_time - self.last_zoom_time > self.zoom_cooldown:
                                if diff > 0:
                                    # Zoom In (Ctrl + Scroll Up)
                                    pyautogui.keyDown('ctrl')
                                    scroll_vertical(120)
                                    pyautogui.keyUp('ctrl')
                                    gesture_mode = "Zooming In"
                                else:
                                    # Zoom Out (Ctrl + Scroll Down)
                                    pyautogui.keyDown('ctrl')
                                    scroll_vertical(-120)
                                    pyautogui.keyUp('ctrl')
                                    gesture_mode = "Zooming Out"
                                self.last_zoom_time = current_time
                                # Update reference
                                self.zoom_start_dist = index_thumb_dist
                    
                    # Reset other continuous gesture memories
                    self.prev_scroll_y = None
                    self.prev_scroll_x = None
                    self.prev_vol_y = None

                # --- 2. SCROLL GESTURE (Index and Middle open, but kept close together) ---
                elif index_open and middle_open and not pinky_open and index_middle_dist <= self.zoom_threshold:
                    gesture_mode = "Scroll Mode"
                    self.zoom_start_dist = None
                    self.prev_vol_y = None
                    
                    # Calculate center point of scrolling fingers
                    avg_x = (index_tip.x + middle_tip.x) / 2
                    avg_y = (index_tip.y + middle_tip.y) / 2

                    if self.prev_scroll_y is not None and self.prev_scroll_x is not None:
                        dy = avg_y - self.prev_scroll_y
                        dx = avg_x - self.prev_scroll_x
                        
                        # Apply deadzones to prevent accidental micro-scrolls
                        if abs(dy) > 0.005:
                            scroll_amount = int(dy * self.scroll_multiplier * 450)
                            # Scroll vertically
                            scroll_vertical(-scroll_amount)
                        
                        if abs(dx) > 0.005:
                            scroll_amount = int(dx * self.scroll_multiplier * 450)
                            # Scroll horizontally
                            scroll_horizontal(scroll_amount)
                            
                    self.prev_scroll_y = avg_y
                    self.prev_scroll_x = avg_x

                # --- 3. SYSTEM VOLUME GESTURE (Thumb, Index, Middle open; Pinky folded) ---
                elif self.enable_volume and index_open and middle_open and not pinky_open and self.get_distance(thumb_tip, landmarks[5]) > 0.08:
                    gesture_mode = "Volume Mode"
                    self.zoom_start_dist = None
                    self.prev_scroll_y = None
                    self.prev_scroll_x = None
                    
                    current_time = time.time()
                    avg_y = index_tip.y
                    
                    if self.prev_vol_y is not None:
                        dy = avg_y - self.prev_vol_y
                        if abs(dy) > 0.015:
                            if current_time - self.last_vol_time > self.vol_cooldown:
                                if dy < 0:
                                    pyautogui.press('volumeup')
                                    gesture_mode = "Volume UP"
                                else:
                                    pyautogui.press('volumedown')
                                    gesture_mode = "Volume DOWN"
                                self.last_vol_time = current_time
                                self.prev_vol_y = avg_y
                    else:
                        self.prev_vol_y = avg_y

                # --- 4. CURSOR NAVIGATION & CLICK / DRAG (Index Open, Middle folded) ---
                elif index_open and not middle_open:
                    self.zoom_start_dist = None
                    self.prev_scroll_y = None
                    self.prev_scroll_x = None
                    self.prev_vol_y = None
                    
                    # Track finger within normalized box
                    raw_x = index_tip.x
                    raw_y = index_tip.y

                    # Normalize raw coordinates to active touchpad boundary
                    norm_x = (raw_x - self.active_zone_x_min) / (self.active_zone_x_max - self.active_zone_x_min)
                    norm_y = (raw_y - self.active_zone_y_min) / (self.active_zone_y_max - self.active_zone_y_min)

                    # Clamp to [0.0, 1.0] to keep cursor on screen edges
                    norm_x = max(0.0, min(1.0, norm_x))
                    norm_y = max(0.0, min(1.0, norm_y))

                    # Apply Adaptive Smoothing Filter
                    smoothed_x, smoothed_y = self.smoother.smooth(norm_x, norm_y)

                    # Interpolate to absolute screen pixel positions
                    screen_x = int(smoothed_x * self.screen_w)
                    screen_y = int(smoothed_y * self.screen_h)

                    # Determine click limits using Schmitt Trigger (Hysteresis)
                    click_limit = self.click_threshold + self.hysteresis if self.is_clicked else self.click_threshold

                    # --- GESTURE: RIGHT CLICK PINCH (Thumb & Middle Finger, only if not fully folded) ---
                    is_middle_folded = not middle_open
                    if not is_middle_folded and middle_thumb_dist < click_limit:
                        gesture_mode = "Right Clicking"
                        if not self.is_clicked:
                            click_right()
                            self.is_clicked = True
                            time.sleep(0.1) # short debounce
                    
                    # --- GESTURE: LEFT CLICK / DRAG PINCH (Thumb & Index Finger) ---
                    elif index_thumb_dist < click_limit:
                        current_time = time.time()
                        gesture_mode = "Left Clicking"
                        
                        if not self.is_clicked:
                            self.is_clicked = True
                            self.click_start_time = current_time
                            
                            # Check for Double Click
                            if current_time - self.last_click_release_time < self.double_click_cooldown:
                                click_double()
                                gesture_mode = "Double Clicked"
                                self.last_click_release_time = 0 # reset double click timer
                            else:
                                # Normal Click / Start Hold Drag
                                if not self.enable_drag:
                                    click_left()
                        
                        else:
                            # If pinch is held down and drag is enabled, trigger drag state
                            if self.enable_drag and not self.drag_active and (current_time - self.click_start_time > self.drag_hold_delay):
                                click_left_down()
                                self.drag_active = True
                            
                            if self.drag_active:
                                gesture_mode = "Dragging"
                                # Move cursor while dragging
                                move_mouse(screen_x, screen_y)
                                
                    # --- GESTURE: NORMAL NAVIGATION MODE (Index open, no pinch) ---
                    else:
                        gesture_mode = "Cursor Moving"
                        
                        # Handle Release events
                        if self.is_clicked:
                            current_time = time.time()
                            self.is_clicked = False
                            
                            if self.drag_active:
                                click_left_up()
                                self.drag_active = False
                                gesture_mode = "Drag Released"
                            else:
                                # Trigger normal click on release if we didn't drag
                                if self.enable_drag and (current_time - self.click_start_time <= self.drag_hold_delay):
                                    click_left()
                            
                            self.last_click_release_time = current_time
                        
                        # Move cursor on screen
                        move_mouse(screen_x, screen_y)

                    # Visual cursor path dot on the camera feed
                    cv2.circle(
                        frame, 
                        (int(raw_x * w), int(raw_y * h)), 
                        12, 
                        (0, 255, 255), 
                        -1, 
                        lineType=cv2.LINE_AA
                    )

                else:
                    # Idle / Unrecognized Hand State
                    self.zoom_start_dist = None
                    self.prev_scroll_y = None
                    self.prev_scroll_x = None
                    self.prev_vol_y = None
                    
                    # Release mouse if hand suddenly disappeared during drag
                    if self.drag_active:
                        click_left_up()
                        self.drag_active = False
                        self.is_clicked = False
                    
                    gesture_mode = "Idle"

        else:
            # No hand detected
            self.zoom_start_dist = None
            self.prev_scroll_y = None
            self.prev_scroll_x = None
            self.prev_vol_y = None
            
            if self.drag_active:
                click_left_up()
                self.drag_active = False
                self.is_clicked = False
            
            gesture_mode = "No Hand Detected"

        # Apply glassmorphism overlay on HUD to display state
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 50), (25, 25, 35), -1)
        cv2.addWeighted(overlay, 0.45, frame, 0.55, 0, frame)
        
        # Display Current Mode
        text_color = (0, 255, 255) if gesture_mode not in ["Idle", "No Hand Detected"] else (180, 180, 180)
        cv2.putText(
            frame, 
            f"MODE: {gesture_mode.upper()}", 
            (20, 32), 
            cv2.FONT_HERSHEY_SIMPLEX, 
            0.6, 
            text_color, 
            2, 
            cv2.LINE_AA
        )
        
        return frame, gesture_mode
        
    def release(self):
        """Cleans up MediaPipe context."""
        self.hands.close()
