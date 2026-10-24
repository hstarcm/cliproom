/** Room WebSocket client (FR-16/FR-17/FR-18): one-time ticket auth,
 * heartbeat every 30 s, exponential reconnect backoff 1 s → 30 s cap. */

export interface RoomEvent {
  type: string;
  items?: any[];
  members?: any[];
  item?: any;
  item_id?: string;
  member?: any;
  member_id?: string;
}

export type WSFactory = (url: string) => WebSocket;

export function defaultWsFactory(url: string): WebSocket {
  return new WebSocket(url);
}

export class RoomWS {
  private ws: WebSocket | null = null;
  private attempt = 0;
  private closedByUser = false;
  private heartbeatTimer: number | null = null;
  private reconnectTimer: number | null = null;

  constructor(
    private roomId: string,
    private getTicket: () => Promise<string>,
    private onEvent: (event: RoomEvent) => void,
    private wsFactory: WSFactory = defaultWsFactory,
  ) {}

  connect(): void {
    if (this.closedByUser) return;
    this.getTicket()
      .then((ticket) => {
        if (this.closedByUser) return;
        const proto = location.protocol === "https:" ? "wss:" : "ws:";
        const url = `${proto}//${location.host}/api/rooms/${this.roomId}/ws?ticket=${encodeURIComponent(ticket)}`;
        this.attach(this.wsFactory(url));
      })
      .catch(() => this.scheduleReconnect());
  }

  private attach(ws: WebSocket): void {
    this.ws = ws;
    ws.onmessage = (ev) => {
      try {
        this.onEvent(JSON.parse(ev.data));
      } catch {
        /* ignore malformed frames */
      }
    };
    ws.onopen = () => {
      this.attempt = 0;
      this.startHeartbeat();
    };
    ws.onclose = () => {
      this.stopHeartbeat();
      if (!this.closedByUser) this.scheduleReconnect();
    };
    ws.onerror = () => {
      /* onclose follows */
    };
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = window.setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: "heartbeat" }));
      }
    }, 30_000);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer !== null) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  /** Exponential backoff: 1s, 2s, 4s … capped at 30 s (FR-17). */
  private scheduleReconnect(): void {
    if (this.closedByUser || this.reconnectTimer !== null) return;
    const delay = Math.min(1000 * 2 ** this.attempt, 30_000);
    this.attempt += 1;
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  /** Exposed for tests. */
  get backoffAttempt(): number {
    return this.attempt;
  }

  close(): void {
    this.closedByUser = true;
    this.stopHeartbeat();
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }
}
