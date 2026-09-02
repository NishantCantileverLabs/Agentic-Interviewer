/** The session/auth layer is shared with the legacy surfaces — one token,
 * one source of truth. Re-exported here so platform code imports from lib/. */
export {
  API,
  authFetch,
  authHeaders,
  getToken,
  homeFor,
  logout,
  setToken,
  useUser,
} from "../app/lib/auth";
export type { AuthUser } from "../app/lib/auth";
