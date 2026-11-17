import { useEffect, useState, type FormEvent } from 'react';
import { adminApi, UnauthorizedError } from '../adminApi';

export default function AdminLogin() {
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    document.title = 'Sign in · Wololo Converter';
    // Already signed in: go straight to the dashboard
    let active = true;
    adminApi
      .me()
      .then(() => active && window.location.replace('/admin'))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await adminApi.login(password);
      window.location.assign('/admin');
    } catch (e) {
      setError(
        e instanceof UnauthorizedError
          ? 'Wrong password.'
          : e instanceof Error && e.message === 'Not Found'
            ? 'The admin view is not enabled on this server.'
            : e instanceof Error
              ? e.message
              : 'Could not sign in.',
      );
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface-secondary flex items-center justify-center px-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-5">
        <div className="flex items-center gap-3">
          <img src="/wololo-left.png" alt="" className="w-10 h-10 object-contain" />
          <div>
            <h1 className="text-lg font-semibold text-text-primary">Wololo admin</h1>
            <p className="text-sm text-text-tertiary">Sign in to see downloads and server usage.</p>
          </div>
        </div>
        <label className="block">
          <span className="text-sm font-medium text-text-secondary">Password</span>
          <input
            type="password"
            className="input-field mt-1"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            autoFocus
            required
          />
        </label>
        {error && (
          <p role="alert" className="text-sm text-error-text">
            {error}
          </p>
        )}
        <button type="submit" className="btn-primary w-full" disabled={busy || !password}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  );
}
