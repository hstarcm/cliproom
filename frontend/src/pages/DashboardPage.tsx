import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { formatExpiry } from "../lib/format";
import QrModal from "../components/QrModal";

type AdminRoom = Awaited<ReturnType<typeof api.adminRooms>>[number];

export default function DashboardPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const role = (location.state as { role?: string } | null)?.role ?? null;

  const [rooms, setRooms] = useState<AdminRoom[] | null>(null);
  const [roleHint, setRoleHint] = useState<string>(role ?? "");
  const [created, setCreated] = useState<{ room_id: string; share_url: string } | null>(null);
  const [ttlChoice, setTtlChoice] = useState<"1h" | "24h" | "7d" | "forever" | "custom">("24h");
  const [customTtl, setCustomTtl] = useState("12h");
  const [maxMb, setMaxMb] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [guestRoom, setGuestRoom] = useState<{ room_id: string; share_url: string } | null>(null);
  const [qrUrl, setQrUrl] = useState<string | null>(null);

  useEffect(() => {
    try {
      const saved = localStorage.getItem("cliproom:guest-room");
      if (saved) setGuestRoom(JSON.parse(saved));
    } catch {
      localStorage.removeItem("cliproom:guest-room");
    }
  }, []);

  const loadRooms = useCallback(async () => {
    try {
      setRooms(await api.adminRooms());
    } catch (e: any) {
      if (e.status === 401) navigate("/admin");
      else setRoleHint(e.status === 403 ? "guest" : "");
      setRooms([]);
    }
  }, [navigate]);

  useEffect(() => {
    void loadRooms();
  }, [loadRooms]);

  const create = async () => {
    setError(null);
    try {
      const ttl = ttlChoice === "custom" ? customTtl.trim() : ttlChoice;
      const cap = maxMb.trim() ? Number.parseInt(maxMb, 10) : undefined;
      const room = await api.createRoom(ttl, cap);
      setCreated(room);
      if (!roleHint || roleHint === "guest") {
        setGuestRoom(room);
        localStorage.setItem("cliproom:guest-room", JSON.stringify(room));
      }
      void loadRooms();
    } catch (e: any) {
      setError(e.message);
      // 409 means the demo already has a room — the response carries it, so
      // the panel can recover even if localStorage was cleared or lost
      if (e.status === 409 && e.payload?.room) {
        setGuestRoom(e.payload.room);
        localStorage.setItem("cliproom:guest-room", JSON.stringify(e.payload.room));
      }
    }
  };

  const terminate = async (uuid: string) => {
    try {
      await api.forceTerminate(uuid);
      void loadRooms();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const deleteGuestRoom = async () => {
    if (!guestRoom) return;
    try {
      await api.deleteRoom(guestRoom.room_id);
      setGuestRoom(null);
      localStorage.removeItem("cliproom:guest-room");
    } catch (e: any) {
      setError(e.message);
    }
  };

  const logout = async () => {
    try {
      await api.logout();
    } finally {
      navigate("/admin");
    }
  };

  return (
    <div className="shell">
      <h1>
        ClipRoom
        <span className={`role-badge ${roleHint === "guest" ? "guest" : "admin"}`}>
          {roleHint === "guest" ? "Demo" : "Admin"}
        </span>
      </h1>
      <p className="muted">
        {roleHint === "guest"
          ? "Demo account: at most one active room; you can delete only your own room."
          : "Admin: unlimited rooms, dashboard, force-terminate."}{" "}
        <button onClick={logout}>Sign out</button>
      </p>

      <div className="card">
        <h2>Create a room</h2>
        <p>
          TTL:{" "}
          <select
            value={ttlChoice}
            onChange={(e) => setTtlChoice(e.target.value as typeof ttlChoice)}
            aria-label="TTL"
          >
            <option value="1h">1 hour</option>
            <option value="24h">24 hours</option>
            <option value="7d">7 days</option>
            <option value="custom">Custom…</option>
            <option value="forever">Forever (no auto-expiry)</option>
          </select>{" "}
          {ttlChoice === "custom" && (
            <input
              type="text"
              style={{ width: 90, display: "inline-block" }}
              placeholder="e.g. 45m / 12h / 30d"
              value={customTtl}
              onChange={(e) => setCustomTtl(e.target.value)}
              aria-label="Custom TTL"
            />
          )}{" "}
          Max file size:{" "}
          <input
            type="text"
            style={{ width: 70, display: "inline-block" }}
            placeholder={`global (10 MB)`}
            value={maxMb}
            onChange={(e) => setMaxMb(e.target.value)}
            aria-label="Max file size in MB"
          />{" "}
          MB{" "}
          <button className="primary" onClick={create}>
            Create room
          </button>
        </p>
        {created && (
          <p>
            Share this link: <div className="share-url">{created.share_url}</div>
            <span className="muted">
              Room ID: {created.room_id} (the link is the only credential)
            </span>
          </p>
        )}
        {guestRoom && (roleHint === "guest" || !rooms) && (
          <p>
            Your active room: <div className="share-url">{guestRoom.share_url}</div>
            <button
              onClick={() => setQrUrl(guestRoom.share_url)}
              title="Show QR code of the share link"
            >
              QR
            </button>{" "}
            <button className="danger" onClick={deleteGuestRoom}>
              Delete this room
            </button>
          </p>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </div>

      {roleHint !== "guest" && (
        <div className="card">
          <h2>Active rooms</h2>
          {rooms === null ? (
            <p className="muted">Loading…</p>
          ) : rooms.length === 0 ? (
            <p className="muted">No active rooms.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Room (uuid)</th>
                  <th>Items</th>
                  <th>Disk</th>
                  <th>Expires</th>
                  <th>By</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rooms.map((r) => (
                  <tr key={r.room_uuid}>
                    <td style={{ fontFamily: "monospace", wordBreak: "break-all" }}>
                      <a
                        href={`/r/${r.room_id}`}
                        target="_blank"
                        rel="noopener"
                        title="Open this room"
                      >
                        {r.room_uuid}
                      </a>{" "}
                      <button
                        style={{ fontSize: 12, padding: "3px 8px" }}
                        title="Show QR code of the share link"
                        onClick={() => setQrUrl(r.share_url)}
                      >
                        QR
                      </button>
                    </td>
                    <td>{r.item_count}</td>
                    <td>{(r.disk_usage / 1024).toFixed(1)} KB</td>
                    <td>{formatExpiry(r.expires_at)}</td>
                    <td>{r.created_by}</td>
                    <td>
                      <button className="danger" onClick={() => terminate(r.room_uuid)}>
                        Terminate
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {qrUrl && <QrModal shareUrl={qrUrl} onClose={() => setQrUrl(null)} />}
    </div>
  );
}
