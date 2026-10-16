# Local Docker H3 rollout correction — 2026-10-16

The owner reported that enabling H3 on `http://localhost:3000` displayed no overlay.
Reproduced in the browser: checked H3 showed statistics unavailable. The same request
to `/api/v1/routing/departure-heatmap?resolution=9` returned HTTP 404 through frontend
3000 and each API port 8000/8002/8003/8004. Existing images predated H3 endpoints.

Code work remains in `feat/route-weight-calibration`. The root checkout is `main`;
Docker frontend bind-mounts its static UI, while API code is copied into images.
An empty `git diff main feat/route-weight-calibration -- backend/app` confirmed
that current application source agrees. No merge or application-code edit was needed.

Rebuilt four API images using the existing root Compose project and its existing
`runtime/journey-scale/local.env`. Verified new-image H3/recommendation registration,
recreated only API containers, then reloaded Nginx to refresh upstream addresses.
No data-plane volume recreation, schema change or ranking-weight change.

All four API readiness checks returned 200. H3 through all four API ports and
frontend 3000 returned 200 / AVAILABLE with **2,950 cells** at verification time.
Browser H3 toggle rendered the map overlay and showed `2950 ô đã nạp · H3-9`.
Local screenshot: `runtime/guided-quality-20261015/h3-docker-fixed.png` in this worktree.
Counts vary with the rolling seven-day window. This is local integration evidence,
not a new production load or field-accuracy test.
