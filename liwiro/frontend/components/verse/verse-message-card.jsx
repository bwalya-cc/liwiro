"use client"

import { ChevronDown, ChevronUp } from "lucide-react"
import Link from "next/link"
import { useState } from "react"

import { MarkdownDocument } from "@/components/ide/markdown-document"
import VerseActionCard from "@/components/verse/verse-action-card"
import VerseVisualizationCard from "@/components/verse/verse-visualization-card"
import { Button } from "@/components/ui/button"

const AGENT_STYLES = {
  blue: "border-sky-400/18 bg-sky-500/[0.13] text-sky-50",
  teal: "border-teal-400/18 bg-teal-500/[0.13] text-teal-50",
  amber: "border-amber-400/18 bg-amber-500/[0.13] text-amber-50",
  violet: "border-violet-400/18 bg-violet-500/[0.13] text-violet-50",
  slate: "border-slate-300/12 bg-white/[0.06] text-slate-100",
}

const LABEL_STYLES = {
  blue: "text-sky-200",
  teal: "text-teal-200",
  amber: "text-amber-200",
  violet: "text-violet-200",
  slate: "text-slate-300",
}

function styleToken(token) {
  return AGENT_STYLES[String(token || "slate").trim()] || AGENT_STYLES.slate
}

function labelToken(token) {
  return LABEL_STYLES[String(token || "slate").trim()] || LABEL_STYLES.slate
}

function confidenceLabel(message) {
  const confidence = String(message?.confidence || "").trim()
  if (!confidence) return ""
  return confidence
}

