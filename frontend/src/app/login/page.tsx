"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Ghost, Key, Shield, Copy, Check, Clock } from "lucide-react";
import { setApiKey, isLiveKey, isTestKey } from "@/lib/api";

type AuthTab = "apikey" | "signature";

export default function LoginPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<AuthTab>("apikey");

  return (
    <div className="min-h-screen bg-gb-bg flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <Ghost className="w-16 h-16 text-gb-accent mx-auto mb-4" />
          <h1 className="font-heading text-3xl font-bold text-gb-text-primary">
            GhostBill
          </h1>
          <p className="text-gb-text-secondary mt-2">
            Monero Payment Gateway
          </p>
        </div>

        {/* Login card */}
        <div className="gb-card">
          {/* Tab selector */}
          <div className="flex mb-6 border-b border-gb-border">
            <button
              onClick={() => setActiveTab("apikey")}
              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === "apikey"
                  ? "border-gb-accent text-gb-accent"
                  : "border-transparent text-gb-text-secondary hover:text-gb-text-primary"
              }`}
            >
              <Key className="w-4 h-4" />
              API Key
            </button>
            <button
              onClick={() => setActiveTab("signature")}
              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === "signature"
                  ? "border-gb-accent text-gb-accent"
                  : "border-transparent text-gb-text-secondary hover:text-gb-text-primary"
              }`}
            >
              <Shield className="w-4 h-4" />
              Monero Signature
            </button>
          </div>

          {activeTab === "apikey" ? (
            <ApiKeyLogin router={router} />
          ) : (
            <SignatureLogin router={router} />
          )}
        </div>
      </div>
    </div>
  );
}

/* ─── API Key Login Tab ──────────────────────────────────────────────────── */

function ApiKeyLogin({ router }: { router: ReturnType<typeof useRouter> }) {
  const [key, setKey] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const isValidFormat = isLiveKey(key) || isTestKey(key);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!isValidFormat) {
      setError("Invalid key format. Must start with gb_live_ or gb_test_");
      return;
    }

    setLoading(true);

    try {
      const response = await fetch("/api/merchants/me", {
        headers: {
          Authorization: `Bearer ${key}`,
          "Content-Type": "application/json",
        },
      });

      if (response.status === 401) {
        setError("Invalid API key. Check your key and try again.");
        return;
      }

      if (!response.ok) {
        setError(`Server error (${response.status}). Try again later.`);
        return;
      }

      const merchant = await response.json();

      if (!merchant.id) {
        setError("Unexpected response. Please try again.");
        return;
      }

      setApiKey(key);
      router.push("/dashboard");
    } catch {
      setError("Connection failed. Is the backend running?");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <form onSubmit={handleLogin} className="space-y-4">
        <div>
          <label
            htmlFor="apiKey"
            className="block text-sm font-medium text-gb-text-secondary mb-2"
          >
            API Key
          </label>
          <input
            id="apiKey"
            type="password"
            value={key}
            onChange={(e) => setKey(e.target.value.trim())}
            placeholder="gb_live_... or gb_test_..."
            className="gb-input w-full font-mono text-sm"
            autoFocus
            autoComplete="off"
            spellCheck={false}
          />
        </div>

        {/* Key type indicator */}
        {key.length > 3 && (
          <div className="flex items-center gap-2">
            {isLiveKey(key) && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono font-medium bg-gb-success/15 text-gb-success border border-gb-success/30">
                <span className="w-1.5 h-1.5 rounded-full bg-gb-success" />
                LIVE MODE
              </span>
            )}
            {isTestKey(key) && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono font-medium bg-gb-warning/15 text-gb-warning border border-gb-warning/30">
                <span className="w-1.5 h-1.5 rounded-full bg-gb-warning" />
                TEST MODE
              </span>
            )}
            {!isLiveKey(key) && !isTestKey(key) && (
              <span className="text-xs text-gb-error font-mono">
                Invalid prefix
              </span>
            )}
          </div>
        )}

        {error && (
          <div className="bg-gb-error/10 border border-gb-error/30 rounded-gb px-4 py-3 text-sm text-gb-error">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={!isValidFormat || loading}
          className="gb-btn-primary w-full"
        >
          {loading ? "Connecting..." : "Connect"}
        </button>
      </form>

      <p className="text-xs text-gb-text-secondary mt-6 text-center">
        Your API key is stored locally and never sent to third parties.
      </p>
    </>
  );
}

/* ─── Monero Signature Login Tab ─────────────────────────────────────────── */

type SigStep = "address" | "sign" | "verify";

