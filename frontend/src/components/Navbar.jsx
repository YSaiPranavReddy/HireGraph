import { Link, useNavigate } from 'react-router-dom'
import { useAuth, UserButton } from '@clerk/clerk-react'
import './Navbar.css'

export default function Navbar({ transparent = false }) {
  const { isSignedIn } = useAuth()
  const navigate = useNavigate()

  return (
    <nav className="navbar">
      <Link to="/" className="navbar-logo">
        <img src="/hiregraph.png" alt="HireGraph Logo" style={{ height: '40px', width: 'auto' }} />
      </Link>

      <div className="navbar-right">
        <div className="nav-links">
          <Link to="#about" className="nav-link">About</Link>
        </div>

        <div className="navbar-actions">
          {isSignedIn ? (
            <>
              <button className="btn-white-pill" onClick={() => navigate('/dashboard')}>
                Dashboard
              </button>
              <UserButton afterSignOutUrl="/" />
            </>
          ) : (
            <>
              <Link to="/sign-in" className="nav-link">Sign In</Link>
              <Link to="/sign-up" className="btn-white-pill">Sign up</Link>
            </>
          )}
        </div>
      </div>
    </nav>
  )
}
