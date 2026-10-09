/**
 * [O9-M1 2026-10-09] Split a Telegram message into numbered parts.
 *
 * Telegram refuses a text over 4,096 UTF-16 units. A JavaScript string's
 * `length` is already in UTF-16 units, so it is the right measure here.
 * Splits at line ends where possible; a single over-long line is cut, never
 * dropped. A message that fits is returned unchanged as one part.
 */
const TELEGRAM_PART_MAX = 4000;

function splitMessage(text, max = TELEGRAM_PART_MAX) {
  if (text.length <= max) return [text];
  const room = max - '[part 99/99] '.length;
  const parts = [];
  let current = '';
  for (let line of text.split('\n')) {
    while (line.length > room) {
      if (current) {
        parts.push(current);
        current = '';
      }
      // Do not cut between the two halves of a surrogate pair.
      let cut = room;
      const code = line.charCodeAt(cut - 1);
      if (code >= 0xd800 && code <= 0xdbff) cut -= 1;
      parts.push(line.slice(0, cut));
      line = line.slice(cut);
    }
    if (current && current.length + 1 + line.length > room) {
      parts.push(current);
      current = line;
    } else {
      current = current ? `${current}\n${line}` : line;
    }
  }
  if (current) parts.push(current);
  return parts.map((part, i) => `[part ${i + 1}/${parts.length}] ${part}`);
}

module.exports = { splitMessage, TELEGRAM_PART_MAX };