export default function VerseMessageCard({
  message,
  onApplyArtifact,
  onExecuteArtifact,
  onSaveExecuteArtifact,
  applyBusy = false,
  executeBusy = false,
  saveExecuteBusy = false,
  userDisplayName = "",
}) {
  const [showInspect, setShowInspect] = useState(false)
  const role = String(message?.role || "")
  const isUser = role === "user"
  const isSystem = role === "system"
  const isAgent = role === "agent" || role === "assistant"
  const contentType = String(message?.contentType || message?.content_type || "message")
  const token = String(message?.styleToken || message?.agent?.styleToken || "slate")
  const agentDisplayName =
    message?.agentDisplayName || message?.agent?.displayName || message?.agentName || message?.agent?.name || "Verse Chat Agent"
  const agentTitle = message?.agentTitle || message?.agent?.title || ""
  const inspectDetails = message?.inspectDetails && typeof message.inspectDetails === "object" ? message.inspectDetails : {}
  const retrievalTrace = Array.isArray(message?.retrievalTrace) ? message.retrievalTrace : []
  const manualLinks = Array.isArray(inspectDetails?.manualLinks) ? inspectDetails.manualLinks : []
  const contextReport = inspectDetails?.contextReport && typeof inspectDetails.contextReport === "object" ? inspectDetails.contextReport : {}
  const promptMode = String(inspectDetails?.promptMode || contextReport?.promptMode || "").trim()
  const bootstrapFiles = Array.isArray(inspectDetails?.bootstrapFiles) ? inspectDetails.bootstrapFiles : []
  const truncationWarnings = Array.isArray(inspectDetails?.truncationWarnings) ? inspectDetails.truncationWarnings : []
  const handoffChain = Array.isArray(inspectDetails?.handoffChain) ? inspectDetails.handoffChain : []
  const synthesisParticipants = Array.isArray(inspectDetails?.synthesisParticipants) ? inspectDetails.synthesisParticipants : []
  const contextEntries = Array.isArray(contextReport?.entries) ? contextReport.entries : []
  const planning = inspectDetails?.planning && typeof inspectDetails.planning === "object" ? inspectDetails.planning : {}
  const supportingBlocks = Array.isArray(message?.supportingBlocks) ? message.supportingBlocks : []
  const contributors = Array.isArray(message?.contributors) ? message.contributors : []
  const primaryCard = message?.primaryCard && typeof message.primaryCard === "object" ? message.primaryCard : null
  const hasInspect = retrievalTrace.length > 0 || Object.keys(inspectDetails).length > 0 || manualLinks.length > 0
  const markdownClassName =
    "break-words [&_p]:text-inherit [&_p]:leading-7 [&_ul]:text-inherit [&_ol]:text-inherit [&_li]:text-inherit [&_code]:break-words [&_code]:text-sky-100 [&_pre]:max-w-full [&_pre]:overflow-x-auto [&_pre]:border-white/10 [&_pre]:bg-black/20 [&_a]:break-words [&_a]:text-sky-200"

  if (isSystem) {
    return (
      <div className="mx-auto max-w-[42rem] rounded-[1.2rem] border border-dashed border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-slate-300">
        <p className="font-semibold uppercase tracking-[0.18em] text-slate-500">Verse Chat Event</p>
        <MarkdownDocument content={String(message?.content || "")} className={`mt-2 ${markdownClassName}`} />
      </div>
    )
  }

  if (isUser) {
    const resolvedUserDisplayName =
      String(message?.userDisplayName || "").trim()
      || String(userDisplayName || "").trim()
      || "User"
    return (
      <div className="flex justify-end">
        <div className="min-w-0 max-w-[85%] overflow-hidden rounded-[1.45rem] border border-emerald-400/15 bg-emerald-500/[0.12] px-4 py-3 text-sm text-emerald-50 shadow-[0_16px_40px_rgba(0,0,0,0.16)]">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-200">{resolvedUserDisplayName}</p>
          <MarkdownDocument content={String(message?.content || "")} className={`mt-2 ${markdownClassName}`} />
        </div>
      </div>
    )
  }

  return (
    <div className="flex justify-start">
      <div
        className={`min-w-0 max-w-[88%] overflow-hidden rounded-[1.45rem] border px-4 py-3 text-sm shadow-[0_16px_40px_rgba(0,0,0,0.18)] transition-all duration-200 ${styleToken(token)}`}
        style={{ animation: "verseChatPop 180ms ease-out" }}
      >
        <div className="flex flex-wrap items-center gap-2">
          <p className={`text-[11px] font-semibold uppercase tracking-[0.18em] ${labelToken(token)}`}>{agentDisplayName}</p>
          {agentTitle ? <span className="text-[11px] text-white/60">{agentTitle}</span> : null}
          {contentType === "synthesis" ? (
            <span className="rounded-full border border-white/10 px-2 py-0.5 text-[10px] uppercase tracking-[0.18em] text-white/70">
              Synthesis
            </span>
          ) : null}
          {contentType === "plan" ? (
            <span className="rounded-full border border-white/10 px-2 py-0.5 text-[10px] uppercase tracking-[0.18em] text-white/70">
              Plan
            </span>
          ) : null}
          {confidenceLabel(message) ? (
            <span className="rounded-full border border-white/10 px-2 py-0.5 text-[10px] uppercase tracking-[0.18em] text-white/55">
              {confidenceLabel(message)}
            </span>
          ) : null}
        </div>
        {contributors.length > 0 ? (
          <div className="mt-2 flex flex-wrap gap-2">
            {contributors.slice(0, 4).map((item, index) => (
              <span key={`contributor-${index}`} className="rounded-full border border-white/10 px-2 py-0.5 text-[10px] uppercase tracking-[0.16em] text-white/65">
                {item?.displayName || item?.agentId || "Contributor"}{item?.role ? ` · ${item.role}` : ""}
              </span>
            ))}
          </div>
        ) : null}
        {isAgent ? <MarkdownDocument content={String(message?.content || "")} className={`mt-2 ${markdownClassName}`} /> : null}

        {primaryCard && !message?.artifact && !message?.visualization ? (
          <div className="mt-3 overflow-hidden rounded-[1.2rem] border border-white/10 bg-black/15 px-4 py-4">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-semibold text-white">{primaryCard?.title || "Verse Card"}</p>
              {primaryCard?.type ? (
                <span className="rounded-full border border-white/10 px-2 py-0.5 text-[10px] uppercase tracking-[0.16em] text-white/60">
                  {String(primaryCard.type).replace(/-/g, " ")}
                </span>
              ) : null}
            </div>
            {primaryCard?.description ? <p className="mt-1 text-xs text-slate-300">{primaryCard.description}</p> : null}
          </div>
        ) : null}

        <VerseVisualizationCard visualization={message?.visualization} />

        {message?.artifact ? (
          <VerseActionCard
            artifact={message.artifact}
            onApply={() => onApplyArtifact?.(message)}
            onExecute={() => onExecuteArtifact?.(message)}
            onSaveExecute={() => onSaveExecuteArtifact?.(message)}
            applyBusy={applyBusy}
            executeBusy={executeBusy}
            saveExecuteBusy={saveExecuteBusy}
          />
        ) : null}

        {supportingBlocks.length > 0 ? (
          <div className="mt-3 space-y-3">
            {supportingBlocks.map((block, index) => {
              const type = String(block?.type || "").trim()
              if (type === "checklist") {
                const items = Array.isArray(block?.items) ? block.items : []
                return (
                  <div key={`block-${index}`} className="rounded-[1.1rem] border border-white/10 bg-black/15 px-4 py-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-300">{block?.title || "Checklist"}</p>
                    <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-200">
                      {items.map((item, itemIndex) => <li key={`check-${itemIndex}`}>{item}</li>)}
                    </ul>
                  </div>
                )
              }
              if (type === "table") {
                const columns = Array.isArray(block?.columns) ? block.columns : []
                const rows = Array.isArray(block?.rows) ? block.rows : []
                return (
                  <div key={`block-${index}`} className="overflow-hidden rounded-[1.1rem] border border-white/10 bg-black/15">
                    <div className="border-b border-white/10 px-4 py-3 text-xs font-semibold uppercase tracking-[0.16em] text-slate-300">{block?.title || "Table"}</div>
                    <div className="overflow-x-auto px-4 py-3">
                      <table className="min-w-full text-left text-xs text-slate-200">
                        <thead>
                          <tr>{columns.map((column) => <th key={column} className="pb-2 pr-4 font-semibold text-slate-400">{column}</th>)}</tr>
                        </thead>
                        <tbody>
                          {rows.slice(0, 5).map((row, rowIndex) => (
                            <tr key={`row-${rowIndex}`}>{columns.map((column) => <td key={`${rowIndex}-${column}`} className="py-1 pr-4 align-top">{String(row?.[column] ?? "—")}</td>)}</tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )
              }
              if (type === "evidence-panel") {
                const items = Array.isArray(block?.items) ? block.items : []
                return (
                  <div key={`block-${index}`} className="rounded-[1.1rem] border border-white/10 bg-black/15 px-4 py-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-300">{block?.title || "Evidence"}</p>
                    <div className="mt-2 space-y-1 text-sm text-slate-200">
                      {items.map((item, itemIndex) => <p key={`evidence-${itemIndex}`}>• {item}</p>)}
                    </div>
                  </div>
                )
              }
              return (
                <div key={`block-${index}`} className="rounded-[1.1rem] border border-white/10 bg-black/15 px-4 py-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-300">{block?.title || "Callout"}</p>
                  <MarkdownDocument content={String(block?.body || "")} className={`mt-2 ${markdownClassName}`} />
                </div>
              )
            })}
          </div>
        ) : null}

        {hasInspect ? (
          <div className="mt-3 border-t border-white/8 pt-3">
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-7 rounded-full px-2 text-[11px] uppercase tracking-[0.16em] text-white/60"
              onClick={() => setShowInspect((current) => !current)}
            >
              {showInspect ? <ChevronUp className="mr-1.5 h-3.5 w-3.5" /> : <ChevronDown className="mr-1.5 h-3.5 w-3.5" />}
              Inspect
            </Button>
            {showInspect ? (
              <div className="mt-3 space-y-3 rounded-[1rem] border border-white/10 bg-black/15 px-3 py-3 text-xs text-slate-300">
                {Array.isArray(retrievalTrace) && retrievalTrace.length > 0 ? (
                  <div>
                    <p className="font-semibold uppercase tracking-[0.16em] text-slate-400">Context</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {retrievalTrace.slice(0, 6).map((trace, index) => (
                        <span
                          key={`${message?.id || "message"}-trace-${index}`}
                          className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[10px] uppercase tracking-[0.16em] text-white/70"
                          title={trace?.reason || ""}
                        >
                          {trace?.source || "context"}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}
                {inspectDetails?.provider ? (
                  <div>
                    <p className="font-semibold uppercase tracking-[0.16em] text-slate-400">Runtime</p>
                    <p className="mt-1 text-slate-300">
                      {inspectDetails.provider.id} · {inspectDetails.provider.model}
                    </p>
                    {promptMode ? <p className="mt-1 text-slate-400">Prompt mode: {promptMode}</p> : null}
                    {inspectDetails?.usage?.totalTokens ? (
                      <p className="mt-1 text-slate-400">Tokens: {inspectDetails.usage.totalTokens}</p>
                    ) : null}
                    {contextReport?.totalBlocks ? (
                      <p className="mt-1 text-slate-400">
                        Context blocks: {contextReport.totalBlocks} · Approx chars: {contextReport.approximateChars || 0}
                      </p>
                    ) : null}
                  </div>
                ) : null}
                {bootstrapFiles.length > 0 || contextEntries.length > 0 ? (
                  <div>
                    <p className="font-semibold uppercase tracking-[0.16em] text-slate-400">Prompt Assembly</p>
                    {bootstrapFiles.length > 0 ? (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {bootstrapFiles.map((fileName) => (
                          <span
                            key={`${message?.id || "message"}-bootstrap-${fileName}`}
                            className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[10px] uppercase tracking-[0.16em] text-white/75"
                          >
                            {fileName}
                          </span>
                        ))}
                      </div>
                    ) : null}
                    {contextEntries.length > 0 ? (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {contextEntries.slice(0, 8).map((entry, index) => (
                          <span
                            key={`${message?.id || "message"}-entry-${index}`}
                            className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[10px] text-white/65"
                            title={entry?.reason || ""}
                          >
                            {entry?.label || entry?.source || "context"}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                {inspectDetails?.routingReason ? (
                  <div>
                    <p className="font-semibold uppercase tracking-[0.16em] text-slate-400">Routing</p>
                    <p className="mt-1 text-slate-300">{inspectDetails.routingReason}</p>
                  </div>
                ) : null}
                {handoffChain.length > 0 ? (
                  <div>
                    <p className="font-semibold uppercase tracking-[0.16em] text-slate-400">Handoff Chain</p>
                    <div className="mt-2 space-y-1 text-slate-300">
                      {handoffChain.map((step, index) => (
                        <p key={`${message?.id || "message"}-handoff-${index}`}>
                          {step?.sourceAgentName || step?.sourceAgentId || "Agent"}
                          {" -> "}
                          {step?.targetAgentName || step?.targetAgentId || "Agent"}
                          {": "}
                          {step?.reason || "Specialist follow-up"}
                        </p>
                      ))}
                    </div>
                  </div>
                ) : null}
                {synthesisParticipants.length > 0 ? (
                  <div>
                    <p className="font-semibold uppercase tracking-[0.16em] text-slate-400">Participants</p>
                    <p className="mt-1 text-slate-300">{synthesisParticipants.join(", ")}</p>
                  </div>
                ) : null}
                {truncationWarnings.length > 0 ? (
                  <div>
                    <p className="font-semibold uppercase tracking-[0.16em] text-slate-400">Truncation</p>
                    <div className="mt-2 space-y-1 text-amber-100/80">
                      {truncationWarnings.map((warning, index) => (
                        <p key={`${message?.id || "message"}-warning-${index}`}>{warning}</p>
                      ))}
                    </div>
                  </div>
                ) : null}
                {Object.keys(planning).length > 0 ? (
                  <div>
                    <p className="font-semibold uppercase tracking-[0.16em] text-slate-400">Plan</p>
                    {planning?.currentGoal ? <p className="mt-1 text-slate-300">{planning.currentGoal}</p> : null}
                    {Array.isArray(planning?.missingDecisions) && planning.missingDecisions.length > 0 ? (
                      <div className="mt-2">
                        <p className="text-[10px] uppercase tracking-[0.16em] text-white/55">Missing Decisions</p>
                        <ul className="mt-1 list-disc space-y-1 pl-4 text-slate-300">
                          {planning.missingDecisions.slice(0, 5).map((item, index) => (
                            <li key={`planning-missing-${index}`}>{item}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    {inspectDetails?.nextStep ? (
                      <div className="mt-2">
                        <p className="text-[10px] uppercase tracking-[0.16em] text-white/55">Next Step</p>
                        <p className="mt-1 text-slate-300">{inspectDetails.nextStep}</p>
                      </div>
                    ) : null}
                  </div>
                ) : null}
                {manualLinks.length > 0 ? (
                  <div>
                    <p className="font-semibold uppercase tracking-[0.16em] text-slate-400">Follow Along</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {manualLinks.slice(0, 4).map((link) => (
                        <Link
                          key={`${link.href}-${link.title}`}
                          href={link.href}
                          className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[10px] uppercase tracking-[0.16em] text-white/75 hover:bg-white/10"
                        >
                          {link.title}
                        </Link>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}
        <style jsx>{`
          @keyframes verseChatPop {
            from {
              opacity: 0;
              transform: translateY(8px);
            }
            to {
              opacity: 1;
              transform: translateY(0);
            }
          }
        `}</style>
      </div>
    </div>
  )
}
