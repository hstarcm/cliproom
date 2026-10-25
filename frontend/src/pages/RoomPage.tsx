import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import JoinScreen from "../components/JoinScreen";
import ItemList from "../components/ItemList";
import Composer from "../components/Composer";
import PresenceBar from "../components/PresenceBar";
import { api, Item, PresentMember } from "../lib/api";
import { generateToken, getStored, Identity, store } from "../lib/identity";
import { RoomEvent, RoomWS } from "../lib/ws";

export default function RoomPage() {
  const { roomId = "" } = useParams();
  const [status, setStatus] = useState<"loading" | "notfound" | "joining" | "live">("loading");
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [roomCapMb, setRoomCapMb] = useState<number>(10);
  const [items, setItems] = useState<Item[]>([]);
  const [members, setMembers] = useState<PresentMember[]>([]);
  const wsRef = useRef<RoomWS | null>(null);

  const applyEvent = useCallback((event: RoomEvent) => {
    switch (event.type) {
      case "state":
        setItems(event.items ?? []);
        setMembers(event.members ?? []);
        break;
      case "item_added":
        setItems((prev) =>
          prev.some((i) => i.item_id === event.item.item_id) ? prev : [event.item, ...prev],
        );
        break;
      case "item_deleted":
        setItems((prev) => prev.filter((i) => i.item_id !== event.item_id));
        break;
      case "member_joined":
        setMembers((prev) =>
          prev.some((m) => m.member_id === event.member.member_id)
            ? prev
            : [...prev, event.member],
        );
        break;
      case "member_left":
        setMembers((prev) => prev.filter((m) => m.member_id !== event.member_id));
        break;
      case "presence":
        setMembers(event.members ?? []);
        break;
    }
  }, []);

  const startWs = useCallback(
    (id: Identity) => {
      wsRef.current?.close();
      const ws = new RoomWS(
        roomId,
        async () => (await api.wsTicket(roomId, id.token)).ticket,
        applyEvent,
      );
      wsRef.current = ws;
      ws.connect();
    },
    [roomId, applyEvent],
  );

  // room existence check + returning-member flow (FR-10)
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const meta = await api.roomMeta(roomId);
        setRoomCapMb(meta.max_file_mb ?? 10);
      } catch (e: any) {
        if (!cancelled) setStatus(e.status === 404 ? "notfound" : "notfound");
        return;
      }
      if (cancelled) return;
      const stored = getStored(roomId);
      if (stored) {
        // re-register presence automatically (FR-10)
        try {
          const m = await api.join(roomId, stored.name, stored.token);
          const next = { ...stored, member_id: m.member_id, color: m.color };
          store(roomId, next);
          setIdentity(next);
          setStatus("live");
          startWs(next);
        } catch {
          // stored identity no longer valid (room recreated) → re-join screen
          setStatus("joining");
        }
      } else {
        setStatus("joining");
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roomId]);

  useEffect(() => () => wsRef.current?.close(), []);

  const handleJoin = async (name: string) => {
    const token = generateToken();
    const member = await api.join(roomId, name, token);
    const next: Identity = { name, token, member_id: member.member_id, color: member.color };
    store(roomId, next);
    setIdentity(next);
    setStatus("live");
    startWs(next);
  };

  const addText = async (content: string) => {
    if (!identity) return;
    await api.addText(roomId, content, identity.token);
    // item_added arrives via WS
  };

  const upload = async (file: File) => {
    if (!identity) return;
    await api.uploadFile(roomId, file, identity.token);
  };

  const remove = async (item: Item) => {
    if (!identity) return;
    await api.deleteItem(roomId, item.item_id, identity.token);
  };

  if (status === "loading") {
    return (
      <div className="shell">
        <p className="muted">Loading room…</p>
      </div>
    );
  }

  if (status === "notfound") {
    return (
      <div className="shell">
        <h1>404 — room not found</h1>
        <p className="muted">
          This room does not exist, has expired, or was deleted. The link you hold is the
          only credential — check that it is complete.
        </p>
      </div>
    );
  }

  return (
    <div className="shell">
      <h1>ClipRoom</h1>
      {status === "joining" && <JoinScreen onJoin={handleJoin} />}
      {status === "live" && identity && (
        <>
          <div className="card">
            <p style={{ margin: "0 0 6px" }}>
              You are in this room as{" "}
              <b data-testid="my-name" style={{ color: identity.color }}>
                {identity.name}
              </b>
            </p>
            <PresenceBar members={members} meId={identity.member_id} />
          </div>
          <Composer onAddText={addText} onUpload={upload} maxFileMb={roomCapMb} />
          <ItemList
            items={items}
            roomId={roomId}
            myMemberId={identity.member_id}
            onDelete={remove}
          />
        </>
      )}
    </div>
  );
}
