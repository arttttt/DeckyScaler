/** English words that follow a number. */

/** The word for one, or for any other number. */
export const plural = (n: number, one: string, many: string): string => (n === 1 ? one : many);

/** A number and the word that follows it: "1 game", "3 games". */
export const count = (n: number, one: string, many: string): string => `${n} ${plural(n, one, many)}`;
