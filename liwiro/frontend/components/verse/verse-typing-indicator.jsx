"use client"

export default function VerseTypingIndicator({ label = "Verse Chat is thinking…" }) {
  return (
    <div className="mr-10 max-w-[22rem] rounded-[1.35rem] border border-white/10 bg-white/[0.06] px-4 py-3 text-sm text-slate-200 shadow-[0_14px_36px_rgba(0,0,0,0.18)]">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">{label}</p>
      <div className="mt-3 flex items-center gap-2">
        <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-sky-200/80" />
        <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-sky-200/65 [animation-delay:150ms]" />
        <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-sky-200/50 [animation-delay:300ms]" />
      </div>
    </div>
  )
}
