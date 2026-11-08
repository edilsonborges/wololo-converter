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

describe('useQueueManager music links', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('replaces a music link with one MP3 item per found track and a failed item per missing one', async () => {
    let resolveCall!: (value: Awaited<ReturnType<typeof api.resolveMusicLink>>) => void;
    vi.spyOn(api, 'resolveMusicLink').mockImplementation(
      () => new Promise((resolve) => { resolveCall = resolve; }),
    );
    const start = vi.spyOn(api, 'startDownload').mockResolvedValue({
      job_id: 'job-1', message: 'Download started', status: 'queued',
    });
    vi.spyOn(api, 'subscribeToProgress').mockImplementation(() => vi.fn());

    const { result } = renderHook(() => useQueueManager());

    act(() => {
      result.current.addMusicLinks(['https://artlist.io/royalty-free-music/album/dale-candela/1000047']);
    });
    expect(result.current.items).toHaveLength(1);
    expect(result.current.items[0].status).toBe('resolving');

    await act(async () => {
      resolveCall({
        album: 'Dale Candela',
        tracks: [
          { title: 'Dale Candela', artist: 'djnoone', video_url: 'https://www.youtube.com/watch?v=p63v0n73aMg' },
          {
            title: 'Dale Candela - Instrumental version',
            artist: 'djnoone',
            source_url: 'https://artlist.io/royalty-free-music/song/dale-candela-instrumental-version/6000144',
            video_url: null,
          },
        ],
      });
    });

    await waitFor(() => {
      expect(start).toHaveBeenCalledWith({ url: 'https://www.youtube.com/watch?v=p63v0n73aMg', quality: 'mp3' });
    });
    const [found, missing] = result.current.items;
    expect(found.label).toBe('djnoone - Dale Candela');
    expect(missing).toMatchObject({
      status: 'failed',
      musicLink: true,
      url: 'https://artlist.io/royalty-free-music/song/dale-candela-instrumental-version/6000144',
      error: 'No matching video found on YouTube',
    });
  });

  it('retrying a missing track resolves only that song again', async () => {
    const resolve = vi.spyOn(api, 'resolveMusicLink')
      .mockResolvedValueOnce({
        album: 'Song',
        tracks: [{ title: 'Song', artist: 'A', source_url: 'https://artlist.io/royalty-free-music/song/song/1', video_url: null }],
      })
      .mockRejectedValueOnce(new Error('The music page is temporarily blocking access, try again in a minute'));

    const { result } = renderHook(() => useQueueManager());
    act(() => {
      result.current.addMusicLinks(['https://artlist.io/royalty-free-music/song/song/1']);
    });
    await waitFor(() => expect(result.current.items[0].status).toBe('failed'));

    act(() => {
      result.current.retryItem(result.current.items[0].id);
    });
    await waitFor(() => expect(result.current.items[0].error).toMatch(/blocking access/));

    expect(resolve).toHaveBeenLastCalledWith('https://artlist.io/royalty-free-music/song/song/1');
    expect(result.current.items).toHaveLength(1);
  });
});
