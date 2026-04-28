import React, { useEffect, useState } from "react";
import {
  GoogleAuthProvider,
  onAuthStateChanged,
  signInWithPopup,
  setPersistence,
  browserLocalPersistence,
} from "firebase/auth";
import { auth, firebaseConfigReady } from "../firebase";

/**
 * Phase 1–2: Identity + token plumbing only.
 * - Backend remains authority.
 * - UI does not mutate evidence.
 * - This gate only ensures an authenticated Firebase user exists
 *   so downstream API calls can attach an ID token.
 */
export default function AuthGate({ children }) {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let unsub;
    (async () => {
      if (!firebaseConfigReady || !auth) {
        setError("Dashboard sign-in is not configured for this deployment.");
        setChecking(false);
        return;
      }

      // 1. Set persistence first
      await setPersistence(auth, browserLocalPersistence);

      // 2. Listen for auth state
      unsub = onAuthStateChanged(auth, (user) => {
        setUser(user || null);
        setChecking(false);
      });
    })();
    return () => unsub?.();
  }, []);

  const signIn = async () => {
    setError("");
    if (!auth) {
      setError("Dashboard sign-in is not configured for this deployment.");
      return;
    }
    const provider = new GoogleAuthProvider();
    try {
      await signInWithPopup(auth, provider);
    } catch (e) {
      setError(e?.message || "Sign-in failed");
    }
  };

  if (checking) {
    return (
      <div style={{ padding: 24, fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif" }}>
        Checking sign-in…
      </div>
    );
  }

  if (!user) {
    return (
      <div style={{ padding: 24, maxWidth: 560, margin: "0 auto", fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif" }}>
        <h2 style={{ margin: "0 0 12px" }}>Sign in</h2>
        <p style={{ margin: "0 0 16px" }}>
          Please sign in with Google to access the Intelligent Analyst dashboard.
        </p>
        <button
          type="button"
          onClick={signIn}
          disabled={!firebaseConfigReady || !auth}
          style={{
            padding: "10px 14px",
            borderRadius: 10,
            border: "1px solid #ddd",
            cursor: firebaseConfigReady && auth ? "pointer" : "not-allowed",
            background: "white",
            color: "#0f172a",
            opacity: firebaseConfigReady && auth ? 1 : 0.65,
            fontWeight: 600,
          }}
        >
          Continue with Google
        </button>
        {error ? <p style={{ marginTop: 12, color: "crimson" }}>{error}</p> : null}
      </div>
    );
  }

  return <>{children}</>;
}
