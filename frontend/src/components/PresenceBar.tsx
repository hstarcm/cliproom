import type { PresentMember } from "../lib/api";

/** FR-18: "in this room now" list with name + color. */
export default function PresenceBar({ members }: { members: PresentMember[] }) {
  return (
    <div data-testid="presence">
      <span className="muted">In this room now: </span>
      <span className="presence" style={{ display: "inline-flex" }}>
        {members.length === 0 && <span className="chip muted">nobody connected</span>}
        {members.map((m) => (
          <span
            key={m.member_id}
            className="chip"
            style={{ borderColor: m.color, color: m.color, fontWeight: 600 }}
          >
            {m.name}
          </span>
        ))}
      </span>
    </div>
  );
}
