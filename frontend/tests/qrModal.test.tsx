/** QR popup on the operator dashboard: renders the share URL + QR image,
 * copy button, and closes via the Close button. */
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("qrcode", () => ({
  default: { toDataURL: vi.fn(async () => "data:image/png;base64,FAKEQR") },
}));

import QrModal from "../src/components/QrModal";

describe("QrModal", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows the share URL and a rendered QR image", async () => {
    const onClose = vi.fn();
    render(<QrModal shareUrl="http://localhost:8080/r/abc123" onClose={onClose} />);
    expect(await screen.findByTestId("qr-image")).toHaveAttribute(
      "src",
      "data:image/png;base64,FAKEQR",
    );
    expect(screen.getByTestId("qr-url").textContent).toBe("http://localhost:8080/r/abc123");
    expect(screen.getByRole("button", { name: "Copy link" })).toBeInTheDocument();
  });

  it("closes on the Close button", async () => {
    const onClose = vi.fn();
    render(<QrModal shareUrl="http://x/r/y" onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalled();
  });
});
