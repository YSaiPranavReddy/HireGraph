import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from '@clerk/clerk-react'
import Landing from './pages/Landing'
import SignInPage from './pages/SignInPage'
import SignUpPage from './pages/SignUpPage'
import SSOCallback from './pages/SSOCallback'
import Dashboard from './pages/Dashboard'

function ProtectedRoute({ children }) {
  const { isSignedIn, isLoaded } = useAuth()
  if (!isLoaded) return <div className="loading-screen"><div className="spinner" /></div>
  if (!isSignedIn) return <Navigate to="/sign-in" replace />
  return children
}

export default function App() {
  return (
    <Routes>
      <Route path="/"         element={<Landing />} />
      <Route path="/sign-in/*"  element={<SignInPage />} />
      <Route path="/sign-up/*"  element={<SignUpPage />} />
      <Route path="/sso-callback" element={<SSOCallback />} />
      <Route path="/dashboard" element={
        <ProtectedRoute>
          <Dashboard />
        </ProtectedRoute>
      } />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
