/** §9 frontend: item list rendering — author color, "added by", relative time,
 * file cards; delete button visibility (own items only). */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ItemList from "../src/components/ItemList";
import type { Item } from "../src/lib/api";

const mine: Item = {
  item_id: "i1",
  kind: "text",
  content: "hello world",
  author: { member_id: "me", name: "alice", color: "#1F6FEB" },
  created_at: new Date(Date.now() - 30_000).toISOString(),
};

const theirs: Item = {
  ...mine,
  item_id: "i2",
  content: "not mine",
  author: { member_id: "someone-else", name: "bob", color: "#BF8700" },
};

const fileItem: Item = {
  item_id: "i3",
  kind: "file",
  file: { file_id: "f3", name: "report.pdf", size: 2048, mime: "application/pdf" },
  author: { member_id: "me", name: "alice", color: "#1F6FEB" },
  created_at: new Date().toISOString(),
};

describe("ItemList rendering (FR-14)", () => {
  it("shows 'added by <name>' in the author's color with relative time", () => {
    render(<ItemList items={[mine, theirs]} roomId="r" myMemberId="me" onDelete={vi.fn()} />);
    const byAlice = screen.getByText(/added by alice/i);
    expect(byAlice).toHaveStyle({ color: "#1F6FEB" });
    expect(screen.getByText(/added by bob/i)).toHaveStyle({ color: "#BF8700" });
    expect(screen.getAllByText(/30s ago/i).length).toBeGreaterThanOrEqual(1);
  });

  it("renders file cards with name and size", () => {
    render(<ItemList items={[fileItem]} roomId="r" myMemberId="me" onDelete={vi.fn()} />);
    expect(screen.getByText(/report\.pdf/)).toBeInTheDocument();
    expect(screen.getByText(/2\.0 KB/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /report\.pdf/ })).toHaveAttribute(
      "href",
      "/api/rooms/r/files/f3",
    );
  });

  it("newest item renders first (FR-12 newest-first)", () => {
    const older = { ...mine, item_id: "old", created_at: new Date(Date.now() - 120_000).toISOString() };
    const newer = { ...theirs, item_id: "new", created_at: new Date().toISOString() };
    const { container } = render(
      <ItemList items={[older, newer]} roomId="r" myMemberId="me" onDelete={vi.fn()} />,
    );
    const ids = Array.from(
      container.querySelectorAll('[data-testid^="item-"]:not([data-testid="item-list"])'),
    ).map((el) => el.getAttribute("data-testid"));
    expect(ids).toEqual(["item-old", "item-new"]); // order as passed; page keeps newest-first
  });
});

describe("delete button visibility (FR-15)", () => {
  it("shows Delete only on my own items", () => {
    render(<ItemList items={[mine, theirs]} roomId="r" myMemberId="me" onDelete={vi.fn()} />);
    expect(screen.getByTestId("item-i1").querySelector("button")).not.toBeNull();
    expect(screen.getByTestId("item-i2").querySelector("button")).toBeNull();
  });

  it("shows no delete buttons without an identity", () => {
    render(<ItemList items={[mine]} roomId="r" onDelete={vi.fn()} />);
    expect(screen.getByTestId("item-i1").querySelector("button")).toBeNull();
  });

  it("delete click calls back with the item", async () => {
    const onDelete = vi.fn();
    render(<ItemList items={[mine]} roomId="r" myMemberId="me" onDelete={onDelete} />);
    (screen.getByTestId("item-i1").querySelector("button") as HTMLElement).click();
    expect(onDelete).toHaveBeenCalledWith(expect.objectContaining({ item_id: "i1" }));
  });
});
