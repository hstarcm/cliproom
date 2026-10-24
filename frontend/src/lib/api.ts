/** REST client — same-origin /api (nginx proxies to the backend). */

export interface ItemAuthor {
  member_id: string;
  name: string;
  color: string;
}

export interface Item {
  item_id: string;
  kind: "text" | "file";
  content?: string;
  file?: { file_id: string; name: string; size: number; mime: string };
  author: ItemAuthor;
  created_at: string;
}

export interface PresentMember {
  member_id: string;
  name: string;
  color: string;
}

async function json(resp: Response): Promise<any> {
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const message =
      typeof body?.detail === "string"
        ? body.detail
        : Array.isArray(body?.detail)
          ? body.detail.map((d: any) => d.msg).join("; ")
          : `Request failed (${resp.status})`;
    const err = new Error(message) as Error & { status: number };
    err.status = resp.status;
    throw err;
  }
  return body;
}

const CSRF = { "X-Requested-With": "fetch" };

export const api = {
  login: async (username: string, password: string) => {
    const r = await fetch("/api/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...CSRF },
      credentials: "include",
      body: JSON.stringify({ username, password }),
    });
    return (await json(r)) as { role: "admin" | "guest" };
  },

  logout: async () => {
    const r = await fetch("/api/admin/logout", {
      method: "POST",
      headers: { ...CSRF },
      credentials: "include",
    });
    return json(r);
  },

  adminRooms: async () => {
    const r = await fetch("/api/admin/rooms", { credentials: "include" });
    return (await json(r)) as Array<{
      room_uuid: string;
      item_count: number;
      disk_usage: number;
      expires_at: string;
      created_by: string;
    }>;
  },

  forceTerminate: async (roomUuid: string) => {
    const r = await fetch(`/api/admin/rooms/${roomUuid}`, {
      method: "DELETE",
      headers: { ...CSRF },
      credentials: "include",
    });
    return json(r);
  },

  createRoom: async (ttl: string, maxFileMb?: number) => {
    const body: Record<string, unknown> = { ttl };
    if (maxFileMb !== undefined) body.max_file_mb = maxFileMb;
    const r = await fetch("/api/rooms", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...CSRF },
      credentials: "include",
      body: JSON.stringify(body),
    });
    return (await json(r)) as { room_id: string; share_url: string; expires_at: string | null };
  },

  deleteRoom: async (roomUuidOrId: string) => {
    const r = await fetch(`/api/rooms/${roomUuidOrId}`, {
      method: "DELETE",
      headers: { ...CSRF },
      credentials: "include",
    });
    return json(r);
  },

  roomMeta: async (roomId: string) => {
    const r = await fetch(`/api/rooms/${roomId}`);
    return (await json(r)) as { expires_at: string; item_count: number };
  },

  join: async (roomId: string, name: string, token: string) => {
    const r = await fetch(`/api/rooms/${roomId}/join`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Member-Token": token },
      body: JSON.stringify({ name }),
    });
    return (await json(r)) as PresentMember;
  },

  items: async (roomId: string) => {
    const r = await fetch(`/api/rooms/${roomId}/items`);
    return (await json(r)) as { items: Item[]; members_present: PresentMember[] };
  },

  addText: async (roomId: string, content: string, token: string) => {
    const r = await fetch(`/api/rooms/${roomId}/items/text`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Member-Token": token },
      body: JSON.stringify({ content }),
    });
    return (await json(r)) as Item;
  },

  uploadFile: async (roomId: string, file: File, token: string) => {
    const form = new FormData();
    form.append("file", file);
    const r = await fetch(`/api/rooms/${roomId}/items/file`, {
      method: "POST",
      headers: { "X-Member-Token": token },
      body: form,
    });
    return (await json(r)) as Item;
  },

  deleteItem: async (roomId: string, itemId: string, token: string) => {
    const r = await fetch(`/api/rooms/${roomId}/items/${itemId}`, {
      method: "DELETE",
      headers: { "X-Member-Token": token },
    });
    return json(r);
  },

  wsTicket: async (roomId: string, token: string) => {
    const r = await fetch(`/api/rooms/${roomId}/ws-ticket`, {
      method: "POST",
      headers: { "X-Member-Token": token },
    });
    return (await json(r)) as { ticket: string };
  },
};

export function fileDownloadUrl(roomId: string, fileId: string): string {
  return `/api/rooms/${roomId}/files/${fileId}`;
}
