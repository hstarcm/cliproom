/** §9 frontend: login/join validation, persistence to localStorage. */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import JoinScreen from "../src/components/JoinScreen";
import { generateToken, getStored, store, validateName } from "../src/lib/identity";

describe("validateName (FR-8: 1–20 chars, trimmed)", () => {
  it("rejects empty and whitespace-only", () => {
    expect(validateName("")).not.toBeNull();
    expect(validateName("   ")).not.toBeNull();
  });
  it("rejects longer than 20 after trim", () => {
    expect(validateName("x".repeat(21))).not.toBeNull();
    expect(validateName("  " + "x".repeat(21) + "  ")).not.toBeNull();
  });
  it("accepts 1–20 after trim", () => {
    expect(validateName("a")).toBeNull();
    expect(validateName("  Ana  ")).toBeNull();
    expect(validateName("x".repeat(20))).toBeNull();
  });
});

describe("identity storage (FR-9: name + token in localStorage, keyed by room)", () => {
  it("round-trips per room and generates 64-hex tokens", () => {
    const token = generateToken();
    expect(token).toMatch(/^[0-9a-f]{64}$/);
    store("room1", { name: "ana", token });
    store("room2", { name: "bo", token: generateToken() });
    expect(getStored("room1")?.name).toBe("ana");
    expect(getStored("room2")?.name).toBe("bo");
    expect(getStored("room1")?.token).toBe(token);
    expect(getStored("missing")).toBeNull();
  });
});

describe("JoinScreen", () => {
  it("shows an error for an empty name and does not join", async () => {
    const onJoin = vi.fn();
    render(<JoinScreen onJoin={onJoin} />);
    await userEvent.click(screen.getByRole("button", { name: /join/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/display name/i);
    expect(onJoin).not.toHaveBeenCalled();
  });

  it("shows an error for names longer than 20 characters", async () => {
    const onJoin = vi.fn();
    render(<JoinScreen onJoin={onJoin} />);
    await userEvent.type(screen.getByLabelText(/display name/i), "x".repeat(21));
    await userEvent.click(screen.getByRole("button", { name: /join/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/20 characters/i);
    expect(onJoin).not.toHaveBeenCalled();
  });

  it("trims and forwards a valid name", async () => {
    const onJoin = vi.fn();
    render(<JoinScreen onJoin={onJoin} />);
    await userEvent.type(screen.getByLabelText(/display name/i), "  Ana  ");
    await userEvent.click(screen.getByRole("button", { name: /join/i }));
    await waitFor(() => expect(onJoin).toHaveBeenCalledWith("Ana"));
  });
});
