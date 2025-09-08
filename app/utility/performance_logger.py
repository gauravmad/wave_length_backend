# app/utils/performance_logger.py

import time
from typing import Dict


class PerformanceLogger:
    """Utility class for logging performance timings"""
    
    def __init__(self):
        self.start_time = time.perf_counter()
        self.timings: Dict[str, float] = {}
    
    def log_step(self, step_name: str) -> None:
        """Log a performance step"""
        elapsed = time.perf_counter() - self.start_time
        self.timings[step_name] = round(elapsed, 3)
        print(f"[⏱️] {step_name} completed in {elapsed:.3f} sec")
        self.start_time = time.perf_counter()
    
    def get_timings(self) -> Dict[str, float]:
        """Get all recorded timings"""
        return self.timings.copy()
    
    def reset(self) -> None:
        """Reset the timer"""
        self.start_time = time.perf_counter()
        self.timings.clear()