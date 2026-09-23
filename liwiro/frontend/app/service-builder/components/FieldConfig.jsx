// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import { Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { JsonTextarea } from "@/components/ui/json-textarea"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"

export default function FieldConfig({ modelId, field, parentPath, depth, updateConfig, removeField }) {
  const fieldId = String(field?.id || "")
  const fullPath = parentPath ? `${parentPath}:${fieldId}` : `${modelId}:${fieldId}`
  const embeddedFields = Array.isArray(field?.embeddedFields) ? field.embeddedFields : []
  const createId = () => {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID()
    }
    return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
  }

  return (
    <div className="mb-4 rounded-md border border-slate-200 p-3 dark:border-slate-700">
      <div className="flex flex-wrap items-center gap-2 pb-2">
        <div className="flex-1 min-w-[200px]">
          <Input
            placeholder="Field name"
            value={String(field.name || "")}
            onChange={e => updateConfig("fields", fullPath, "name", e.target.value)}
          />
        </div>

        <div className="flex flex-1 gap-2 items-center min-w-[200px]">
          <Select
            value={field.type || "string"}
            onValueChange={value => {
              updateConfig("fields", fullPath, "type", value)
              if (value !== "object") {
                updateConfig("fields", fullPath, "embeddedFields", [])
              }
            }}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder="Type" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="string">String</SelectItem>
              <SelectItem value="number">Number</SelectItem>
              <SelectItem value="boolean">Boolean</SelectItem>
              <SelectItem value="date">Date</SelectItem>
              <SelectItem value="object">
                {depth < 3 ? "Embedded Document" : "Object"}
              </SelectItem>
            </SelectContent>
          </Select>

          <div className="flex items-center gap-1">
            <Switch
              checked={Boolean(field.required)}
              onCheckedChange={checked => updateConfig("fields", fullPath, "required", checked)}
            />
            <Label className="text-xs">Required</Label>
          </div>

          <div className="flex items-center gap-1">
            <Switch
              checked={Boolean(field.unique)}
              onCheckedChange={checked => updateConfig("fields", fullPath, "unique", checked)}
            />
            <Label className="text-xs">Unique</Label>
          </div>

          <div className="flex items-center gap-1">
            <Switch
              checked={Boolean(field.default)}
              onCheckedChange={checked => updateConfig("fields", fullPath, "default", checked)}
            />
            <Label className="text-xs">Default</Label>
          </div>

          <Button
            variant="ghost"
            size="sm"
            className="h-8 w-8 p-0 text-destructive hover:text-destructive/80"
            onClick={() => removeField(modelId, field.id, parentPath)}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {field.default && (
        <div className="pl-6 mt-2">
          <Label className="text-xs mb-1 block">Default Value</Label>
          {field.type === "boolean" ? (
            <Select
              value={String(field.defaultValue ?? "")}
              onValueChange={value => updateConfig("fields", fullPath, "defaultValue", value)}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select value" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="true">True</SelectItem>
                <SelectItem value="false">False</SelectItem>
              </SelectContent>
            </Select>
          ) : field.type === "object" ? (
            <JsonTextarea
              placeholder="Enter JSON object"
              value={String(field.defaultValue ?? "")}
              onChange={e => updateConfig("fields", fullPath, "defaultValue", e.target.value)}
              className="font-mono text-sm h-32"
            />
          ) : (
            <Input
              type={field.type === "number" ? "number" : "text"}
              value={String(field.defaultValue ?? "")}
              onChange={e => updateConfig("fields", fullPath, "defaultValue", e.target.value)}
            />
          )}
        </div>
      )}

      {field.type === "object" && depth < 3 && (
        <div className="pl-6 mt-2 mb-4">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-medium text-slate-900 dark:text-slate-100">
              {depth === 0 ? "Embedded Fields" : 
               depth === 1 ? "Nested Fields" : 
               "Deep Nested Fields"}
            </h4>
            <Button
              variant="outline"
              size="sm"
              className="border-sky-400/30 bg-sky-400/10 text-sky-100 hover:bg-sky-400/20 hover:text-white"
              onClick={() => updateConfig("fields", fullPath, "embeddedFields", [
                ...embeddedFields,
                {
                  id: createId(),
                  name: "",
                  type: "string",
                  required: false,
                  unique: false,
                  default: false,
                  defaultValue: "",
                  objectTemplate: "",
                  embeddedFields: [],
                  depth: depth + 1
                }
              ])}
            >
              <Plus className="h-4 w-4 mr-1" /> Add Field
            </Button>
          </div>

          {embeddedFields.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-slate-300">No nested fields</p>
          ) : (
            <div className="space-y-3">
              {embeddedFields.map((embeddedField, embeddedIndex) => (
                <FieldConfig
                  key={embeddedField.id || `${fullPath}-embedded-${embeddedIndex}`}
                  modelId={modelId}
                  field={embeddedField}
                  parentPath={fullPath}
                  depth={depth + 1}
                  updateConfig={updateConfig}
                  removeField={removeField}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {field.type === "object" && depth >= 3 && (
        <div className="pl-6 mt-2">
          <Label className="text-xs mb-1 block">Object Template (JSON)</Label>
          <JsonTextarea
            placeholder='{"key":"value"}'
            value={String(field.objectTemplate || "")}
            onChange={e => updateConfig("fields", fullPath, "objectTemplate", e.target.value)}
            className="font-mono text-sm h-28"
          />
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-300">
            Max embedded depth reached. Use JSON template text here for this object field.
          </p>
        </div>
      )}
    </div>
  )
}
