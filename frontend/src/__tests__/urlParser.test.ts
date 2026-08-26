import { describe, expect, it } from 'vitest';
import { parseAutoDownloadRoute, parseURLs } from '../urlParser';

function route(pathname: string, search = '', hash = '') {
  return { pathname, search, hash };
}

describe('parseAutoDownloadRoute', () => {
  it('accepts a full source URL after the root and removes its query', () => {
    const result = parseAutoDownloadRoute(route(
      '/https://x.com/pardald3sign/status/2092425556650242194',
      '?s=48',
    ));

    expect(result).toMatchObject({
      url: 'https://x.com/pardald3sign/status/2092425556650242194',
      platform: 'twitter',
      isValid: true,
    });
  });

  it('adds HTTPS when the source protocol is omitted', () => {
    const result = parseAutoDownloadRoute(route(
      '/x.com/pardald3sign/status/2092425556650242194',
      '?s=48',
    ));

    expect(result?.url).toBe(
      'https://x.com/pardald3sign/status/2092425556650242194',
    );
  });

  it('accepts an encoded source URL', () => {
    const source = 'https://www.instagram.com/reel/ABC123/';
    const result = parseAutoDownloadRoute(route(`/${encodeURIComponent(source)}`));

    expect(result?.url).toBe(source);
    expect(result?.platform).toBe('instagram');
  });

  it.each([
    [
      '/https://m.youtube.com/watch',
      '?v=dQw4w9WgXcQ',
      'youtube',
      'https://youtu.be/dQw4w9WgXcQ',
    ],
    [
      '/www.instagram.com/share/reel/ABC123/',
      '',
      'instagram',
      'https://www.instagram.com/share/reel/ABC123/',
    ],
    [
      '/vt.tiktok.com/ZMkABC123/',
      '',
      'tiktok',
      'https://vt.tiktok.com/ZMkABC123/',
    ],
  ])('accepts shared %s routes', (pathname, search, platform, expectedUrl) => {
    const result = parseAutoDownloadRoute(route(pathname, search));

    expect(result).toMatchObject({
      url: expectedUrl,
      platform,
      isValid: true,
    });
  });

  it('repairs a protocol slash merged by a reverse proxy', () => {
    const result = parseAutoDownloadRoute(route(
      '/https:/x.com/user/status/123456',
    ));

    expect(result?.url).toBe('https://x.com/user/status/123456');
  });

  it('removes playback and tracking parameters from pasted URLs', () => {
    const [youtube, instagram] = parseURLs([
      'https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95&list=playlist',
      'https://www.instagram.com/reel/ABC123/?igsh=tracking#fragment',
    ].join('\n'));

    expect(youtube.url).toBe('https://youtu.be/dQw4w9WgXcQ');
    expect(instagram.url).toBe('https://www.instagram.com/reel/ABC123/');
  });

  it('ignores the app root and unsupported routes', () => {
    expect(parseAutoDownloadRoute(route('/'))).toBeNull();
    expect(parseAutoDownloadRoute(route('/assets/app.js'))).toBeNull();
    expect(parseAutoDownloadRoute(route('/example.com/video'))).toBeNull();
  });
});
