import { describe, expect, it } from "vitest";
import { count, plural } from "./words";

describe("words after a number", () => {
  it("take the singular for one and the plural otherwise", () => {
    expect(plural(1, "is", "are")).toBe("is");
    expect(plural(0, "is", "are")).toBe("are");
    expect(plural(2, "is", "are")).toBe("are");
    expect(count(1, "game", "games")).toBe("1 game");
    expect(count(3, "game", "games")).toBe("3 games");
  });
});
