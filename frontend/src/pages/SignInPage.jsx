import { useState } from 'react';
import { useSignIn, useAuth } from '@clerk/clerk-react';
import { Link, useNavigate, Navigate } from 'react-router-dom';
import './AuthPages.css';

export default function SignInPage() {
  const { isSignedIn } = useAuth();
  const { isLoaded, signIn, setActive } = useSignIn();
  const [emailAddress, setEmailAddress] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();

  // Already logged in → send straight to dashboard
  if (isSignedIn) {
    return <Navigate to="/dashboard" replace />;
  }

  const handleGoogle = async () => {
    if (!isLoaded) return;
    try {
      await signIn.authenticateWithRedirect({
        strategy: 'oauth_google',
        redirectUrl: `${window.location.origin}/sso-callback`,
        redirectUrlComplete: '/dashboard',
      });
    } catch (err) {
      setError(err.errors?.[0]?.longMessage || err.message || 'Google sign-in failed.');
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!isLoaded) return;
    setError('');
    setIsLoading(true);
    
    try {
      const result = await signIn.create({
        identifier: emailAddress,
        password,
      });
      
      if (result.status === 'complete') {
        await setActive({ session: result.createdSessionId });
        navigate('/dashboard');
      } else {
        setError('Additional verification is required.');
      }
    } catch (err) {
      setError(err.errors?.[0]?.longMessage || err.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <Link to="/" className="auth-top-logo-wrap">
        <img src="/hiregraph.png" alt="HireGraph" className="auth-top-logo" />
      </Link>
      
      <div className="auth-container">
        <h1 className="auth-title">Sign In to HireGraph</h1>
        
        <div className="auth-social-grid">
          <button type="button" onClick={handleGoogle} className="auth-social-btn google">
            <svg viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
            Google
          </button>
        </div>

        <div className="auth-divider">or</div>

        {error && <div className="auth-error">{error}</div>}

        <form onSubmit={submit}>
          <div className="auth-form-group">
            <label className="auth-label">Email</label>
            <input 
              type="email" 
              className="auth-input" 
              value={emailAddress}
              onChange={(e) => setEmailAddress(e.target.value)}
              placeholder="your@email.com"
              required 
            />
          </div>
          <div className="auth-form-group">
            <label className="auth-label">Password</label>
            <input 
              type={showPassword ? "text" : "password"} 
              className="auth-input" 
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="correct horse battery staple"
              required 
            />
            <button 
              type="button" 
              className="auth-password-eye"
              onClick={() => setShowPassword(!showPassword)}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                {showPassword ? (
                  <>
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
                    <line x1="1" y1="1" x2="23" y2="23"></line>
                  </>
                ) : (
                  <>
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                    <circle cx="12" cy="12" r="3"></circle>
                  </>
                )}
              </svg>
            </button>
          </div>
          
          <button type="submit" className="auth-submit-btn" disabled={isLoading || !isLoaded}>
            {isLoading ? 'Signing in...' : 'Sign in'}
          </button>
        </form>

        <div className="auth-links">
          <div>Need an account? <Link to="/sign-up" className="auth-link">Sign up</Link></div>
          <div>Forgot your password? <Link to="#" className="auth-link">Reset it</Link></div>
        </div>
      </div>
    </div>
  );
}
