/**
 * API base URL for backend requests.
 *
 * - Vercel Services: NEXT_PUBLIC_BACKEND_URL is auto-injected as "/backend"
 * - Local dev: talks directly to FastAPI on port 8000
 * - Override anytime with NEXT_PUBLIC_API_URL
 */
export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ??
  "/api";
