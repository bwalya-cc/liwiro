// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

"use client"

import { Info } from "lucide-react"

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"

const BLOCKED_MUTATION_COPY = {
  define_domain: {
    title: "Startup schema change blocked",
    detail: "The service tried to create or redefine a VDB domain while Liwiro was only validating the upload.",
    guidance: "Pre-create the domain outside startup, or move this work into an explicit setup step instead of automatic boot logic.",
  },
  define_database: {
    title: "Startup schema change blocked",
    detail: "The service tried to create or redefine a VDB database during dry-run validation.",
    guidance: "Pre-create the database outside startup, or move this work into an explicit setup step instead of automatic boot logic.",
  },
  create_collection: {
    title: "Startup collection creation blocked",
    detail: "The service tried to create a collection during validation.",
    guidance: "Keep upload validation read-only. Create the collection in a setup step or provision it before generation.",
  },
  create_index: {
    title: "Startup index creation blocked",
    detail: "The service tried to create an index during validation.",
    guidance: "Move index creation into provisioning or an explicit admin/setup action.",
  },
  create_script: {
    title: "Startup script creation blocked",
    detail: "The service tried to create or overwrite a stored VDB script during validation.",
    guidance: "Provision stored scripts outside startup or gate them behind a separate setup path.",
  },
  create_document: {
    title: "Startup data write blocked",
    detail: "The service tried to insert seed or runtime data during validation.",
    guidance: "Uploads must validate without changing data. Seed through setup or a separate admin action.",
  },
  update_document: {
    title: "Startup data update blocked",
    detail: "The service tried to update data during validation.",
    guidance: "Move the update into a setup flow or another explicit runtime action.",
  },
  delete_document: {
    title: "Startup data delete blocked",
    detail: "The service tried to delete data during validation.",
    guidance: "Remove destructive startup behavior from the LAPIS upload path.",
  },
  drop_collection: {
    title: "Startup destructive change blocked",
    detail: "The service tried to drop a collection during validation.",
    guidance: "Do not run destructive schema cleanup during startup. Use a separate maintenance path instead.",
  },
  drop_domain: {
    title: "Startup destructive change blocked",
    detail: "The service tried to drop a domain during validation.",
    guidance: "Do not run destructive schema cleanup during startup. Use a separate maintenance path instead.",
  },
  drop_database: {
    title: "Startup destructive change blocked",
    detail: "The service tried to drop a database during validation.",
    guidance: "Do not run destructive schema cleanup during startup. Use a separate maintenance path instead.",
  },
}

