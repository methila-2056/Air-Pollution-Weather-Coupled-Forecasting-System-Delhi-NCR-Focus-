import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import ErrorBoundary from './components/ErrorBoundary'
import { AuthProvider } from './auth/AuthContext'
import { startKeepWarm } from './api/warmup'
import App from './App'
import './index.css'

// Keep the (scale-to-zero) Render backend warm while a tab is open.
startKeepWarm()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <ErrorBoundary>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </ErrorBoundary>,
)
