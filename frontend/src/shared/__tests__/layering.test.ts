import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

/**
 * Enforces the FSD layering rule that no lint rule covers: files under
 * `shared/` must never import from `features/` or `app/`. The rule was silently
 * violated by four production files and three tests before this test existed;
 * a rule with no enforcement is a rule that regresses.
 *
 * The scan is textual on purpose: it matches the import specifier a reader
 * would see, so a reintroduced edge fails here rather than in production.
 */

const SRC_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..')

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) {
      walk(full, out)
    } else if (/\.(ts|tsx)$/.test(entry)) {
      out.push(full)
    }
  }
  return out
}

/** True when a module specifier escapes `shared/` into a sibling layer. */
function crossesIntoFeatureOrApp(specifier: string): boolean {
  // Relative specifiers only; an alias would be caught by the same pattern.
  return /(?:^|\/)features(?:\/|$)/.test(specifier) || /(?:^|\/)app(?:\/|$)/.test(specifier)
}

function importSpecifiers(source: string): string[] {
  const specifiers: string[] = []
  const pattern = /(?:import|export)\s[^'"]*from\s*['"]([^'"]+)['"]|import\s*['"]([^'"]+)['"]/g
  let match: RegExpExecArray | null
  while ((match = pattern.exec(source)) !== null) {
    specifiers.push(match[1] ?? match[2])
  }
  return specifiers
}

describe('FSD layering — shared must not import features/app', () => {
  it('has no file under shared/ importing from features/ or app/', () => {
    const violations: string[] = []
    const sharedRoot = join(SRC_ROOT, 'shared')

    for (const file of walk(sharedRoot)) {
      const source = readFileSync(file, 'utf8')
      for (const specifier of importSpecifiers(source)) {
        if (crossesIntoFeatureOrApp(specifier)) {
          violations.push(`${file.replace(SRC_ROOT, 'src')} → ${specifier}`)
        }
      }
    }

    expect(violations).toEqual([])
  })
})
