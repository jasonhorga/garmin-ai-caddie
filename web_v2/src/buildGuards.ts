// Build-time SECURITY guards. Pure functions (no DOM / no import.meta) so they can
// be unit-tested here AND imported by vite.config.ts to fail `vite build`.

export interface ConsumerAdminTokenGuardEnv {
  /** VITE_AI_CADDIE_DEFAULT_ADMIN_TOKEN — baked into the shipped JS when set. */
  bakedAdminToken?: string
  /** VITE_AI_CADDIE_REQUIRE_LINK — "true" marks a consumer/public (link-gated) build. */
  requireLink?: string
}

/**
 * True when a consumer/public build would bake the owner admin token into the
 * shipped JS. `VITE_AI_CADDIE_REQUIRE_LINK=true` means the build is for a public
 * deployment where every visitor downloads the bundle; baking the high-privilege
 * admin token there hands it to everyone. The owner's PRIVATE homeserver build DOES
 * bake the token but leaves REQUIRE_LINK unset, so it is allowed.
 */
export function isConsumerBuildWithBakedAdminToken(env: ConsumerAdminTokenGuardEnv): boolean {
  const baked = (env.bakedAdminToken ?? '').trim()
  const requireLink = (env.requireLink ?? '').trim().toLowerCase() === 'true'
  return baked.length > 0 && requireLink
}

/**
 * Throw (failing the build) when a consumer build bakes an admin token. Called from
 * the vite.config build-only plugin; a no-op for the owner homeserver build and for
 * dev/CI builds that set neither variable.
 */
export function assertNoConsumerAdminToken(env: ConsumerAdminTokenGuardEnv): void {
  if (isConsumerBuildWithBakedAdminToken(env)) {
    throw new Error(
      'Refusing to build: VITE_AI_CADDIE_DEFAULT_ADMIN_TOKEN is set while ' +
        'VITE_AI_CADDIE_REQUIRE_LINK=true. A consumer/public build must NEVER bake the ' +
        'owner admin token into the shipped JS — every visitor could read it and act as ' +
        'the owner. Unset VITE_AI_CADDIE_DEFAULT_ADMIN_TOKEN for the consumer build; it is ' +
        "only for the owner's private homeserver build, which leaves VITE_AI_CADDIE_REQUIRE_LINK unset.",
    )
  }
}
