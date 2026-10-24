# F1 UI refresh — 24 October 2026

The interface is organised around a race-strategy decision: choose a driver,
compare pit-stop strategies, inspect uncertainty, and test a rival scenario.
The production demo still uses the bundled 2024 Bahrain race and the existing
Python simulation engine. It does not provide live race telemetry.

## Layout and visual changes

- The overview leads with the lowest expected race-time strategy, chronological
  tyre stints, pit laps, race-time variability, and estimated pit loss.
- The five leading strategies show their gap to the best result, making small
  differences visible without repeatedly printing ambiguous win-rate figures.
- Historical classification is available in a collapsed section. The desktop
  circuit panel shows the outline without invented car positions.
- A flat charcoal palette, restrained red accent, system fonts, consistent
  borders, and clearer spacing replace glows, pulsing status indicators,
  decorative gradients, and the external font dependency.
- The sidebar groups race setup and simulation options. Less frequently used
  parameters live under Advanced settings. On phones, Settings opens the form
  without placing the whole form above the results on every visit.
- Navigation remains scrollable on narrow screens. Wide data tables scroll
  within their panel rather than widening the entire page.
- Focus indicators, a skip link, labelled controls, notification roles, and
  reduced-motion styling support keyboard and assistive-technology use.
- Template CSS, React/Vite logos, an unused hero asset, and the template icon
  sprite were removed. The favicon now matches the application.

## Features simplified or removed

- Removed the artificial multi-car overview replay. It spaced drivers around
  the circuit using field offsets rather than their individual race traces.
- Retained the two-car backtest and rival replays that use lap-time traces.
  They start paused, sit behind expandable replay sections, and are explicitly
  described as illustrative simulations.
- Removed “Mission Control”, misleading “LIVE” labels, “AI Recommendation”,
  framework/parity commentary, duplicate weather displays, and repeated
  driver/tyre summary panels.
- Replaced duplicate browser/backend CSV buttons with one complete download.
  Backend CSV and plotting endpoints remain available.
- Replaced automatic PNG generation and extra rival scans in Pit windows with
  charts derived from the completed run. Backtest also renders its existing
  trace directly rather than requesting a redundant server plot.
- Saved comparisons show strategy, time, pit laps, and simulation settings.
  Decorative winner badges and relative win-rate progress bars were removed.

## Behaviour and correctness

Only the selected analysis tab mounts. Opening the app or browsing completed
analysis does not submit simulation, rival-analysis, or plot POST requests.
Fresh calculations require an explicit Run simulation or Run rival analysis.
This reduces unnecessary work on the shared VM.

Results have compound/pit-lap search, one/two-stop filtering, and 30-row
pagination. CSV exports every strategy, including rows outside the current
page or filter, with the completed run's driver/race in its filename.

Tyre sequences prefer chronological stints from the strategy text. A compound
summary such as `HARD + SOFT` previously appeared as one incorrect badge; the
initial strategy now correctly displays `SOFT → HARD → HARD`, with pit laps
20 and 38. Race-time formatting correctly carries rounded seconds into
minutes and hours.

Completed-run settings are stored separately from editable settings. Changing
inputs shows a pending-settings notice while retaining the completed run's
driver and iteration count. Saving is disabled until those changes are applied.
Loading a saved run restores its matching settings. A failed simulation keeps
the previous completed results available. Reset clears results without discarding
already loaded race metadata.

Saved runs remain local to the browser. Storage failures produce an error
instead of a false success message. Comparisons between different drivers or
races explicitly state that total times are not directly comparable.

## Validation

The production build passed TypeScript checking and Vite bundling. The existing
backend suite passed all 122 tests.
`npm test --prefix frontend` checks chronological tyre sequences, legacy
sequence fallback, empty data, and race-time rounding boundaries.

Browser verification passed locally and against the public HTTPS deployment.
It uses installed Chromium with a temporary Playwright driver,
without adding a browser dependency to the application. It checks initial
network traffic, all analysis sections, result search/filter/pagination, complete
CSV content, fresh simulation, rival analysis, saving/comparing/loading runs,
replay controls, mobile settings, and reload persistence. Responsive checks cover
1440, 1024, 768, 390, and 320-pixel widths.

To reproduce the browser checks (these submit one simulation and one rival scan):

```sh
npm install --prefix /tmp/f1-ui-browser playwright
NODE_PATH=/tmp/f1-ui-browser/node_modules node scripts/smoke_ui.cjs http://127.0.0.1:8000
```

Screenshots and the downloaded CSV are written to `/tmp/f1-ui-check` by default.
Use `UI_ARTIFACT_DIR` to change that location or `CHROMIUM_PATH` to select an
installed Chromium executable.

See [AWS deployment notes](aws-demo.md) for the release ID, live verification,
and rollback procedure.
