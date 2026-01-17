import type {
  DownloadRequest,
  DownloadStartResponse,
  URLValidationResponse,
  HealthResponse,
  JobProgressUpdate,
} from './types';

const API_BASE = '/api';

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
      message = data.detail || data.error || message;
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
   * Subscribe to job progress updates via SSE
   */
  subscribeToProgress(
    jobId: string,
    callbacks: {
      onProgress: (update: JobProgressUpdate) => void;
      onComplete: (update: JobProgressUpdate) => void;
      onError: (error: Error) => void;
    }
  ): () => void {
    const eventSource = new EventSource(`${API_BASE}/jobs/${jobId}/progress`);

    eventSource.addEventListener('progress', (event) => {
      try {
        const update = JSON.parse(event.data) as JobProgressUpdate;
        callbacks.onProgress(update);
      } catch (e) {
        console.error('Failed to parse progress event:', e);
      }
    });

    eventSource.addEventListener('complete', (event) => {
      try {
        const update = JSON.parse(event.data) as JobProgressUpdate;
        callbacks.onComplete(update);
      } catch (e) {
        console.error('Failed to parse complete event:', e);
      }
      eventSource.close();
    });

    eventSource.addEventListener('error', () => {
      callbacks.onError(new Error('Connection lost'));
      eventSource.close();
    });

    // Return cleanup function
    return () => {
      eventSource.close();
    };
  },
};

export { ApiError };
