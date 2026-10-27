// Single source for the backend address used by every page.
//
// The production API is the AWS backend behind CloudFront. The old
// NEXT_PUBLIC_API_URL variable is deliberately not read: it is still set on
// the Vercel project to the retired Railway service, and Next.js inlines
// NEXT_PUBLIC_* values at build time, so it silently overrode this default.
// Use NEXT_PUBLIC_ROLE2_API_URL to point a local or preview build elsewhere.
export const API_BASE =
  process.env.NEXT_PUBLIC_ROLE2_API_URL || 'https://api.role2builder.org';
