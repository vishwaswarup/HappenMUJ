import { useEffect, useRef, useState } from 'react';

// Google Identity Services ("Sign in with Google"). It hands us an ID token (`credential`); the backend verifies it.
// The script is loaded on demand and only when the server says Google sign-in is configured.

interface GoogleId {
  initialize(o: { client_id: string; callback: (r: { credential: string }) => void }): void;
  renderButton(el: HTMLElement, o: Record<string, unknown>): void;
}
declare global {
  interface Window { google?: { accounts: { id: GoogleId } } }
}

const SRC = 'https://accounts.google.com/gsi/client';
let loader: Promise<void> | null = null;
function loadGoogle(): Promise<void> {
  if (window.google?.accounts?.id) return Promise.resolve();
  loader ??= new Promise<void>((resolve, reject) => {
    const s = document.createElement('script');
    s.src = SRC; s.async = true; s.defer = true;
    s.onload = () => resolve();
    s.onerror = () => { loader = null; reject(new Error('Google script blocked')); };
    document.head.appendChild(s);
  });
  return loader;
}

interface Props { clientId: string; onCredential: (credential: string) => void; text?: 'continue_with' | 'signin_with' | 'signup_with' }

export function GoogleButton({ clientId, onCredential, text = 'continue_with' }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const handler = useRef(onCredential);
  handler.current = onCredential;
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    loadGoogle().then(() => {
      if (cancelled || !box.current || !window.google) return;
      window.google.accounts.id.initialize({ client_id: clientId, callback: (r) => handler.current(r.credential) });
      window.google.accounts.id.renderButton(box.current, { type: 'standard', theme: 'outline', size: 'large', text, shape: 'rectangular', width: 320 });
    }).catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, [clientId, text]);

  if (failed) return <p className="field__hint">Google sign-in could not load (your browser or network may be blocking it). Use your email and password instead.</p>;
  return <div ref={box} className="google-btn" role="group" aria-label="Continue with Google" />;
}
