# LeanCode frontend

React, TypeScript, Vite, and Tailwind CSS are already installed. The application uses the supplied Cue Foundations `cue102` Minimal AI Dev Workspace design, adapted to the existing live backend.

- Component: `src/components/ui/cue-minimal-ai-dev-workspace.tsx`.
- Styles: `src/styles.css`, with the supplied `dw-*` scoped design classes.
- Entry/demo: `src/App.tsx` renders the integrated component.
- Alias: `@/*` resolves to `src/*` in TypeScript and Vite.

`components/ui` keeps reusable UI in the conventional location expected by shadcn-style components. This design uses plain React and the installed Lucide icons; it needs no additional UI package, context provider, stock photography, or external font request. System font fallbacks keep assets local.

If you want to add shadcn primitives later, use the [existing Vite project setup](https://ui.shadcn.com/docs/installation/vite): run `npx shadcn@latest init` from this directory, select `src/styles.css`, and keep the existing `@/components` and `@/components/ui` aliases. Review any stylesheet changes before accepting them. A `components.json` is optional for a copy-and-paste component and required for CLI-managed components; see the [official configuration reference](https://ui.shadcn.com/docs/components-json).

The reference's mock replies, simulated reasoning, hardcoded Claude label, example repositories, deployments, and document counts have been replaced with real sessions, registered repositories, actual model usage, approval controls, and truthful empty states. Unimplemented file-upload, branch switching, and deployment controls are not displayed. Workflow cards prefill a task and never start paid work by themselves.

Run `npm run dev`, `npm run build`, and `npm run test:e2e` from this directory. Browser tests use disposable scripted model replies with real backend/Docker operations on isolated ports 5174 and 8001. They do not spend provider credits or disturb the live app.
