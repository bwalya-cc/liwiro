"use client"

import { X } from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { createPortal } from "react-dom"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

function labelize(value) {
  return String(value || "").replace(/[_-]+/g, " ")
}

function AgentCard({ agent, compact = false, selected = false, onSelect }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full overflow-hidden rounded-[1.2rem] border p-4 text-left transition ${selected ? "border-teal-400/35 bg-teal-400/10" : "border-white/10 bg-white/[0.03] hover:bg-white/[0.06]"}`}
    >
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <p className="text-lg font-semibold text-white">{agent.displayName || agent.name}</p>
          {agent.title ? <Badge variant="secondary">{agent.title}</Badge> : null}
          {agent.theme ? (
            <Badge variant="outline" className="border-white/10 text-slate-300">
              {agent.theme}
            </Badge>
          ) : null}
        </div>
        <p className="text-sm leading-6 text-slate-300">
          {agent.abilitySummary || agent.mission || "Specialist profile available."}
        </p>
      </div>
      <div className="mt-4 flex flex-wrap gap-2 border-t border-white/10 pt-4">
        {(agent.responsibilities || []).slice(0, compact ? 3 : 4).map((item) => (
          <Badge key={`${agent.id}-${item}`} variant="secondary" className="bg-white/10 text-white">
            {labelize(item)}
          </Badge>
        ))}
      </div>
      <div className="mt-4 grid gap-2">
        {(agent.skills || []).slice(0, compact ? 2 : 3).map((skill, index) => (
          <div key={skill.id || `${agent.id}-skill-${skill.title || index}`} className="rounded-2xl border border-white/10 bg-black/20 px-3 py-3">
            <p className="font-semibold text-white">{skill.title}</p>
            {skill.purpose ? <p className="mt-1 text-xs text-slate-400">{skill.purpose}</p> : null}
          </div>
        ))}
      </div>
    </button>
  )
}

function AgentDetail({ agent, compact = false }) {
  if (!agent) return null

  return (
    <div className="space-y-5">
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-lg font-semibold text-white">{agent.displayName || agent.name}</p>
          {agent.title ? <Badge variant="secondary">{agent.title}</Badge> : null}
          {agent.theme ? (
            <Badge variant="outline" className="border-white/10 text-slate-300">
              {agent.theme}
            </Badge>
          ) : null}
        </div>
        <p className="text-sm leading-6 text-slate-300">
          {agent.abilitySummary || agent.mission}
        </p>
      </div>

      <div className="space-y-2">
        <p className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Best For</p>
        <div className="flex flex-wrap gap-2">
          {(agent.responsibilities || []).slice(0, compact ? 4 : 6).map((item) => (
            <Badge key={`${agent.id}-responsibility-${item}`} variant="secondary" className="bg-white/10 text-white">
              {labelize(item)}
            </Badge>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        <p className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Skills</p>
        <div className="grid gap-2">
          {(agent.skills || []).slice(0, compact ? 2 : 3).map((skill, index) => (
            <div key={skill.id || `${agent.id}-skill-${skill.title || index}`} className="rounded-2xl border border-white/10 bg-black/20 px-3 py-3">
              <p className="font-semibold text-white">{skill.title}</p>
              {skill.purpose ? <p className="mt-1 text-xs text-slate-400">{skill.purpose}</p> : null}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function VerseAgentProfilePanel({ agents = [], compact = false, initialAgentId = "", onClose, modal = true }) {
  const [selectedId, setSelectedId] = useState("")
  const [mounted, setMounted] = useState(false)
  const selectedAgent = useMemo(() => {
    const list = Array.isArray(agents) ? agents : []
    return list.find((agent) => agent.id === selectedId) || list[0] || null
  }, [agents, selectedId])

  useEffect(() => {
    setMounted(true)
    return () => setMounted(false)
  }, [])

  useEffect(() => {
    const list = Array.isArray(agents) ? agents : []
    const preferredId = String(initialAgentId || "").trim()
    if (preferredId && list.some((agent) => agent.id === preferredId)) {
      setSelectedId(preferredId)
      return
    }
    setSelectedId((current) => current || String(list[0]?.id || ""))
  }, [agents, initialAgentId])

  useEffect(() => {
    if (!onClose) return undefined
    const handleKeyDown = (event) => {
      if (event.key === "Escape") onClose()
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [onClose])

  if (!Array.isArray(agents) || agents.length === 0) return null

  if (!modal) {
    return (
      <div className="space-y-4">
        <div>
          <p className="text-sm font-semibold text-white">{compact ? "Agent abilities" : "Verse specialists"}</p>
          <p className="mt-1 text-sm text-slate-400">See each specialist’s remit, strongest skills, and best-fit tasks.</p>
        </div>
        <div className="grid gap-3">
          {agents.map((agent) => (
            <AgentCard
              key={agent.id}
              agent={agent}
              compact={compact}
              selected
              onSelect={() => {}}
            />
          ))}
        </div>
      </div>
    )
  }

  if (!mounted) return null

  return createPortal(
    <div className="fixed inset-0 z-[140] flex items-center justify-center p-4 sm:p-6">
      <button
        type="button"
        aria-label="Close abilities modal"
        className="absolute inset-0 bg-[#020817]/80 backdrop-blur-sm"
        onClick={onClose}
      />
      <Card className="relative z-[1] flex max-h-[calc(100vh-2rem)] w-full max-w-2xl flex-col overflow-hidden border-white/10 bg-[#08111c]/98 shadow-[0_30px_120px_rgba(0,0,0,0.5)] sm:max-h-[calc(100vh-3rem)]">
        <CardHeader className="sticky top-0 z-[1] space-y-3 border-b border-white/10 bg-[#08111c]/98 pb-4 backdrop-blur">
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle className="text-white">{compact ? "Agent abilities" : "Verse specialists"}</CardTitle>
              <p className="mt-2 text-sm text-slate-400">See each specialist’s remit, strongest skills, and best-fit tasks.</p>
            </div>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="h-9 w-9 shrink-0 rounded-full border border-white/10 bg-white/5 text-slate-200 hover:bg-white/10"
              onClick={onClose}
              aria-label="Close abilities modal"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
          <div className="flex flex-wrap gap-2">
            {agents.map((agent) => (
              <Button
                key={agent.id}
                type="button"
                size="sm"
                variant={selectedAgent?.id === agent.id ? "default" : "secondary"}
                className="rounded-full"
                onClick={() => setSelectedId(agent.id)}
              >
                {agent.displayName || agent.name}
              </Button>
            ))}
          </div>
        </CardHeader>
        {selectedAgent ? <CardContent className="max-h-[min(72vh,34rem)] overflow-y-auto px-6 py-5"><AgentDetail agent={selectedAgent} compact={compact} /></CardContent> : null}
      </Card>
    </div>,
    document.body
  )
}