function SignatureLogin({ router }: { router: ReturnType<typeof useRouter> }) {
  const [step, setStep] = useState<SigStep>("address");
  const [address, setAddress] = useState("");
  const [nonce, setNonce] = useState("");
  const [signature, setSignature] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [expiresAt, setExpiresAt] = useState<number>(0);
  const [timeLeft, setTimeLeft] = useState<number>(0);

  // Address validation: 95 chars, starts with 4
  const isValidAddress =
    address.length === 95 && address.startsWith("4");

  // Countdown timer for nonce expiry
  useEffect(() => {
    if (expiresAt <= 0) return;

    const interval = setInterval(() => {
      const remaining = Math.max(
        0,
        Math.floor((expiresAt - Date.now()) / 1000)
      );
      setTimeLeft(remaining);

      if (remaining <= 0) {
        clearInterval(interval);
        setError("Nonce expired. Request a new one.");
        setStep("address");
        setNonce("");
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [expiresAt]);

  const copyNonce = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(nonce);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for non-HTTPS
      const ta = document.createElement("textarea");
      ta.value = nonce;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [nonce]);

  // Step 1: Request nonce
  const handleGetNonce = async () => {
    setError("");
    setLoading(true);

    try {
      const response = await fetch("/api/auth/nonce", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address }),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({ detail: "Request failed" }));
        setError(body.detail || `Error ${response.status}`);
        return;
      }

      const data = await response.json();
      setNonce(data.nonce);
      setExpiresAt(Date.now() + data.expires_in * 1000);
      setTimeLeft(data.expires_in);
      setStep("sign");
    } catch {
      setError("Connection failed. Is the backend running?");
    } finally {
      setLoading(false);
    }
  };

  // Step 3: Verify signature
  const handleVerify = async () => {
    setError("");
    setLoading(true);

    try {
      const response = await fetch("/api/auth/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address, nonce, signature: signature.trim() }),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({ detail: "Verification failed" }));
        setError(body.detail || `Error ${response.status}`);
        return;
      }

      const data = await response.json();

      // Store session token as auth credential
      setApiKey(data.session_token);
      router.push("/dashboard");
    } catch {
      setError("Connection failed. Is the backend running?");
    } finally {
      setLoading(false);
    }
  };

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  return (
    <div className="space-y-4">
      {/* Step indicator */}
      <div className="flex items-center gap-2 mb-2">
        {(["address", "sign", "verify"] as SigStep[]).map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <div
              className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                step === s
                  ? "bg-gb-accent text-white"
                  : i < ["address", "sign", "verify"].indexOf(step)
                  ? "bg-gb-success text-white"
                  : "bg-gb-surface text-gb-text-secondary border border-gb-border"
              }`}
            >
              {i + 1}
            </div>
            {i < 2 && (
              <div className="w-8 h-px bg-gb-border" />
            )}
          </div>
        ))}
      </div>

      {/* Step 1: Enter address */}
      {step === "address" && (
        <>
          <div>
            <label className="block text-sm font-medium text-gb-text-secondary mb-2">
              Monero Address
            </label>
            <input
              type="text"
              value={address}
              onChange={(e) => setAddress(e.target.value.trim())}
              placeholder="4..."
              className="gb-input w-full font-mono text-xs"
              autoFocus
              autoComplete="off"
              spellCheck={false}
            />
            <p className="text-xs text-gb-text-secondary mt-1">
              Primary address (95 chars, starts with 4)
            </p>
          </div>

          {error && (
            <div className="bg-gb-error/10 border border-gb-error/30 rounded-gb px-4 py-3 text-sm text-gb-error">
              {error}
            </div>
          )}

          <button
            onClick={handleGetNonce}
            disabled={!isValidAddress || loading}
            className="gb-btn-primary w-full"
          >
            {loading ? "Requesting..." : "Get Nonce"}
          </button>
        </>
      )}

      {/* Step 2: Sign nonce */}
      {step === "sign" && (
        <>
          <div>
            <label className="block text-sm font-medium text-gb-text-secondary mb-2">
              Sign this nonce with monero-wallet-cli
            </label>
            <div className="relative">
              <div className="gb-input w-full font-mono text-xs pr-10 break-all min-h-[3rem] flex items-center">
                {nonce}
              </div>
              <button
                onClick={copyNonce}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded hover:bg-gb-surface transition-colors"
                title="Copy nonce"
              >
                {copied ? (
                  <Check className="w-4 h-4 text-gb-success" />
                ) : (
                  <Copy className="w-4 h-4 text-gb-text-secondary" />
                )}
              </button>
            </div>

            <div className="flex items-center gap-1.5 mt-2">
              <Clock className="w-3.5 h-3.5 text-gb-text-secondary" />
              <span
                className={`text-xs font-mono ${
                  timeLeft < 60
                    ? "text-gb-error"
                    : "text-gb-text-secondary"
                }`}
              >
                Expires in {formatTime(timeLeft)}
              </span>
            </div>
          </div>

          <div className="bg-gb-surface rounded-gb p-3 text-xs font-mono text-gb-text-secondary">
            <p className="text-gb-text-primary mb-1">In monero-wallet-cli:</p>
            <p className="text-gb-accent">sign {nonce}</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gb-text-secondary mb-2">
              Paste Signature
            </label>
            <input
              type="text"
              value={signature}
              onChange={(e) => setSignature(e.target.value)}
              placeholder="SigV2..."
              className="gb-input w-full font-mono text-xs"
              autoComplete="off"
              spellCheck={false}
            />
          </div>

          {error && (
            <div className="bg-gb-error/10 border border-gb-error/30 rounded-gb px-4 py-3 text-sm text-gb-error">
              {error}
            </div>
          )}

          <div className="flex gap-3">
            <button
              onClick={() => {
                setStep("address");
                setNonce("");
                setSignature("");
                setError("");
              }}
              className="gb-btn-secondary flex-1"
            >
              Back
            </button>
            <button
              onClick={handleVerify}
              disabled={!signature.startsWith("SigV") || loading}
              className="gb-btn-primary flex-1"
            >
              {loading ? "Verifying..." : "Verify & Login"}
            </button>
          </div>
        </>
      )}

      <p className="text-xs text-gb-text-secondary mt-4 text-center">
        Maximum-privacy login. No persistent keys stored on server.
      </p>
    </div>
  );
}
