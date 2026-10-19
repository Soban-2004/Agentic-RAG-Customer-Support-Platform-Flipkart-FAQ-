# Aster frontend

A cinematic customer-support interface built with React, TypeScript, Vite, Tailwind CSS, and Framer Motion.

## Run locally

From this directory:

```powershell
npm install
npm run dev
```

The Vite server proxies `/api` and `/ws` to the FastAPI backend on port 8000. Without the backend, chat displays an offline state; login and registration require the backend too.

## Checks

```powershell
npm run build
npm run lint
```

## Design

The UI has an independent Aster identity. Flipkart remains the subject of the assistant's policies and demonstration orders. See `../DESIGN.md` for the palette, typography, layout, and motion rules, and `../PRODUCT.md` for product constraints.

Dark is the initial theme for new visitors. Explicit light, dark, and system choices are saved locally. CSS motion and Framer Motion respect reduced-motion preferences.

Browser review images live in `../.impeccable/review/`. Conversation preview images contain explicitly labeled test responses and do not establish backend correctness.