function explainLapisUploadError(error) {
  const text = String(error || "").trim()
  if (!text) return null

  const blockedMutationMatch = text.match(/^Startup attempted blocked mutation:\s*([a-z_]+)\s*\((.+)\)$/i)
  if (blockedMutationMatch) {
    const action = String(blockedMutationMatch[1] || "").trim().toLowerCase()
    const target = String(blockedMutationMatch[2] || "").trim()
    const copy = BLOCKED_MUTATION_COPY[action] || {
      title: "Startup mutation blocked",
      detail: "The service tried to mutate VDB state while Liwiro was validating the upload in dry-run mode.",
      guidance: "Move the mutation into an explicit setup step, or provision the resource before generation.",
    }
    return {
      title: copy.title,
      lines: [
        copy.detail,
        target ? `Blocked target: ${target}.` : "",
        "Liwiro dry-runs uploaded LAPIS so validation can inspect startup behavior without changing shared platform state.",
        copy.guidance,
      ].filter(Boolean),
    }
  }

  const endpointFailureMatch = text.match(/^Endpoint '([^']+)' failed dry-run validation:\s*(.+)$/i)
  if (endpointFailureMatch) {
    const endpointId = String(endpointFailureMatch[1] || "").trim()
    const reason = String(endpointFailureMatch[2] || "").trim()
    return {
      title: "Endpoint dry-run failed",
      lines: [
        endpointId ? `The endpoint '${endpointId}' failed when Liwiro executed its safe validation request.` : "A generated endpoint failed its safe validation request.",
        reason || "The endpoint returned an error during dry-run validation.",
        "Check the route logic, required inputs, and any Versa or VQL used by that endpoint.",
      ].filter(Boolean),
    }
  }

  const sandboxEndpointFailureMatch = text.match(/^Endpoint '([^']+)' failed dry-run validation in sandbox:\s*(.+)$/i)
  if (sandboxEndpointFailureMatch) {
    const endpointId = String(sandboxEndpointFailureMatch[1] || "").trim()
    const reason = String(sandboxEndpointFailureMatch[2] || "").trim()
    return {
      title: "Sandbox route validation failed",
      lines: [
        endpointId ? `The endpoint '${endpointId}' failed while Liwiro exercised it inside an isolated validation sandbox.` : "A generated endpoint failed inside Liwiro's isolated validation sandbox.",
        reason || "The endpoint returned an error during sandbox validation.",
        "This no longer means startup mutations were blocked. It means the generated route itself failed with the inputs used for validation.",
      ].filter(Boolean),
    }
  }

  if (/VDB authentication failed during dry-run validation/i.test(text)) {
    return {
      title: "VDB authentication failed",
      lines: [
        "Liwiro could not authenticate to VDB while validating this upload.",
        "Verify the saved runtime transport, username, password, domain, and database settings before retrying.",
      ],
    }
  }

  if (/Sandbox VDB authentication failed during dry-run validation/i.test(text)) {
    return {
      title: "Sandbox VDB authentication failed",
      lines: [
        "Liwiro started an isolated validation VDB, but the generated service could not authenticate against it.",
        "Check the backend VDB username/password values and retry so the sandbox can seed matching runtime credentials.",
      ],
    }
  }

  if (/Dry-run startup failed:/i.test(text)) {
    return {
      title: "Startup validation failed",
      lines: [
        "The generated service could not finish startup inside Liwiro's dry-run validator.",
        text.replace(/^Dry-run startup failed:\s*/i, "") || text,
        "Review startup-side modules, schema setup, and external calls used by this LAPIS file.",
      ],
    }
  }

  if (/Dry-run startup failed in sandbox:/i.test(text)) {
    return {
      title: "Sandbox startup failed",
      lines: [
        "The generated service could not finish startup inside Liwiro's isolated validation sandbox.",
        text.replace(/^Dry-run startup failed in sandbox:\s*/i, "") || text,
        "Review startup logic, required config, and any route code that runs during initialization.",
      ],
    }
  }

  if (/Validation sandbox failed to start:/i.test(text)) {
    return {
      title: "Validation sandbox failed",
      lines: [
        "Liwiro could not start the isolated VDB sandbox used for upload validation.",
        text.replace(/^Validation sandbox failed to start:\s*/i, "") || text,
        "Check local runtime prerequisites such as the VDB jar, Java tooling, and sandbox log output.",
      ],
    }
  }

  if (/Invalid JSON/i.test(text)) {
    return {
      title: "File could not be parsed",
      lines: [
        "The uploaded file is not valid JSON, so Liwiro could not read it as LAPIS.",
        "Fix the JSON syntax first, then upload the file again.",
      ],
    }
  }

  return {
    title: "Why upload is blocked",
    lines: [
      "This LAPIS file did not pass Liwiro's pre-generation validation.",
      text,
      "Fix the reported issue in the LAPIS config or referenced Versa logic, then retry the upload.",
    ],
  }
}

export function LapisUploadError({ error, className = "" }) {
  const text = String(error || "").trim()
  const explanation = explainLapisUploadError(text)

  if (!text) return null

  return (
    <div className={`mt-1 flex items-start gap-1.5 text-xs text-amber-700 dark:text-amber-300 ${className}`.trim()}>
      <p className="min-w-0 flex-1">{text}</p>
      {explanation ? (
        <TooltipProvider delayDuration={120}>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                aria-label={`Explain LAPIS upload error: ${explanation.title}`}
                className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-amber-400/50 bg-amber-100/70 text-amber-800 hover:bg-amber-100 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-200 dark:hover:bg-amber-500/20"
              >
                <Info className="h-3 w-3" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="top" align="start" className="max-w-sm rounded-xl border-slate-200 bg-white px-3 py-3 text-xs text-slate-700 shadow-xl dark:border-white/10 dark:bg-[#08111c] dark:text-slate-100">
              <div className="space-y-2">
                <p className="font-semibold text-slate-900 dark:text-white">{explanation.title}</p>
                {explanation.lines.map((line, index) => (
                  <p key={`${explanation.title}-${index}`} className="text-slate-600 dark:text-slate-300">
                    {line}
                  </p>
                ))}
              </div>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      ) : null}
    </div>
  )
}
