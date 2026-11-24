import { describe, expect, it } from "vitest";
import { count, listed, plural } from "./words";

describe("words after a number", () => {
  it("take the singular for one and the plural otherwise", () => {
    expect(plural(1, "is", "are")).toBe("is");
    expect(plural(0, "is", "are")).toBe("are");
    expect(plural(2, "is", "are")).toBe("are");
    expect(count(1, "game", "games")).toBe("1 game");
    expect(count(3, "game", "games")).toBe("3 games");
  });
});

describe("an English list", () => {
  it("joins two with and, more with commas and a last and", () => {
    expect(listed([])).toBe("");
    expect(listed(["FP8"])).toBe("FP8");
    expect(listed(["FP8", "INT8"])).toBe("FP8 and INT8");
    expect(listed(["FP8", "INT8", "INT8 RDNA2", "INT8 Lite"])).toBe("FP8, INT8, INT8 RDNA2 and INT8 Lite");
  });
});
