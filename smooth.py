import math

class AdaptiveSmoother:
    def __init__(self, alpha_min=0.15, alpha_max=0.85, v_scale=20.0):
        """
        Adaptive Exponential Smoother.
        :param alpha_min: Smoothing factor for slow/static movements (higher smoothing, lower jitter)
        :param alpha_max: Smoothing factor for fast movements (lower smoothing, lower latency)
        :param v_scale: Velocity scaling factor to transition between alpha_min and alpha_max
        """
        self.alpha_min = alpha_min
        self.alpha_max = alpha_max
        self.v_scale = v_scale
        
        self.prev_x = None
        self.prev_y = None

    def reset(self):
        self.prev_x = None
        self.prev_y = None

    def smooth(self, target_x, target_y):
        """
        Applies adaptive exponential smoothing based on current velocity.
        """
        if self.prev_x is None or self.prev_y is None:
            self.prev_x = target_x
            self.prev_y = target_y
            return target_x, target_y

        # Calculate distance (velocity) from previous smoothed position
        dx = target_x - self.prev_x
        dy = target_y - self.prev_y
        velocity = math.hypot(dx, dy)

        # Adaptive alpha: higher speed -> larger alpha -> less smoothing, lower latency
        #                  lower speed -> smaller alpha -> more smoothing, less jitter
        alpha = self.alpha_min + (self.alpha_max - self.alpha_min) * (1.0 - math.exp(-velocity / self.v_scale))

        # Apply smoothing
        smoothed_x = alpha * target_x + (1.0 - alpha) * self.prev_x
        smoothed_y = alpha * target_y + (1.0 - alpha) * self.prev_y

        self.prev_x = smoothed_x
        self.prev_y = smoothed_y

        return smoothed_x, smoothed_y
