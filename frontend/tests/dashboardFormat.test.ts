/** Regression for the blank-dashboard bug: forever rooms have expires_at
 * null — formatting must not throw on them (FR-19 / AC20). */
import { describe, expect, it } from "vitest";
import { formatExpiry } from "../src/lib/format";

describe("formatExpiry (admin listing cell)", () => {
  it("returns 'forever' for null (forever rooms) instead of throwing", () => {
    expect(formatExpiry(null)).toBe("forever");
  });

  it("formats Z-suffixed and suffixed-less ISO strings to a locale string", () => {
    expect(formatExpiry("2026-10-25T09:00:00Z")).toMatch(/2026/);
    expect(formatExpiry("2026-10-25T09:00:00")).toMatch(/2026/);
    expect(formatExpiry("2026-10-25T09:00:00+00:00")).toMatch(/2026/);
  });
});
