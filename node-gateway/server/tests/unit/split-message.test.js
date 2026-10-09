const { splitMessage } = require('../../utils/split-message');

test('a message that fits is unchanged', () => {
  expect(splitMessage('short')).toEqual(['short']);
});

test('parts fit, keep every character and never split a surrogate pair', () => {
  const text = ['a'.repeat(100), '📈'.repeat(3000), 'b'.repeat(50)].join('\n');
  const parts = splitMessage(text);
  expect(parts.length).toBeGreaterThan(1);
  parts.forEach((p) => {
    expect(p.length).toBeLessThanOrEqual(4000);
    const body = p.replace(/^\[part \d+\/\d+\] /, '');
    expect(/[\uD800-\uDBFF]$/.test(body)).toBe(false);
  });
  expect(parts.map((p) => p.replace(/^\[part \d+\/\d+\] /, '')).join('').replace(/\n/g, ''))
    .toBe(text.replace(/\n/g, ''));
});
