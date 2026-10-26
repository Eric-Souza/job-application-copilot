# Web

React + TypeScript + Vite + MUI front end for the API in `apps/api`.

```bash
npm install
npm run dev      # http://localhost:5173, proxies /api to the API on localhost:8000
npm test         # Vitest + Testing Library
npm run lint     # oxlint and Prettier
npm run build
```

Set `VITE_API_URL` to call the API somewhere other than `/api` (it then needs that origin in the API's `CORS_ORIGINS`).

## How it follows a run

A run executes in segments: from the start (or a review decision, or a retry) until it pauses for review, finishes, or fails. `followRun` (in `src/api/client.ts`) opens the run's SSE stream for one segment: a `status` event with the run as it is, `step` and `node` events as steps start and finish, then `review`, `done`, or `error`, after which the stream is closed so EventSource doesn't reconnect. `useRun` reloads the run on those events and follows it again after each action. Progress combines the steps the server reports as finished with the live events, so a page opened mid-run still shows what's done.
