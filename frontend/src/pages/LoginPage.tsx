import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";

export default function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { role } = await api.login(username, password);
      navigate("/admin/dashboard", { state: { role } });
    } catch (err: any) {
      setError(err.message || "Invalid credentials");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="shell">
      <h1>ClipRoom</h1>
      <p className="muted">Operator sign-in (admin or demo account).</p>
      <div className="card" style={{ maxWidth: 380 }}>
        <form onSubmit={submit}>
          <p>
            <input
              type="text"
              placeholder="Username"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              aria-label="Username"
            />
          </p>
          <p>
            <input
              type="password"
              placeholder="Password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-label="Password"
            />
          </p>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <button className="primary" type="submit" disabled={busy}>
            Sign in
          </button>
        </form>
      </div>
    </div>
  );
}
