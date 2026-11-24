/** Presentation text whose line breaks show (presentation/lines makes it). Nothing for no text. */
export const multiline = (text: string | null | undefined) =>
  text ? <span style={{ whiteSpace: "pre-line" }}>{text}</span> : undefined;
