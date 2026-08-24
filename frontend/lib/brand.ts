/** Brand + contact identity, configured per deployment (never hardcoded in
 * screens). NEXT_PUBLIC_* values are baked at build time. */
export const ORG_NAME = process.env.NEXT_PUBLIC_ORG_NAME ?? "AI Interview";
export const CONTACT_EMAIL =
  process.env.NEXT_PUBLIC_CONTACT_EMAIL ?? "talent@example.dev";
