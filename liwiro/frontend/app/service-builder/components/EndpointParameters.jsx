// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

// components/endpoint-parameters.jsx
import { Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"

export function EndpointParameters({ parameters, onChange }) {
  const addParameter = () => {
    onChange([
      ...(parameters || []),
      {
        name: "",
        in: "query",
        type: "string",
        required: false,
        description: ""
      }
    ])
  }

  const updateParameter = (index, field, value) => {
    const updated = [...parameters]
    updated[index] = { ...updated[index], [field]: value }
    onChange(updated)
  }

  const removeParameter = (index) => {
    onChange(parameters.filter((_, i) => i !== index))
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Label>Additional Parameters</Label>
        <Button variant="outline" size="sm" className="border-sky-400/30 bg-sky-400/10 text-sky-100 hover:bg-sky-400/20 hover:text-white" onClick={addParameter}>
          <Plus className="h-4 w-4 mr-1" /> Add Parameter
        </Button>
      </div>

      {parameters?.map((param, index) => (
        <div key={`parameter-${index}`} className="rounded-md border border-slate-200 p-4 dark:border-slate-700">
          {/* First row: Name, Location, Type, Required, Delete */}
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex flex-col flex-1 md:basis-1/[0.03]">
              <Label>Name</Label>
              <Input
                value={param.name}
                onChange={(e) => updateParameter(index, "name", e.target.value)}
                placeholder="Parameter Name"
                className="w-full"
              />
            </div>

            <div className="flex flex-col flex-1 md:basis-1/[0.06]">
              <Label>Location</Label>
              <Select
                value={param.in}
                onValueChange={(value) => updateParameter(index, "in", value)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="query">Query</SelectItem>
                  <SelectItem value="header">Header</SelectItem>
                  <SelectItem value="path">Path</SelectItem>
                  <SelectItem value="body">Body</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col flex-1 md:basis-1/[0.06]">
              <Label>Type</Label>
              <Select
                value={param.type}
                onValueChange={(value) => updateParameter(index, "type", value)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="string">String</SelectItem>
                  <SelectItem value="number">Number</SelectItem>
                  <SelectItem value="boolean">Boolean</SelectItem>
                  <SelectItem value="array">Array</SelectItem>
                  <SelectItem value="object">Object</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col flex-1 md:basis-1/[0.06]">
              <Label>Required</Label>
              <div className="flex items-center gap-2">
                <Switch
                  checked={param.required}
                  onCheckedChange={(checked) => updateParameter(index, "required", checked)}
                />
                <span className="text-sm text-slate-700 dark:text-slate-300">{param.required ? "Yes" : "No"}</span>
              </div>
            </div>

            <div className="flex-shrink-0">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => removeParameter(index)}
                className="p-2 text-destructive hover:text-destructive/80"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {/* Second row: Description */}
          <div className="mt-4">
            <Label>Description</Label>
            <Textarea
              value={param.description}
              onChange={(e) => updateParameter(index, "description", e.target.value)}
              placeholder="Parameter description"
              rows={2}
              className="w-full"
            />
          </div>
        </div>
      ))}

      {(!parameters || parameters.length === 0) && (
        <div className="rounded-lg border border-dashed py-4 text-center dark:border-slate-700">
          <p className="text-slate-500 dark:text-slate-300">No additional parameters defined</p>
        </div>
      )}
    </div>
  )
}
