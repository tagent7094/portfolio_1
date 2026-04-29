export default function LandingPage() {
  return (
    <div className="grain relative flex min-h-screen flex-col items-center justify-center bg-black px-6 text-center overflow-hidden">
      {/* Background ambient glow */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute left-1/2 top-1/2 h-[700px] w-[700px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-white/[0.015] blur-3xl" />
        <div className="absolute left-1/2 top-1/2 h-[300px] w-[300px] -translate-x-1/2 -translate-y-[60%] rounded-full bg-white/[0.03] blur-2xl" />
      </div>

      <div className="relative z-10 max-w-md animate-slide-up">
        {/* Logo mark */}
        <div className="mb-10 flex justify-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-white shadow-[0_0_40px_rgba(255,255,255,0.08)]">
            <span className="font-[var(--font-display)] text-xl font-bold tracking-tight text-black">T</span>
          </div>
        </div>

        {/* Company name */}
        <h1 className="font-[var(--font-display)] text-[52px] font-semibold tracking-[-0.04em] text-white leading-none mb-5">
          tagent
        </h1>

        {/* Divider */}
        <div className="mx-auto mb-5 h-px w-12 bg-white/15" />

        {/* Tagline */}
        <p className="text-base font-[var(--font-display)] text-white/55 tracking-wide mb-8">
          The intelligence layer for founders.
        </p>

        {/* Description */}
        <p className="text-sm text-white/30 leading-[1.7] mb-12 max-w-xs mx-auto">
          We work with a select group of founders to help them think,
          communicate, and grow with precision. Currently available
          by invitation only.
        </p>

        {/* CTA */}
        <a
          href="mailto:hello@tagent.club"
          className="inline-flex items-center gap-2 rounded-xl bg-white px-7 py-3 text-sm font-semibold text-black transition-all hover:bg-white/90 hover:scale-[1.02] active:scale-[0.98]"
        >
          Get in touch
        </a>
      </div>

      {/* Footer */}
      <p className="absolute bottom-8 text-[11px] text-white/20 tracking-wide">
        © {new Date().getFullYear()} Tagent
      </p>
    </div>
  )
}
