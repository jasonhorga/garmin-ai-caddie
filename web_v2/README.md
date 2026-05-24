# AI Caddie Web v2

React + Vite + TypeScript frontend for the AI Caddie v2 product surface.

## Runtime

Use Node 24 LTS. The expected version is declared in `.nvmrc` and
`package.json`.

## Commands

```bash
npm install
npm run dev
npm test -- --run --passWithNoTests
npm run build
npm run lint
```

The Vite dev server expects the v2 API server at `http://127.0.0.1:9000` and
proxies `/api` requests there.
