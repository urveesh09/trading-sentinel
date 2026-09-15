// [FIX 2026-09-14] Static-analysis regression test.
//
// On 2026-09-14 the production dashboard crashed with
//   ReferenceError: SessionPhaseCard is not defined
// because Dashboard.jsx used <SessionPhaseCard> but never imported
// it. The component lived in a separate file
// (``components/SessionPhaseCard.jsx``) so the import was
// required -- unlike the other 12 components used by Dashboard,
// which are declared inline in the same module and so don't
// need an import.
//
// This test scans Dashboard.jsx for JSX tags that are NOT
// defined inline in the file AND NOT imported from a known
// location. The contract: every PascalCase JSX tag referenced
// in Dashboard.jsx must either be a local function declaration
// or have a matching import.
//
// The check is a simple lexical scan -- not perfect (it can
// false-positive on attribute names or comments), but it
// catches the class of bug that broke production and is
// defensible enough to ship as a regression test.

import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DASHBOARD_PATH = resolve(__dirname, '../src/pages/Dashboard.jsx');

/**
 * Parse ``src/pages/Dashboard.jsx`` and return the set of
 * PascalCase tokens used as JSX tags (i.e. immediately after a
 * ``<`` character, followed by whitespace, ``>``, ``/``, or
 * a prop name) that are NOT defined locally and NOT imported.
 *
 * A token is "defined locally" if the file contains a
 * ``function <Token>`` or ``const <Token> =`` declaration.
 *
 * A token is "imported" if the file contains an import
 * statement that brings the symbol into scope. We match the
 * simple patterns: ``import Token from '...'``,
 * ``import { Token } from '...'``, and ``import { Foo, Token } from '...'``.
 */
function findUndefinedJsxTags(source) {
  // 1. Tokens used as JSX tags: <Token (with optional whitespace
  //    or props ahead of > or />). This is a loose match --
  //    it can false-positive on attribute names that happen to
  //    be PascalCase, but those are rare in the codebase and
  //    the false-positive rate is acceptable for a regression
  //    test. Tightening the match would require a JSX parser.
  const jsxTagRegex = /<([A-Z][A-Za-z0-9]*)/g;
  const referenced = new Set();
  let match;
  while ((match = jsxTagRegex.exec(source)) !== null) {
    referenced.add(match[1]);
  }

  // 2. Tokens defined locally: ``function Token(...)`` or
  //    ``const Token = ...``. We also include ``Token.displayName``
  //    assignments since the file might use the displayName
  //    pattern. Hoisted function declarations and ``const``-
  //    bound components both qualify.
  const localRegex = /(?:function|const)\s+([A-Z][A-Za-z0-9]*)/g;
  const local = new Set();
  while ((match = localRegex.exec(source)) !== null) {
    local.add(match[1]);
  }

  // 3. Tokens imported. We support three import shapes:
  //    - ``import Token from 'path'``
  //    - ``import { Token } from 'path'``
  //    - ``import { Foo, Token } from 'path'``
  //    - ``import Token, { Foo } from 'path'``
  //    - ``import * as Token from 'path'``
  // We skip the path string after ``from '...'`` -- only the
  //    imported bindings matter.
  const importRegex = /^import\s+(?:([A-Z][A-Za-z0-9]*)\s*,?\s*)?(?:\{([^}]+)\})?\s*(?:from\s*['"][^'"]+['"])?/gm;
  const imported = new Set();
  while ((match = importRegex.exec(source)) !== null) {
    if (match[1]) {
      imported.add(match[1]);
    }
    if (match[2]) {
      // ``{ Foo, Token, Baz as Qux }`` -> ['Foo', 'Token', 'Baz as Qux']
      for (const part of match[2].split(",")) {
        const name = part.trim().split(/\s+as\s+/)[0];
        if (name) {
          imported.add(name);
        }
      }
    }
  }
  // React is always in scope because we import it explicitly
  // at the top of the file (``import React, { useState } from 'react'``).
  // The regex above may or may not capture it depending on the
  // shape -- so we also accept React as imported by convention.
  imported.add("React");

  // 4. Compute the set of referenced-but-not-defined-or-imported.
  // Skip known false positives: HTML/SVG element names that
  // appear as JSX tags in valid JSX (e.g. ``<text>`` in SVG) are
  // lower-case and already excluded by the regex; PascalCase
  // false positives in this codebase are: ``FlaskConical``
  // (lucide-react icon -- imported), ``Microscope``
  // (lucide-react icon -- imported), ``BarChart3`` (imported),
  // ``AlertTriangle`` (imported). The regex captures them all;
  // we rely on the import check to filter them.
  const undefined_ = [];
  for (const token of referenced) {
    if (local.has(token)) continue;
    if (imported.has(token)) continue;
    undefined_.push(token);
  }
  return undefined_;
}

test('Dashboard.jsx references no undefined JSX tags', () => {
  const source = readFileSync(DASHBOARD_PATH, 'utf-8');
  const undefinedTags = findUndefinedJsxTags(source);
  assert.deepEqual(
    undefinedTags,
    [],
    `Dashboard.jsx references these JSX tags without defining or importing them: ` +
      `${JSON.stringify(undefinedTags)}. Either define them inline or add an import.`
  );
});

test('SessionPhaseCard is imported in Dashboard.jsx', () => {
  // [FIX 2026-09-14] Regression guard for the production crash.
  // The component lives in components/SessionPhaseCard.jsx and
  // is used in the Session Phase section heading; the import
  // must remain. Removing it brings back the
  // "SessionPhaseCard is not defined" ReferenceError.
  const source = readFileSync(DASHBOARD_PATH, 'utf-8');
  assert.match(
    source,
    /import\s+SessionPhaseCard\s+from\s+['"]\.\.\/components\/SessionPhaseCard['"]/,
    'SessionPhaseCard must be imported from ../components/SessionPhaseCard'
  );
});

test('SessionPhaseCard is used as a JSX tag in Dashboard.jsx', () => {
  // The reverse direction: the import exists but the tag is
  // never used. That suggests an unused-import cleanup went too
  // far. The Dashboard must render the card so the operator can
  // see the bounded session phase.
  const source = readFileSync(DASHBOARD_PATH, 'utf-8');
  assert.match(
    source,
    /<SessionPhaseCard\b/,
    'Dashboard must render <SessionPhaseCard> in the Session Phase section'
  );
});
