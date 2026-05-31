import { SignIn } from '@clerk/clerk-react'
import { Link } from 'react-router-dom'
import './AuthPages.css'
import { dark } from '@clerk/themes'

export default function SignInPage() {
  return (
    <div className="auth-page">
      <Link to="/" style={{ textDecoration: 'none' }}>
        <img src="/hiregraph.png" alt="HireGraph" className="auth-top-logo" />
      </Link>
      
      <div className="auth-split-layout">
        <div className="auth-left-floating">
          <div className="auth-graphic-circle">
            <img src="/hire.png" alt="HireGraph Graphic" />
          </div>
          <h2 className="auth-welcome-title">Welcome to the world of HireGraph</h2>
          <p className="auth-welcome-subtitle">Hire smarter, not harder.<br />6 AI agents. Zero bias.</p>
        </div>
        
        <div className="auth-right-card">
          <div className="auth-form-wrapper">
            <Link to="/sign-up" className="auth-custom-link">Create an account &gt;</Link>
            <SignIn
              routing="path"
              path="/sign-in"
              signUpUrl="/sign-up"
              fallbackRedirectUrl="/dashboard"
              appearance={{
                baseTheme: dark,
                layout: {
                  socialButtonsPlacement: 'top',
                  helpPageUrl: '',
                  logoImageUrl: '',
                },
                variables: {
                  colorPrimary: '#61f2a3', // Bloom green flavor for the button
                  colorBackground: '#111115',
                  colorInputBackground: 'rgba(255,255,255,0.05)',
                  colorInputText: '#ffffff',
                  colorText: '#ffffff',
                  colorTextSecondary: 'rgba(255,255,255,0.6)',
                  borderRadius: '8px',
                  fontFamily: 'Plus Jakarta Sans, sans-serif',
                },
                elements: {
                  card: 'auth-clerk-card',
                  formButtonPrimary: 'btn btn-primary',
                  footerAction: { display: 'none' }, // Hides bottom link
                  footer: { display: 'none' }, // Hides "Secured by Clerk"
                  headerSubtitle: { display: 'none' },
                  headerTitle: { fontSize: '32px', textAlign: 'center' },
                }
              }}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
