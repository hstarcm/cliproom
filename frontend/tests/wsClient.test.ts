/** §9 frontend: WS client — event application + reconnect backoff with a
 * mocked socket. */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { RoomWS } from "../src/lib/ws";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  readyState = 0;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  get OPEN() {
    return 1;
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.readyState = 3;
  }

  // test helpers
  simulateOpen() {
    this.readyState = 1;
    this.onopen?.();
  }

  simulateClose() {
    this.readyState = 3;
    this.onclose?.();
  }

  deliver(event: object) {
    this.onmessage?.({ data: JSON.stringify(event) });
  }
}

function setup() {
  FakeWebSocket.instances = [];
  const events: any[] = [];
  const getTicket = vi.fn(async () => "ticket-1");
  const ws = new RoomWS(
    "room1",
    getTicket,
    (e) => events.push(e),
    (url) => new FakeWebSocket(url) as unknown as WebSocket,
  );
  return { ws, events, getTicket };
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("RoomWS", () => {
  it("connects with a one-time ticket in the URL and applies state events", async () => {
    const { ws, events } = setup();
    ws.connect();
    await vi.advanceTimersByTimeAsync(0);
    const sock = FakeWebSocket.instances[0];
    expect(sock.url).toContain("/api/rooms/room1/ws?ticket=ticket-1");
    sock.simulateOpen();
    sock.deliver({ type: "state", items: [], members: [] });
    expect(events).toEqual([{ type: "state", items: [], members: [] }]);
    ws.close();
  });

  it("sends heartbeats every 30 s while open (FR-18)", async () => {
    const { ws } = setup();
    ws.connect();
    await vi.advanceTimersByTimeAsync(0);
    const sock = FakeWebSocket.instances[0];
    sock.simulateOpen();
    await vi.advanceTimersByTimeAsync(31_000);
    expect(sock.sent.filter((s) => s.includes("heartbeat")).length).toBeGreaterThanOrEqual(1);
    ws.close();
  });

  it("reconnects with exponential backoff 1s→2s→4s and resets after success", async () => {
    const { ws, getTicket } = setup();
    ws.connect();
    await vi.advanceTimersByTimeAsync(0);
    FakeWebSocket.instances[0].simulateOpen();
    FakeWebSocket.instances[0].simulateClose();

    await vi.advanceTimersByTimeAsync(1000); // first retry after 1 s
    expect(FakeWebSocket.instances.length).toBe(2);
    FakeWebSocket.instances[1].simulateClose();

    await vi.advanceTimersByTimeAsync(2000); // second retry after 2 s
    expect(FakeWebSocket.instances.length).toBe(3);
    FakeWebSocket.instances[2].simulateClose();

    await vi.advanceTimersByTimeAsync(3000); // not yet: backoff doubled to 4 s
    expect(FakeWebSocket.instances.length).toBe(3);
    await vi.advanceTimersByTimeAsync(1500); // 4.5 s since last close → reconnected
    expect(FakeWebSocket.instances.length).toBe(4);

    // success resets the backoff: next drop reconnects after 1 s again
    FakeWebSocket.instances[3].simulateOpen();
    FakeWebSocket.instances[3].simulateClose();
    await vi.advanceTimersByTimeAsync(1000);
    expect(FakeWebSocket.instances.length).toBe(5);
    expect(getTicket.mock.calls.length).toBe(5); // fresh ticket each attempt
    ws.close();
  });

  it("does not reconnect after an explicit close", async () => {
    const { ws } = setup();
    ws.connect();
    await vi.advanceTimersByTimeAsync(0);
    FakeWebSocket.instances[0].simulateOpen();
    ws.close();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(FakeWebSocket.instances.length).toBe(1);
  });
});
