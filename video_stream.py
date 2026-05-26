import cv2
import threading
import time

class VideoStream:
    def __init__(self, src=0, width=640, height=480):
        self.stream = None
        self.grabbed = False
        self.frame = None
        self.started = False
        self.read_lock = threading.Lock()
        self.is_valid = False

        try:
            self.stream = cv2.VideoCapture(src)
            if self.stream is None or not self.stream.isOpened():
                self.is_valid = False
                return
            
            self.stream.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.stream.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            (self.grabbed, self.frame) = self.stream.read()
            if not self.grabbed or self.frame is None:
                self.is_valid = False
            else:
                self.is_valid = True
        except Exception as e:
            print(f"Error initializing VideoStream: {e}")
            self.is_valid = False

    def start(self):
        if not self.is_valid:
            return self
        if self.started:
            return self
        self.started = True
        self.thread = threading.Thread(target=self.update, args=())
        self.thread.daemon = True
        self.thread.start()
        return self

    def update(self):
        while self.started:
            if self.stream is None or not self.stream.isOpened():
                with self.read_lock:
                    self.grabbed = False
                break
            (grabbed, frame) = self.stream.read()
            if not grabbed:
                with self.read_lock:
                    self.grabbed = False
                break
            with self.read_lock:
                self.grabbed = grabbed
                self.frame = frame
            # Short sleep to prevent excessive CPU consumption in the frame grabber thread
            time.sleep(0.01)

    def read(self):
        with self.read_lock:
            if self.frame is not None:
                return self.grabbed, self.frame.copy()
            return self.grabbed, None

    def stop(self):
        self.started = False
        if hasattr(self, 'thread'):
            self.thread.join(timeout=1.0)
        if self.stream and self.stream.isOpened():
            self.stream.release()
