import React, { Suspense, lazy } from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

// Separate pages load on demand so the downloader stays light
const StatusPage = lazy(() => import('./pages/StatusPage'))
const AdminLogin = lazy(() => import('./pages/AdminLogin'))
const AdminPage = lazy(() => import('./pages/AdminPage'))

function Root() {
  const path = window.location.pathname.replace(/\/+$/, '') || '/'
  if (path === '/status') return <StatusPage />
  if (path === '/login') return <AdminLogin />
  if (path === '/admin') return <AdminPage />
  return <App />
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Suspense fallback={null}>
      <Root />
    </Suspense>
  </React.StrictMode>,
)
