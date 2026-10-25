/** FR-14/FR-18 UI: presence chip marks your own identity; item timestamps
 * carry an absolute local date+time next to the relative one. */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import PresenceBar from "../src/components/PresenceBar";
import { formatAbsolute } from "../src/lib/format";

describe("PresenceBar '(you)' marker", () => {
  const members = [
    { member_id: "me", name: "alice", color: "#1F6FEB" },
    { member_id: "other", name: "bob", color: "#BF8700" },
  ];

  it("marks only the own chip", () => {
    render(<PresenceBar members={members} meId="me" />);
    expect(screen.getByText(/alice \(you\)/i)).toBeInTheDocument();
    expect(screen.getByText("bob")).toBeInTheDocument();
    expect(screen.getByText(/alice \(you\)/i).getAttribute("data-me")).toBe("true");
    expect(screen.getByText("bob").getAttribute("data-me")).toBeNull();
  });

  it("renders without a me id", () => {
    render(<PresenceBar members={members} />);
    expect(screen.getByText("alice")).toBeInTheDocument();
    expect(screen.queryByText(/\(you\)/i)).toBeNull();
  });
});

describe("formatAbsolute (item timestamps)", () => {
  it("formats Z-suffixed and bare ISO strings", () => {
    expect(formatAbsolute("2026-10-25T09:05:00Z")).toMatch(/\d{1,2} \w{3} \d{4}, \d{2}:\d{2}/);
    expect(formatAbsolute("2026-10-25T09:05:00")).toMatch(/\d{1,2} \w{3} \d{4}/);
  });
});
