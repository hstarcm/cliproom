import type { Item } from "../lib/api";
import { fileDownloadUrl } from "../lib/api";
import { formatSize, relativeTime } from "../lib/format";

export interface ItemListProps {
  items: Item[];
  roomId: string;
  myMemberId?: string;
  onDelete: (item: Item) => void;
}

/** FR-12/FR-14/FR-15: newest-first list; every item shows "added by <name>"
 * in the author's color with a relative time; delete only on own items. */
export default function ItemList({ items, roomId, myMemberId, onDelete }: ItemListProps) {
  if (items.length === 0) {
    return (
      <p className="muted" data-testid="empty-canvas">
        Nothing shared yet — add the first clip or file.
      </p>
    );
  }
  return (
    <div data-testid="item-list">
      {items.map((item) => (
        <div className="card" key={item.item_id} data-testid={`item-${item.item_id}`}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
            <span className="author" style={{ color: item.author.color }}>
              added by {item.author.name}
            </span>
            <span className="muted">{relativeTime(item.created_at)}</span>
          </div>
          {item.kind === "text" ? (
            <pre style={{ whiteSpace: "pre-wrap", margin: "8px 0 0" }}>{item.content}</pre>
          ) : (
            <p style={{ margin: "8px 0 0" }}>
              📎{" "}
              <a href={fileDownloadUrl(roomId, item.file!.file_id)} download={item.file!.name}>
                {item.file!.name}
              </a>{" "}
              <span className="muted">({formatSize(item.file!.size)})</span>
            </p>
          )}
          {myMemberId && item.author.member_id === myMemberId && (
            <p style={{ margin: "8px 0 0", textAlign: "right" }}>
              <button
                className="danger"
                onClick={() => onDelete(item)}
                aria-label={`Delete ${item.kind === "text" ? "clip" : item.file?.name}`}
              >
                Delete
              </button>
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
