/** Member identity in localStorage (FR-9/FR-10): name + per-room token. */

export interface Identity {
  name: string;
  token: string;
  member_id?: string;
  color?: string;
}

const key = (roomId: string) => `cliproom:${roomId}`;

/** 32 random bytes, hex (FR-9). */
export function generateToken(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function validateName(raw: string): string | null {
  const name = raw.trim();
  if (name.length < 1) return "Please enter a display name.";
  if (name.length > 20) return "Name must be at most 20 characters.";
  return null;
}

export function getStored(roomId: string): Identity | null {
  try {
    const raw = localStorage.getItem(key(roomId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Identity;
    if (!parsed.name || !parsed.token) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function store(roomId: string, identity: Identity): void {
  localStorage.setItem(key(roomId), JSON.stringify(identity));
}

/** For tests. */
export function clearAll(): void {
  Object.keys(localStorage)
    .filter((k) => k.startsWith("cliproom:"))
    .forEach((k) => localStorage.removeItem(k));
}
