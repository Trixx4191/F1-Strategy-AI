# F1 Strategy frontend

React and TypeScript application served by the FastAPI backend in production.
The AWS demo is restricted to the bundled 2024 Bahrain race.

```sh
npm ci
npm run dev
```

The Vite development server forwards `/api` to `http://127.0.0.1:8000`.
Start the backend from the repository root:

```sh
F1_DEMO_MODE=true venv/bin/python -m uvicorn backend.main:app --port 8000
```

For the deployed demo build:

```sh
VITE_DEMO_MODE=true npm run build
npm test
```

`npm test` checks chronological tyre sequences and race-time formatting using
Node's built-in test runner and TypeScript stripping (Node 22.6 or newer).

`App.tsx` owns the simulation settings, completed-run state, tab navigation,
and browser-local saves. Only the active tab mounts. `Charts.tsx` renders SVG
charts from completed results; opening analysis tabs does not run simulations.
`f1ui.ts` provides compound styling, ordered stint extraction, and time formatting.
`index.css` defines the shared layout and responsive breakpoints.

See [UI refresh notes](../docs/ui-refresh.md) for the design decisions and checks,
and [AWS deployment notes](../docs/aws-demo.md) for release and rollback steps.
