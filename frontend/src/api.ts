import type {
  DownloadRequest,
  DownloadStartResponse,
  URLValidationResponse,
  HealthResponse,
  JobProgressUpdate,
  PreviewResponse,
  ResolveResponse,
  JobResponse,
  JobStatus,
} from './types';

const API_BASE = '/api';

const TERMINAL_STATUSES: JobStatus[] = ['completed', 'failed', 'cancelled'];

/** Map the job record returned by GET /api/jobs/{id} to a progress update. */
export function jobToProgressUpdate(job: JobResponse): JobProgressUpdate {
  return {
    job_id: job.id,
    status: job.status,
    progress: job.progress ?? 0,
    speed: job.speed ?? undefined,
    eta: job.eta ?? undefined,
    current_stage: job.current_stage ?? undefined,
    title: job.title ?? undefined,
    error_message: job.error_message ?? undefined,
    download_ready: job.status === 'completed',
  };
}

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = 'An error occurred';
    try {
      const data = await response.json();
      message = (Array.isArray(data.detail) ? data.detail.map((d: { msg: string }) => d.msg).join(', ') : data.detail) || data.error || message;
    } catch {
      // Ignore JSON parse errors
    }
    throw new ApiError(response.status, message);
  }
  return response.json();
}

export const api = {
  /**
   * Check API health
   */
  async health(): Promise<HealthResponse> {
    const response = await fetch(`${API_BASE}/health`);
    return handleResponse<HealthResponse>(response);
  },

  /**
   * Validate a URL before downloading
   */
  async validateUrl(url: string): Promise<URLValidationResponse> {
    const response = await fetch(`${API_BASE}/validate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    return handleResponse<URLValidationResponse>(response);
  },

  /**
   * Fetch video preview/metadata
   */
  async fetchPreview(url: string): Promise<PreviewResponse> {
    const response = await fetch(`${API_BASE}/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    return handleResponse<PreviewResponse>(response);
  },

  /**
   * Resolve a music page link into the matching YouTube video of each track
   */
  async resolveMusicLink(url: string): Promise<ResolveResponse> {
    const response = await fetch(`${API_BASE}/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    return handleResponse<ResolveResponse>(response);
  },

  /**
   * Start a download job
   */
  async startDownload(request: DownloadRequest): Promise<DownloadStartResponse> {
    const response = await fetch(`${API_BASE}/download`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
    return handleResponse<DownloadStartResponse>(response);
  },

  /**
   * Cancel a download job
   */
  async cancelJob(jobId: string): Promise<void> {
    const response = await fetch(`${API_BASE}/jobs/${jobId}`, {
      method: 'DELETE',
    });
    if (!response.ok) {
      throw new ApiError(response.status, 'Failed to cancel job');
    }
  },

  /**
   * Get download URL for a completed job
   */
  getDownloadUrl(jobId: string): string {
    return `${API_BASE}/jobs/${jobId}/download`;
  },

  /**
   * Extract audio (MP3) from a completed video download
   */
  async extractAudio(jobId: string): Promise<{ filename: string; file_size: number }> {
    const response = await fetch(`${API_BASE}/jobs/${jobId}/extract-audio`, {
      method: 'POST',
    });
    return handleResponse(response);
  },

  /**
   * Get audio download URL for a completed extraction
   */
  getAudioDownloadUrl(jobId: string): string {
    return `${API_BASE}/jobs/${jobId}/download-audio`;
  },

  /**
   * Subscribe to job progress updates via SSE
   */
  subscribeToProgress(
    jobId: string,
    callbacks: {
      onProgress: (update: JobProgressUpdate) => void;
      onComplete: (update: JobProgressUpdate) => void;
      onError: (error: Error) => void;
    },
    options: { pollIntervalMs?: number; maxPollFailures?: number } = {}
  ): () => void {
    // Live updates come over SSE. Long jobs (e.g. a 2 h live replay) outlast
    // that connection: mobile browsers drop it when the tab is in the
    // background and proxies close it. The job keeps running on the server, so
    // when the stream drops we poll the job's status instead of failing.
    const pollIntervalMs = options.pollIntervalMs ?? 2000;
    const maxPollFailures = options.maxPollFailures ?? 300; // ~10 min offline
    let stopped = false;
    let polling = false;
    let pollTimer: ReturnType<typeof setTimeout> | undefined;
    let pollFailures = 0;

    const eventSource = new EventSource(`${API_BASE}/jobs/${jobId}/progress`);

    const stop = () => {
      stopped = true;
      eventSource.close();
      if (pollTimer) clearTimeout(pollTimer);
    };

    const finish = (update: JobProgressUpdate) => {
      if (stopped) return;
      stop();
      callbacks.onComplete(update);
    };

    const fail = (error: Error) => {
      if (stopped) return;
      stop();
      callbacks.onError(error);
    };

    const poll = async () => {
      if (stopped) return;
      try {
        const response = await fetch(`${API_BASE}/jobs/${jobId}`);
        if (response.status === 404) {
          fail(new Error('Job not found'));
          return;
        }
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const job = (await response.json()) as JobResponse;
        pollFailures = 0;
        const update = jobToProgressUpdate(job);
        if (TERMINAL_STATUSES.includes(job.status)) {
          finish(update);
          return;
        }
        if (!stopped) callbacks.onProgress(update);
      } catch {
        pollFailures += 1;
        if (pollFailures >= maxPollFailures) {
          fail(new Error('Connection lost'));
          return;
        }
      }
      if (!stopped) pollTimer = setTimeout(poll, pollIntervalMs);
    };

    eventSource.addEventListener('progress', (event) => {
      try {
        const update = JSON.parse((event as MessageEvent).data) as JobProgressUpdate;
        if (!stopped) callbacks.onProgress(update);
      } catch (e) {
        console.error('Failed to parse progress event:', e);
      }
    });

    eventSource.addEventListener('complete', (event) => {
      try {
        finish(JSON.parse((event as MessageEvent).data) as JobProgressUpdate);
      } catch (e) {
        console.error('Failed to parse complete event:', e);
        stop();
      }
    });

    eventSource.addEventListener('error', () => {
      eventSource.close();
      if (stopped || polling) return;
      polling = true;
      poll();
    });

    // Return cleanup function
    return stop;
  },
};

export { ApiError };
