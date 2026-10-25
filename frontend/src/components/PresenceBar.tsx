import type { PresentMember } from "../lib/api";

/** FR-18: "in this room now" list with name + color; your own chip is
 * marked "(you)" so you never forget the name you picked. */
export default function PresenceBar({
  members,
  meId,
}: {
  members: PresentMember[];
  meId?: string;
}) {
  return (
    <div data-testid="presence">
      <span className="muted">In this room now: </span>
      <span className="presence" style={{ display: "inline-flex" }}>
        {members.length === 0 && <span className="chip muted">nobody connected</span>}
        {members.map((m) => {
          const me = meId === m.member_id;
          return (
            <span
              key={m.member_id}
              className="chip"
              data-me={me || undefined}
              style={{
                borderColor: m.color,
                color: m.color,
                fontWeight: 700,
                background: me ? `${m.color}1a` : undefined,
                boxShadow: me ? `0 0 0 1px ${m.color}` : undefined,
              }}
            >
              {m.name}
              {me ? " (you)" : ""}
            </span>
          );
        })}
      </span>
    </div>
  );
}
