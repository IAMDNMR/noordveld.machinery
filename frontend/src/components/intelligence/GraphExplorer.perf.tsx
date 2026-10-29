// @vitest-environment jsdom
// Rendering cost of the relationship graph alone, with the data already in hand (the API request is measured by backend/scripts/perf_probe.py).
// Not part of the regular suite (the *.perf.tsx name is outside its pattern). Run: npm run perf:ui
//
// TWO SEPARATE MEASUREMENTS, not equivalent to each other:
//
// 1. This file runs in jsdom, a simulated DOM that is roughly three times slower than a browser at building elements. Its thresholds below are
//    regression guardrails for that simulation only: each is about 2-3x the p50 measured on 2026-10-29 (12 parts 65 ms, 60 parts 145 ms,
//    150 parts 660 ms; layout alone 2 / 16 / 87 ms), so a change that makes the graph several times slower fails, normal noise does not.
//
// 2. The real target is 500 ms at 150 parts in an actual browser. That is NOT tested continuously: it was measured by hand on 2026-10-29
//    (Chrome in the Claude desktop app, Vite dev build, hidden pane, one run of 10 after a warm-up). Method: import GraphExplorer in the page,
//    then for each size time `flushSync(() => root.render(<GraphExplorer view={star(n)} />))` followed by a forced layout (getBoundingClientRect
//    and svg.getBBox), because animation frames do not fire in a hidden pane. Result p50 / worst: 12 parts 39 / 49 ms, 60 parts 75 / 140 ms,
//    150 parts 218 / 389 ms. Repeat that measurement after any change to GraphExplorer.tsx or graphModel.ts.
import { cleanup, render } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import type { GraphView } from '../../api/intelligenceTypes'
import { GraphExplorer } from './GraphExplorer'
import { graphPositions } from './graphModel'

afterEach(cleanup)

/** A machine with `n` fitting parts, each part in one of 8 categories: the shape graph draws for a machine and its fitting parts. */
const star = (n: number): GraphView => ({
  nodes: [
    { id: 'M', label: 'Machine A', kind: 'MACHINE', part_number: null },
    ...Array.from({ length: n }, (_, i) => ({
      id: `P${i}`,
      label: `Part ${i}`,
      kind: 'PART',
      part_number: `PN-${i}`,
    })),
    ...Array.from({ length: 8 }, (_, i) => ({
      id: `C${i}`,
      label: `Category ${i}`,
      kind: 'CATEGORY',
      part_number: null,
    })),
  ],
  edges: Array.from({ length: n }, (_, i) => [
    { source: `P${i}`, target: 'M', type: 'FITS', data_class: 'REAL' as const },
    { source: `P${i}`, target: `C${i % 8}`, type: 'IN_CATEGORY', data_class: 'REAL' as const },
  ]).flat(),
  truncated: false,
})

it('renders the relationship graph quickly enough to feel immediate, at three sizes', () => {
  const rows: string[] = []
  const medians: [number, number][] = []
  // jsdom-only guardrails in ms, per size (see the header): not the 500 ms real-browser target
  const budget: Record<number, number> = { 12: 200, 60: 500, 150: 1200 }
  for (const n of [12, 60, 150]) {
    const view = star(n)
    render(<GraphExplorer view={view} />) // warm-up
    cleanup()
    const layoutStart = performance.now()
    for (let run = 0; run < 5; run++) graphPositions(view)
    const layout = (performance.now() - layoutStart) / 5
    const times: number[] = []
    for (let run = 0; run < 15; run++) {
      const start = performance.now()
      render(<GraphExplorer view={view} />)
      times.push(performance.now() - start)
      cleanup()
    }
    times.sort((a, b) => a - b)
    const p50 = times[7]
    const p95 = times[14]
    rows.push(
      `${n} parts (${view.nodes.length} nodes, ${view.edges.length} edges): p50 ${p50.toFixed(1)} ms, p95 ${p95.toFixed(1)} ms (layout alone ${layout.toFixed(1)} ms)`,
    )
    medians.push([n, p50])
  }
  console.log(`graph render (jsdom simulation, not a browser; data in hand)\n${rows.join('\n')}`)
  // asserted only after every size is printed, so a failure never hides the other measurements
  for (const [n, p50] of medians) expect(p50, `${n} parts`).toBeLessThan(budget[n])
})
