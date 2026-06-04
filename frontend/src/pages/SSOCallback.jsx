import { AuthenticateWithRedirectCallback } from '@clerk/clerk-react';

export default function SSOCallback() {
  return (
    <div style={{ height: '100vh', backgroundColor: '#0b0b0b', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <AuthenticateWithRedirectCallback 
        signInFallbackRedirectUrl="/dashboard"
        signUpFallbackRedirectUrl="/dashboard"
      />
    </div>
  );
}
