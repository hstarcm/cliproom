import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api";

type AdminRoom = Awaited<ReturnType<typeof api.adminRooms>>[number];

export default function DashboardPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const role = (location.state as { role?: string } | null)?.role ?? null;

  const [rooms, setRooms] = useState<AdminRoom[] | null>(null);
  const [roleHint, setRoleHint] = useState<string>(role ?? "");
  const [created, setCreated] = useState<{ room_id: string; share_url: string } | null>(null);
  const [ttl, setTtl] = useState<"1h" | "24h" | "7d">("24h");
  const [error, setError] = useState<string | null>(null);
  const [guestRoom, setGuestRoom] = useState<{ room_id: string; share_url: string } | null>(null);

  useEffect(() => {
    const saved = localStorage.getItem("cliproom:guest-room");
    if (saved) setGuestRoom(JSON.parse(saved));
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
      const room = await api.createRoom(ttl);
      setCreated(room);
      if (!roleHint || roleHint === "guest") {
        setGuestRoom(room);
        localStorage.setItem("cliproom:guest-room", JSON.stringify(room));
      }
      void loadRooms();
    } catch (e: any) {
      setError(e.message);
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
      <h1>ClipRoom — operator</h1>
      <p className="muted">
        {roleHint === "guest"
          ? "Guest/demo account: at most one active room; you can delete only your own room."
          : "Admin: unlimited rooms, dashboard, force-terminate."}{" "}
        <button onClick={logout}>Sign out</button>
      </p>

      <div className="card">
        <h2>Create a room</h2>
        <p>
          TTL:{" "}
          <select value={ttl} onChange={(e) => setTtl(e.target.value as any)} aria-label="TTL">
            <option value="1h">1 hour</option>
            <option value="24h">24 hours</option>
            <option value="7d">7 days</option>
          </select>{" "}
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
                    <td style={{ fontFamily: "monospace" }}>{r.room_uuid.slice(0, 12)}…</td>
                    <td>{r.item_count}</td>
                    <td>{(r.disk_usage / 1024).toFixed(1)} KB</td>
                    <td>{new Date(r.expires_at.endsWith("Z") ? r.expires_at : `${r.expires_at}Z`).toLocaleString()}</td>
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
    </div>
  );
}
