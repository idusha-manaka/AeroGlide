import tkinter as tk
import customtkinter as ctk
import cv2
import threading
import time
from video_stream import VideoStream
from gesture_engine import GestureEngine

# Set gorgeous light theme style
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")  # Clean base light palette

class AeroGlideApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window Config
        self.title("AeroGlide Virtual Touchpad")
        self.geometry("780x630")  # Increased height to resolve start button truncation bug!
        self.resizable(False, False)
        self.configure(fg_color="#F8F6FC")  # Soft clean lavender-white backdrop

        # Threading & Control states
        self.is_touchpad_running = False
        self.stream = None
        self.engine = None
        self.loop_thread = None
        
        # Performance variables
        self.fps = 0
        self.current_mode = "Idle"
        
        self.build_ui()

    def build_ui(self):
        # Configure Grid
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=3) # Controls
        self.grid_columnconfigure(1, weight=2) # Diagnostics

        # ================= LEFT SIDE PANEL: CONTROLS & SETTINGS =================
        self.left_panel = ctk.CTkFrame(
            self, 
            corner_radius=15, 
            fg_color="#FFFFFF",
            border_width=2,
            border_color="#FFB7C5"  # Soft pastel Sakura Pink border
        )
        self.left_panel.grid(row=0, column=0, padx=15, pady=15, sticky="nsew")
        
        self.title_lbl = ctk.CTkLabel(
            self.left_panel, 
            text="🌸 AEROGLIDE CONTROL PANEL 🌸", 
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color="#4A3C6B"  # High-contrast deep plum purple
        )
        self.title_lbl.pack(pady=(20, 5))

        self.title_sub = ctk.CTkLabel(
            self.left_panel,
            text="─── SYSTEM INTERFACE: ONLINE ───",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#FF8DA1"
        )
        self.title_sub.pack(pady=(0, 15))

        # --- SLIDER: Smoothing Min (Precision) ---
        self.smooth_min_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.smooth_min_frame.pack(fill="x", padx=25, pady=8)
        self.smooth_min_lbl = ctk.CTkLabel(
            self.smooth_min_frame, 
            text="Fine Precision Smoothing: 0.12", 
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#4A3C6B"
        )
        self.smooth_min_lbl.pack(anchor="w")
        self.smooth_min_slider = ctk.CTkSlider(
            self.smooth_min_frame, 
            from_=0.02, 
            to=0.35, 
            number_of_steps=100,
            command=self.on_settings_change,
            fg_color="#F0ECF8",
            progress_color="#FF8DA1",
            button_color="#B19FFB",
            button_hover_color="#9C85FB"
        )
        self.smooth_min_slider.set(0.12)
        self.smooth_min_slider.pack(fill="x", pady=4)

        # --- SLIDER: Smoothing Max (Velocity) ---
        self.smooth_max_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.smooth_max_frame.pack(fill="x", padx=25, pady=8)
        self.smooth_max_lbl = ctk.CTkLabel(
            self.smooth_max_frame, 
            text="Fast Motion Responsiveness: 0.80", 
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#4A3C6B"
        )
        self.smooth_max_lbl.pack(anchor="w")
        self.smooth_max_slider = ctk.CTkSlider(
            self.smooth_max_frame, 
            from_=0.40, 
            to=0.98, 
            number_of_steps=100,
            command=self.on_settings_change,
            fg_color="#F0ECF8",
            progress_color="#FF8DA1",
            button_color="#B19FFB",
            button_hover_color="#9C85FB"
        )
        self.smooth_max_slider.set(0.80)
        self.smooth_max_slider.pack(fill="x", pady=4)

        # --- SLIDER: Click Distance ---
        self.click_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.click_frame.pack(fill="x", padx=25, pady=8)
        self.click_lbl = ctk.CTkLabel(
            self.click_frame, 
            text="Pinch Click Threshold: 0.30", 
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#4A3C6B"
        )
        self.click_lbl.pack(anchor="w")
        self.click_slider = ctk.CTkSlider(
            self.click_frame, 
            from_=0.15, 
            to=0.45, 
            number_of_steps=100,
            command=self.on_settings_change,
            fg_color="#F0ECF8",
            progress_color="#FF8DA1",
            button_color="#B19FFB",
            button_hover_color="#9C85FB"
        )
        self.click_slider.set(0.30)
        self.click_slider.pack(fill="x", pady=4)

        # --- SLIDER: Pointer Speed / Sensitivity ---
        self.sens_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.sens_frame.pack(fill="x", padx=25, pady=8)
        self.sens_lbl = ctk.CTkLabel(
            self.sens_frame, 
            text="Cursor Speed / Sensitivity: 1.00x", 
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#4A3C6B"
        )
        self.sens_lbl.pack(anchor="w")
        self.sens_slider = ctk.CTkSlider(
            self.sens_frame, 
            from_=0.5, 
            to=2.0, 
            number_of_steps=150,
            command=self.on_settings_change,
            fg_color="#F0ECF8",
            progress_color="#FF8DA1",
            button_color="#B19FFB",
            button_hover_color="#9C85FB"
        )
        self.sens_slider.set(1.0)
        self.sens_slider.pack(fill="x", pady=4)

        # --- TOGGLES: Gestures Features ---
        self.toggles_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.toggles_frame.pack(fill="x", padx=25, pady=15)
        
        self.enable_zoom_sw = ctk.CTkSwitch(
            self.toggles_frame, 
            text="Enable Zoom In/Out Gesture", 
            command=self.on_settings_change,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#5A4D7C",
            fg_color="#F0ECF8",
            progress_color="#FF8DA1",
            button_color="#B19FFB",
            button_hover_color="#9C85FB"
        )
        self.enable_zoom_sw.select()
        self.enable_zoom_sw.pack(anchor="w", pady=5)

        self.enable_vol_sw = ctk.CTkSwitch(
            self.toggles_frame, 
            text="Enable System Volume Gesture", 
            command=self.on_settings_change,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#5A4D7C",
            fg_color="#F0ECF8",
            progress_color="#FF8DA1",
            button_color="#B19FFB",
            button_hover_color="#9C85FB"
        )
        self.enable_vol_sw.select()
        self.enable_vol_sw.pack(anchor="w", pady=5)

        self.enable_drag_sw = ctk.CTkSwitch(
            self.toggles_frame, 
            text="Enable Pinch-to-Drag Gesture", 
            command=self.on_settings_change,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#5A4D7C",
            fg_color="#F0ECF8",
            progress_color="#FF8DA1",
            button_color="#B19FFB",
            button_hover_color="#9C85FB"
        )
        self.enable_drag_sw.select()
        self.enable_drag_sw.pack(anchor="w", pady=5)


        # ================= RIGHT SIDE PANEL: DIAGNOSTICS =================
        self.right_panel = ctk.CTkFrame(
            self, 
            corner_radius=15, 
            fg_color="#FFFFFF",
            border_width=2,
            border_color="#B19FFB"  # Soft pastel Lavender border
        )
        self.right_panel.grid(row=0, column=1, padx=15, pady=15, sticky="nsew")
        
        self.diag_lbl = ctk.CTkLabel(
            self.right_panel, 
            text="📊 LIVE DIAGNOSTICS", 
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color="#B19FFB"
        )
        self.diag_lbl.pack(pady=(20, 5))

        self.diag_sub = ctk.CTkLabel(
            self.right_panel,
            text="─── TELEMETRY MONITOR ───",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#FF8DA1"
        )
        self.diag_sub.pack(pady=(0, 10))

        # LED status circle (canvas indicator styled as Magical Girl target frame)
        self.led_canvas = tk.Canvas(self.right_panel, width=100, height=100, bg="#FFFFFF", highlightthickness=0)
        self.led_canvas.pack(pady=10)
        
        # Soft anime magical circle reticle decor
        self.led_canvas.create_oval(10, 10, 90, 90, outline="#B19FFB", width=2)
        self.led_canvas.create_oval(20, 20, 80, 80, outline="#FFB7C5", width=1, dash=(4, 2))
        self.led_canvas.create_line(5, 50, 20, 50, fill="#FFB7C5", width=2)
        self.led_canvas.create_line(80, 50, 95, 50, fill="#FFB7C5", width=2)
        self.led_canvas.create_line(50, 5, 50, 20, fill="#FFB7C5", width=2)
        self.led_canvas.create_line(50, 80, 50, 95, fill="#FFB7C5", width=2)
        
        self.led_circle = self.led_canvas.create_oval(35, 35, 65, 65, fill="#E6E6FA", outline="#B19FFB", width=1)

        self.status_lbl = ctk.CTkLabel(
            self.right_panel, 
            text="SYSTEM OFFLINE", 
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#FF8DA1"
        )
        self.status_lbl.pack(pady=5)

        # Mode Box HUD
        self.mode_frame = ctk.CTkFrame(
            self.right_panel, 
            corner_radius=10, 
            fg_color="#FDF8FA",
            border_width=1,
            border_color="#FFB7C5"
        )
        self.mode_frame.pack(fill="x", padx=20, pady=15)
        
        self.mode_title = ctk.CTkLabel(
            self.mode_frame, 
            text="🌸 CURRENT GESTURE STATE 🌸", 
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), 
            text_color="#5A4D7C"
        )
        self.mode_title.pack(pady=(8, 2))
        self.mode_value = ctk.CTkLabel(
            self.mode_frame, 
            text="INACTIVE", 
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"), 
            text_color="#FF8DA1"
        )
        self.mode_value.pack(pady=(0, 8))

        # Camera preview switch
        self.show_cam_sw = ctk.CTkSwitch(
            self.right_panel, 
            text="Show HUD Camera Feed",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#5A4D7C",
            fg_color="#F0ECF8",
            progress_color="#FF8DA1",
            button_color="#B19FFB",
            button_hover_color="#9C85FB"
        )
        self.show_cam_sw.select()
        self.show_cam_sw.pack(pady=10)

        # FPS HUD
        self.fps_lbl = ctk.CTkLabel(
            self.right_panel, 
            text="TELEMETRY: 0 FPS", 
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#5A4D7C"
        )
        self.fps_lbl.pack(side="bottom", pady=20)


        # ================= BOTTOM PANEL: MAIN TRIGGER BUTTON =================
        self.start_btn = ctk.CTkButton(
            self.left_panel, 
            text="🌸 START AEROGLIDE 🌸", 
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            height=45,
            command=self.toggle_touchpad,
            fg_color="#FF8DA1",
            text_color="#FFFFFF",
            hover_color="#FF6B8B"
        )
        self.start_btn.pack(side="bottom", fill="x", padx=25, pady=20)

        # Schedule constant UI background updates
        self.update_gui_loop()

    def toggle_touchpad(self):
        if not self.is_touchpad_running:
            # Start
            self.is_touchpad_running = True
            self.start_btn.configure(
                text="🌸 TERMINATE LINK 🌸", 
                fg_color="#B19FFB", 
                text_color="#FFFFFF", 
                hover_color="#9C85FB"
            )
            self.status_lbl.configure(text="SYSTEM ACTIVE", text_color="#3CB371")
            self.led_canvas.itemconfig(self.led_circle, fill="#FF5E84")
            
            # Start Processing Loop Thread
            self.loop_thread = threading.Thread(target=self.run_touchpad_loop)
            self.loop_thread.daemon = True
            self.loop_thread.start()
        else:
            # Stop
            self.is_touchpad_running = False
            self.start_btn.configure(
                text="🌸 START AEROGLIDE 🌸", 
                fg_color="#FF8DA1",
                text_color="#FFFFFF",
                hover_color="#FF6B8B"
            )
            self.status_lbl.configure(text="SYSTEM OFFLINE", text_color="#FF8DA1")
            self.led_canvas.itemconfig(self.led_circle, fill="#E6E6FA")
            self.mode_value.configure(text="INACTIVE", text_color="#FF8DA1")

    def run_touchpad_loop(self):
        """Threaded main processing loop for tracking and frame grabbing."""
        try:
            self.stream = VideoStream(src=0).start()
            self.engine = GestureEngine()
            
            # Synchronize sliders immediately
            self.on_settings_change()

            prev_time = time.time()
            frame_count = 0

            while self.is_touchpad_running:
                grabbed, frame = self.stream.read()
                if not grabbed or frame is None:
                    time.sleep(0.01)
                    continue

                # Flip horizontally to match mirror movement
                frame = cv2.flip(frame, 1)

                # Process hand tracking and gesture execution
                frame, mode = self.engine.process_frame(frame)
                
                self.current_mode = mode
                
                # Calculate real-time FPS
                frame_count += 1
                curr_time = time.time()
                elapsed = curr_time - prev_time
                if elapsed >= 1.0:
                    self.fps = int(frame_count / elapsed)
                    frame_count = 0
                    prev_time = curr_time

                # Display or hide camera window preview
                if self.show_cam_sw.get():
                    cv2.imshow("AeroGlide HUD Feed", frame)
                    # waitKey holds window refreshing (1ms is enough)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                else:
                    cv2.destroyAllWindows()
                    # Sleep slightly to prevent CPU consumption when preview is hidden
                    time.sleep(0.01)

        except Exception as e:
            print(f"Exception in gesture thread: {e}")
        finally:
            # Cleanup thread assets
            if self.stream:
                self.stream.stop()
            if self.engine:
                self.engine.release()
            cv2.destroyAllWindows()
            self.fps = 0

    def on_settings_change(self, *args):
        """Callback to update active gesture engine values dynamically when user slides or toggles UI."""
        # Read from GUI controls
        smooth_min = self.smooth_min_slider.get()
        smooth_max = self.smooth_max_slider.get()
        click_val = self.click_slider.get()
        sens_val = self.sens_slider.get()
        
        enable_zoom = self.enable_zoom_sw.get()
        enable_vol = self.enable_vol_sw.get()
        enable_drag = self.enable_drag_sw.get()

        # Update text labels
        self.smooth_min_lbl.configure(text=f"Fine Precision Smoothing: {smooth_min:.2f}")
        self.smooth_max_lbl.configure(text=f"Fast Motion Responsiveness: {smooth_max:.2f}")
        self.click_lbl.configure(text=f"Pinch Click Threshold: {click_val:.3f}")
        self.sens_lbl.configure(text=f"Cursor Speed / Sensitivity: {sens_val:.2f}x")

        # Propagate to Gesture Engine
        if self.engine:
            self.engine.update_settings(
                smoothing_min=smooth_min,
                smoothing_max=smooth_max,
                click_threshold=click_val,
                pointer_sensitivity=sens_val,
                enable_zoom=enable_zoom,
                enable_volume=enable_vol,
                enable_drag=enable_drag
            )

    def update_gui_loop(self):
        """Periodic GUI refresh timer running on main Tkinter thread."""
        if self.is_touchpad_running:
            # Display real-time state and FPS on diagnostics board
            self.fps_lbl.configure(text=f"Framerate: {self.fps} FPS")
            self.mode_value.configure(text=self.current_mode.upper())
            
            # Color code current mode for rapid cognitive visibility
            if self.current_mode in ["Left Clicking", "Right Clicking", "Dragging", "Double Clicked"]:
                self.mode_value.configure(text_color="#00FF80") # Green click
            elif self.current_mode in ["Scroll Mode", "Zoom Mode", "Zooming In", "Zooming Out", "Volume Mode"]:
                self.mode_value.configure(text_color="#00DFFF") # Cyan action
            elif self.current_mode == "Cursor Moving":
                self.mode_value.configure(text_color="#FFFF00") # Yellow motion
            else:
                self.mode_value.configure(text_color="#E0E0E0") # Grey idle
        
        # Schedule next update in 50ms
        self.after(50, self.update_gui_loop)

    def destroy(self):
        # Force cleanup on close
        self.is_touchpad_running = False
        if self.stream:
            self.stream.stop()
        cv2.destroyAllWindows()
        super().destroy()

if __name__ == "__main__":
    app = AeroGlideApp()
    app.mainloop()
