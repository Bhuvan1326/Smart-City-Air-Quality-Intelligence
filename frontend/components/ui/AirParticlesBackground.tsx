"use client";

import { useMemo } from "react";

/**
 * Small deterministic PRNG (mulberry32) so particle layout is identical on
 * every render -- including the very first server render -- instead of being
 * re-rolled with Math.random() on each re-render or mismatching between
 * server and client hydration.
 */
function mulberry32(seed: number) {
  return function random() {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

type ParticleTier = "base" | "md" | "lg";

interface Particle {
  id: number;
  leftVw: number;
  size: number;
  duration: number;
  delay: number;
  driftX: number;
  opacity: number;
  color: string;
  tier: ParticleTier;
}

/** Blue / cyan / soft-green / neutral, in line with the AirIQ brand palette. */
const PARTICLE_COLORS = [
  "hsl(217 72% 58%)",
  "hsl(199 85% 60%)",
  "hsl(158 50% 52%)",
  "hsl(212 16% 68%)",
];

const TOTAL_PARTICLES = 36;
const SEED = 88172645;

/**
 * Generates the full particle set once. The first 12 are the "base" tier
 * (shown on every viewport), the next 12 are "md" (tablet and up), and the
 * last 12 are "lg" (desktop only) -- so density scales up with screen size
 * via CSS breakpoints alone, with no resize listener or client-only state.
 */
function generateParticles(): Particle[] {
  const random = mulberry32(SEED);
  const particles: Particle[] = [];

  for (let i = 0; i < TOTAL_PARTICLES; i += 1) {
    const tier: ParticleTier = i < 12 ? "base" : i < 24 ? "md" : "lg";
    particles.push({
      id: i,
      leftVw: random() * 100,
      size: 3 + random() * 6,
      duration: 20 + random() * 22,
      delay: -(random() * 32),
      driftX: (random() - 0.5) * 110,
      opacity: 0.1 + random() * 0.26,
      color: PARTICLE_COLORS[Math.floor(random() * PARTICLE_COLORS.length)],
      tier,
    });
  }

  return particles;
}

// Computed once at module scope -- shared by every mount, never regenerated
// on re-render.
const PARTICLES = generateParticles();

const TIER_VISIBILITY_CLASS: Record<ParticleTier, string> = {
  base: "",
  md: "hidden sm:block",
  lg: "hidden lg:block",
};

/**
 * Subtle animated atmospheric background: small floating particles evoking
 * air / PM2.5 / wind movement behind the login card.
 *
 * Purely decorative -- `aria-hidden` and `pointer-events-none` throughout so
 * it's invisible to assistive tech and never intercepts clicks on the form
 * above it. Motion is driven entirely by the `air-particle` /
 * `float-particle` CSS in globals.css, which is already disabled by the
 * project-wide `prefers-reduced-motion` rule there.
 */
export function AirParticlesBackground() {
  const particles = useMemo(() => PARTICLES, []);

  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-0 overflow-hidden"
    >
      {particles.map((particle) => (
        <span
          key={particle.id}
          className={`air-particle ${TIER_VISIBILITY_CLASS[particle.tier]}`}
          style={
            {
              left: `${particle.leftVw}vw`,
              width: `${particle.size}px`,
              height: `${particle.size}px`,
              backgroundColor: particle.color,
              "--particle-opacity": particle.opacity,
              "--particle-duration": `${particle.duration}s`,
              "--particle-delay": `${particle.delay}s`,
              "--particle-drift-x": `${particle.driftX}px`,
            } as React.CSSProperties
          }
        />
      ))}
    </div>
  );
}
