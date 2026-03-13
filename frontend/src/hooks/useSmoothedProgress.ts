import { useState, useEffect, useRef } from 'react';

/**
 * Smooths progress updates to avoid jumps and freezes.
 * - Large jumps (>10%) are animated incrementally (1% per 100ms)
 * - If no update for 5s during active phases, interpolates +0.5%/s (capped at 95%)
 * - Resets interpolation on each real update
 */
export function useSmoothedProgress(
  rawProgress: number,
  isActive: boolean
): number {
  const [displayProgress, setDisplayProgress] = useState(rawProgress);
  const lastRawRef = useRef(rawProgress);
  const lastUpdateTimeRef = useRef(Date.now());
  const animationRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const interpolationRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Cleanup helper
  const clearTimers = () => {
    if (animationRef.current) {
      clearInterval(animationRef.current);
      animationRef.current = null;
    }
    if (interpolationRef.current) {
      clearInterval(interpolationRef.current);
      interpolationRef.current = null;
    }
  };

  // Handle raw progress changes
  useEffect(() => {
    const prevRaw = lastRawRef.current;
    lastRawRef.current = rawProgress;
    lastUpdateTimeRef.current = Date.now();

    // Clear any existing interpolation since we got a real update
    if (interpolationRef.current) {
      clearInterval(interpolationRef.current);
      interpolationRef.current = null;
    }

    const jump = rawProgress - prevRaw;

    if (jump > 10) {
      // Large jump: animate incrementally
      if (animationRef.current) {
        clearInterval(animationRef.current);
      }

      let current = prevRaw;
      animationRef.current = setInterval(() => {
        current += 1;
        if (current >= rawProgress) {
          current = rawProgress;
          if (animationRef.current) {
            clearInterval(animationRef.current);
            animationRef.current = null;
          }
        }
        setDisplayProgress(current);
      }, 100);
    } else {
      // Small jump or decrease: apply directly
      if (animationRef.current) {
        clearInterval(animationRef.current);
        animationRef.current = null;
      }
      setDisplayProgress(rawProgress);
    }
  }, [rawProgress]);

  // Interpolation: if no update for 5s during active state, add 0.5%/s capped at 95%
  useEffect(() => {
    if (!isActive) {
      clearTimers();
      return;
    }

    // Check every second if we should interpolate
    interpolationRef.current = setInterval(() => {
      const elapsed = Date.now() - lastUpdateTimeRef.current;
      if (elapsed >= 5000) {
        setDisplayProgress((prev) => {
          const next = prev + 0.5;
          return next > 95 ? 95 : next;
        });
      }
    }, 1000);

    return () => {
      if (interpolationRef.current) {
        clearInterval(interpolationRef.current);
        interpolationRef.current = null;
      }
    };
  }, [isActive]);

  // Cleanup on unmount
  useEffect(() => {
    return clearTimers;
  }, []);

  // Reset when not active
  useEffect(() => {
    if (!isActive) {
      setDisplayProgress(rawProgress);
    }
  }, [isActive, rawProgress]);

  return displayProgress;
}
