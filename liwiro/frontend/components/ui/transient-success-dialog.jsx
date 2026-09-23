"use client"

import { CheckCircle2 } from "lucide-react"

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"

export function TransientSuccessDialog({ status, onOpenChange }) {
  const open = Boolean(status?.visible && String(status?.state || "").trim() === "success" && String(status?.presentation || "").trim() === "modal")

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md border-emerald-200 bg-white/95 dark:border-emerald-500/30 dark:bg-[#08111c]">
        <DialogHeader className="items-center text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-300">
            <CheckCircle2 className="h-7 w-7" />
          </div>
          <DialogTitle className="pt-2 text-slate-900 dark:text-white">
            {status?.title || status?.label || "Completed successfully"}
          </DialogTitle>
          <DialogDescription className="text-slate-600 dark:text-slate-300">
            {status?.detail || "The operation finished successfully."}
          </DialogDescription>
        </DialogHeader>
      </DialogContent>
    </Dialog>
  )
}

