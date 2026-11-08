import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api';
import { useQueueManager } from '../hooks/useQueueManager';
import type { JobProgressUpdate } from '../types';

const completedUpdate: JobProgressUpdate = {
  job_id: 'route-job',
  status: 'completed',
  progress: 100,
  download_ready: true,
};

describe('useQueueManager automatic download', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('downloads a route item automatically after processing completes', async () => {
    vi.spyOn(api, 'startDownload').mockResolvedValue({
      job_id: 'route-job',
      message: 'Download started',
      status: 'queued',
    });
    vi.spyOn(api, 'subscribeToProgress').mockImplementation((_jobId, callbacks) => {
      queueMicrotask(() => callbacks.onComplete(completedUpdate));
      return vi.fn();
    });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    const { result } = renderHook(() => useQueueManager());

    act(() => {
      result.current.addToQueue([
        {
          url: 'https://x.com/user/status/123456',
          platform: 'twitter',
          isValid: true,
        },
      ], '480p', { autoDownload: true });
    });

    await waitFor(() => {
      expect(api.startDownload).toHaveBeenCalledWith({
        url: 'https://x.com/user/status/123456',
        quality: '480p',
      });
      expect(click).toHaveBeenCalledOnce();
    });
  });

  it('records when processing started and finished', async () => {
    vi.spyOn(api, 'startDownload').mockResolvedValue({
      job_id: 'route-job',
      message: 'Download started',
      status: 'queued',
    });
    vi.spyOn(api, 'subscribeToProgress').mockImplementation((_jobId, callbacks) => {
      queueMicrotask(() => callbacks.onComplete(completedUpdate));
      return vi.fn();
    });

    const { result } = renderHook(() => useQueueManager());

    act(() => {
      result.current.addToQueue([
        { url: 'https://x.com/user/status/123456', platform: 'twitter', isValid: true },
      ], '480p');
    });

    await waitFor(() => {
      expect(result.current.items[0].status).toBe('completed');
    });

    const item = result.current.items[0];
    expect(item.startedAt).toBeTypeOf('number');
    expect(item.completedAt).toBeTypeOf('number');
    expect(item.completedAt!).toBeGreaterThanOrEqual(item.startedAt!);
    expect(item.startedAt!).toBeGreaterThanOrEqual(item.addedAt);
  });
});
