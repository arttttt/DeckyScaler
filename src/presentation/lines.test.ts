import { describe, expect, it } from "vitest";
import { lines } from "./lines";

describe("lines of presentation text", () => {
  it("puts each part on a line of its own, leaving out the empty ones", () => {
    expect(lines(["Patched.", "Libraries: none"])).toBe("Patched.\nLibraries: none");
    expect(lines([null, "Patched.", "", undefined, "Libraries: none"])).toBe("Patched.\nLibraries: none");
    expect(lines(["Patched."])).toBe("Patched.");
    expect(lines([])).toBe("");
    expect(lines([null, ""])).toBe("");
  });
});
