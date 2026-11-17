import { act, fireEvent, render, renderHook, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api';
import { QualitySelector } from '../components/QualitySelector';
import { useQueueManager } from '../hooks/useQueueManager';
import { checkSize, formatSize } from '../size';
import { mediaKey, parseURLs } from '../urlParser';

const GB = 1_000_000_000;
// Estimates of the 10-hour video from issue #11
const preview = {
  sizes: { '1080p': 6.9 * GB, '720p': 2.3 * GB, '480p': 1.7 * GB, '360p': 1.3 * GB, mp3: 1.44 * GB },
  size_limit: 4 * GB,
};

describe('mediaKey and pasted duplicates', () => {
  it('gives the same key to every way of writing a YouTube link', () => {
    const keys = [
      'https://youtu.be/XIhEPwTMjWk',
      'https://www.youtube.com/watch?v=XIhEPwTMjWk&t=30',
      'youtube.com/watch?feature=share&v=XIhEPwTMjWk',
      'https://m.youtube.com/shorts/XIhEPwTMjWk?si=abc',
    ].map((url) => mediaKey(url));
    expect(new Set(keys)).toEqual(new Set(['youtube:XIhEPwTMjWk']));
    expect(mediaKey('https://www.instagram.com/reels/Abc/')).toBe(mediaKey('https://instagram.com/p/Abc'));
  });

  it('keeps one entry per video and counts the rest', () => {
    const text = [
      'https://youtu.be/XIhEPwTMjWk',
      'https://www.youtube.com/watch?v=XIhEPwTMjWk&t=30',
      'https://youtu.be/XIhEPwTMjWk',
      'https://youtu.be/dQw4w9WgXcQ',
    ].join('\n');
    const parsed = parseURLs(text);
    expect(parsed.map((p) => p.url)).toEqual(['https://youtu.be/XIhEPwTMjWk', 'https://youtu.be/dQw4w9WgXcQ']);
    expect(parsed[0].duplicates).toBe(2);
    expect(parsed[1].duplicates).toBeUndefined();
  });
});

describe('size estimates', () => {
  it('formats decimal sizes', () => {
    expect(formatSize(6.9 * GB)).toBe('6.9 GB');
    expect(formatSize(4 * GB)).toBe('4 GB');
    expect(formatSize(450_000_000)).toBe('450 MB');
  });

  it('flags a quality over the limit and suggests one that fits', () => {
    expect(checkSize(preview, '720p')).toEqual({ size: 2.3 * GB, tooLarge: false });
    const check = checkSize(preview, '1080p');
    expect(check.tooLarge).toBe(true);
    expect(check.suggestion).toEqual({ quality: '720p', size: 2.3 * GB });
    expect(check.message).toBe('Too large: ~6.9 GB at 1080p (limit 4 GB). 720p fits (~2.3 GB).');
    expect(checkSize(null, '1080p').tooLarge).toBe(false);
  });

  it('shows sizes in the quality selector and disables the ones over the limit', () => {
    render(
      <QualitySelector selectedQuality="480p" onQualityChange={vi.fn()} sizes={preview.sizes} sizeLimit={preview.size_limit} />,
    );
    expect(screen.getByText('~2.3 GB')).toBeInTheDocument();
    const button1080 = screen.getByText('1080p').closest('button')!;
    expect(button1080).toBeDisabled();
    expect(button1080).toHaveAttribute('title', 'Too large (~6.9 GB, limit 4 GB)');
    expect(screen.getByText('720p').closest('button')).not.toBeDisabled();
  });
});

describe('useQueueManager limits', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    // Keep items pending: nothing should start in these tests
    vi.spyOn(api, 'startDownload').mockReturnValue(new Promise(() => {}));
  });

  const link = (url: string) => ({ url, platform: 'youtube', platformInfo: null, isValid: true });

  it('skips links already in the queue and reports them', () => {
    const { result } = renderHook(() => useQueueManager());
    let first!: ReturnType<typeof result.current.addToQueue>;
    act(() => {
      first = result.current.addToQueue([link('https://youtu.be/XIhEPwTMjWk')], '1080p');
    });
    expect(first).toEqual({ added: 1, duplicates: 0, duplicateIds: [] });

    let again!: ReturnType<typeof result.current.addToQueue>;
    act(() => {
      again = result.current.addToQueue(
        [link('https://www.youtube.com/watch?v=XIhEPwTMjWk&t=9'), link('https://youtu.be/dQw4w9WgXcQ')],
        '1080p',
      );
    });
    expect(again.added).toBe(1);
    expect(again.duplicates).toBe(1);
    expect(again.duplicateIds).toEqual([result.current.items[0].id]);

    // Another quality of the same video is a different download
    act(() => {
      result.current.addToQueue([link('https://youtu.be/XIhEPwTMjWk')], 'mp3');
    });
    expect(result.current.items).toHaveLength(3);
  });

  it('adds a too-large video as blocked and switches it to a quality that fits', () => {
    const { result } = renderHook(() => useQueueManager());
    act(() => {
      result.current.addToQueue([link('https://youtu.be/XIhEPwTMjWk')], '1080p', { preview });
    });
    const item = result.current.items[0];
    expect(item.status).toBe('failed');
    expect(item.error).toBe('Too large: ~6.9 GB at 1080p (limit 4 GB). 720p fits (~2.3 GB).');
    expect(item.suggestedQuality).toBe('720p');
    expect(api.startDownload).not.toHaveBeenCalled();

    act(() => {
      result.current.switchQuality(item.id, '720p');
    });
    expect(result.current.items[0]).toMatchObject({ quality: '720p', error: undefined });
    expect(api.startDownload).toHaveBeenCalledWith({ url: 'https://youtu.be/XIhEPwTMjWk', quality: '720p' });
  });

  it('a failed item does not block adding the video again', () => {
    const { result } = renderHook(() => useQueueManager());
    act(() => {
      result.current.addToQueue([link('https://youtu.be/XIhEPwTMjWk')], '1080p', { preview });
    });
    let again!: ReturnType<typeof result.current.addToQueue>;
    act(() => {
      again = result.current.addToQueue([link('https://youtu.be/XIhEPwTMjWk')], '1080p');
    });
    expect(again.added).toBe(1);
  });
});

describe('queue item size warning', () => {
  it('shows the estimate and a switch button on a too-large item', async () => {
    const { QueueManager } = await import('../components/QueueManager');
    const onSwitch = vi.fn();
    render(
      <QueueManager
        items={[{
          id: 'a', url: 'https://youtu.be/XIhEPwTMjWk', platform: 'youtube', quality: '1080p',
          status: 'failed', addedAt: 0, estimatedSize: 6.9 * GB, suggestedQuality: '720p',
          error: 'Too large: ~6.9 GB at 1080p (limit 4 GB). 720p fits (~2.3 GB).',
        }]}
        config={{ processingMode: 'sequential', maxConcurrent: 2 }}
        onConfigChange={vi.fn()} onReorder={vi.fn()} onRemove={vi.fn()} onCancel={vi.fn()}
        onRetry={vi.fn()} onSwitchQuality={onSwitch} onDownload={vi.fn()} onExtractAudio={vi.fn()}
        extractingAudio={new Set()} onClearCompleted={vi.fn()}
      />,
    );
    expect(screen.getByText('~6.9 GB')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Switch to 720p' }));
    expect(onSwitch).toHaveBeenCalledWith('a', '720p');
  });
});
