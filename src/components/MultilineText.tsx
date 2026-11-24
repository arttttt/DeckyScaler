/** Presentation text whose line breaks show, given as one "\n"-joined string or as its lines. Nothing for none. */
export const multiline = (text: string | readonly string[] | null | undefined) => {
  const joined = typeof text === "string" || text == null ? text : text.join("\n");
  return joined ? <span style={{ whiteSpace: "pre-line" }}>{joined}</span> : undefined;
};
