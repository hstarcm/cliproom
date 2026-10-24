import { useState } from "react";
import { validateName } from "../lib/identity";

export interface JoinScreenProps {
  onJoin: (name: string) => void;
}

/** FR-8: first visit requires a display name of 1–20 chars (trimmed). */
export default function JoinScreen({ onJoin }: JoinScreenProps) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const problem = validateName(name);
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    onJoin(name.trim());
  };

  return (
    <div className="card" data-testid="join-screen">
      <h2>Join this room</h2>
      <p className="muted">Pick a display name (1–20 characters). It stays in your browser.</p>
      <form onSubmit={submit}>
        <input
          type="text"
          value={name}
          maxLength={40}
          placeholder="e.g. Ana"
          onChange={(e) => setName(e.target.value)}
          aria-label="Display name"
        />
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <p>
          <button className="primary" type="submit">
            Join
          </button>
        </p>
      </form>
    </div>
  );
}
