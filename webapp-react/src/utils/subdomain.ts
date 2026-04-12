/**
 * Resolve the founder slug from the current hostname.
 *
 * Returns:
 *   - "sharath" for sharath.tagent.club
 *   - null for tagent.club, localhost, 127.0.0.1, or any IP
 *
 * When this returns null, the app is in "unscoped" (dev/admin) mode and
 * the existing local-dev workflow runs unchanged.
 */
export function getSubdomainSlug(): string | null {
  if (typeof window === 'undefined') return null
  const host = window.location.hostname
  if (!host) return null
  if (host === 'tagent.club') return null
  if (host === 'localhost' || host === '127.0.0.1' || host === '0.0.0.0') return null
  if (/^\d/.test(host)) return null // bare IP
  if (host.endsWith('.localhost')) return null

  const parts = host.split('.')
  // sharath.tagent.club → ["sharath","tagent","club"]
  if (parts.length >= 3 && parts.slice(-2).join('.') === 'tagent.club') {
    return parts[0]
  }
  return null
}
