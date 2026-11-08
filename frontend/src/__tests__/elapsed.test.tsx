import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { formatElapsed } from '../elapsed';
import { ElapsedTime } from '../components/ElapsedTime';

describe('formatElapsed', () => {
  it('formats seconds', () => {
    expect(formatElapsed(0)).toBe('0s');
    expect(formatElapsed(42_900)).toBe('42s');
  });

  it('formats minutes with padded seconds', () => {
    expect(formatElapsed(185_000)).toBe('3m 05s');
  });

  it('formats hours with padded minutes', () => {
    expect(formatElapsed(3_720_000)).toBe('1h 02m');
  });

  it('never returns negative durations', () => {
    expect(formatElapsed(-5000)).toBe('0s');
  });
});

describe('ElapsedTime', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows the final duration when finished', () => {
    render(<ElapsedTime startedAt={1_000} endedAt={84_000} label="Took" />);
    expect(screen.getByTestId('elapsed-time')).toHaveTextContent('Took 1m 23s');
  });

  it('ticks while running', () => {
    vi.useFakeTimers();
    vi.setSystemTime(10_000);
    render(<ElapsedTime startedAt={10_000} />);
    expect(screen.getByTestId('elapsed-time')).toHaveTextContent('0s');

    act(() => {
      vi.advanceTimersByTime(3_000);
    });
    expect(screen.getByTestId('elapsed-time')).toHaveTextContent('3s');
  });
});
