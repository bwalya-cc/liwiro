// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import { Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { generateCollectionNameFromModelName } from "@/lib/model-naming"

import FieldConfig from "./FieldConfig"

export default function ModelConfig({ config, addModel, removeModel, updateConfig }) {
  const createId = () => {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID()
    }
    return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
  }

  const getFieldByPath = (modelFields, parentPath) => {
    const [, rootFieldId, ...nestedFieldIds] = String(parentPath || "").split(":")
    let currentField = modelFields?.[rootFieldId]

    for (const nestedFieldId of nestedFieldIds) {
      currentField = (Array.isArray(currentField?.embeddedFields) ? currentField.embeddedFields : []).find(
        (field) => field?.id === nestedFieldId,
      )
      if (!currentField) {
        return null
      }
    }

    return currentField
  }

  const addField = (modelId, parentPath = null, depth = 0) => {
    const fieldId = createId()
    const newField = {
      id: fieldId,
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

    if (!parentPath) {
      updateConfig("models", modelId, "fields", {
        ...(config.models?.[modelId]?.fields || {}),
        [fieldId]: newField
      })
    } else {
      const parentField = getFieldByPath(config.models?.[modelId]?.fields, parentPath)
      const existingEmbeddedFields = Array.isArray(parentField?.embeddedFields) ? parentField.embeddedFields : []
      updateConfig("fields", parentPath, "embeddedFields", [
        ...existingEmbeddedFields,
        newField
      ])
    }
  }

  const removeField = (modelId, fieldId, parentPath = null) => {
    if (!parentPath) {
      const updatedFields = { ...(config.models?.[modelId]?.fields || {}) }
      delete updatedFields[fieldId]
      updateConfig("models", modelId, "fields", updatedFields)
    } else {
      const updatedFields = { ...(config.models?.[modelId]?.fields || {}) }
      const currentField = getFieldByPath(updatedFields, parentPath)

      if (!currentField) {
        return
      }

      currentField.embeddedFields = (Array.isArray(currentField.embeddedFields) ? currentField.embeddedFields : []).filter(
        (field) => field?.id !== fieldId,
      )
      updateConfig("models", modelId, "fields", updatedFields)
    }
  }

  const handleModelNameChange = (modelId, nextName) => {
    const model = config.models[modelId] || {}
    const currentCollection = String(model.collection || "").trim()
    const previousAutoCollection = generateCollectionNameFromModelName(model.name || "")
    const nextAutoCollection = generateCollectionNameFromModelName(nextName)
    const shouldAutoUpdateCollection = !currentCollection || currentCollection === previousAutoCollection

    updateConfig("models", modelId, "name", nextName)
    if (shouldAutoUpdateCollection) {
      updateConfig("models", modelId, "collection", nextAutoCollection)
    }
  }

  return (
    <div className="app-card p-6">
      <div className="mb-5 flex items-center justify-between">
        <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">Models</h2>
        <Button onClick={addModel} size="sm" className="brand-solid h-9">
          <Plus className="h-4 w-4 mr-1" /> Add Model
        </Button>
      </div>

      {Object.keys(config.models).length === 0 ? (
        <div className="rounded-lg border border-dashed py-8 text-center dark:border-slate-700">
          <p className="text-slate-500 dark:text-slate-300">No models defined yet</p>
        </div>
      ) : (
        <div className="space-y-6">
          {Object.entries(config.models).map(([modelId, model]) => {
            const modelFields = model?.fields || {}

            return (
              <div key={modelId} className="mb-4 rounded-lg border border-slate-200 p-4 dark:border-slate-700">
                <div className="mb-4 flex items-center justify-between">
                  <h3 className="font-medium text-slate-900 dark:text-slate-100">Model Configuration</h3>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => removeModel(modelId)}
                    className="text-destructive hover:text-destructive/80"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>

                <div className="mb-4 grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label>Model Name</Label>
                    <Input
                      value={String(model.name || "")}
                      onChange={(e) => handleModelNameChange(modelId, e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Collection Name</Label>
                    <Input
                      value={String(model.collection || "")}
                      onChange={(e) => updateConfig("models", modelId, "collection", e.target.value)}
                    />
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="flex justify-between items-center">
                    <Label>Fields</Label>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8"
                      onClick={() => addField(modelId)}
                    >
                      <Plus className="h-4 w-4 mr-1" /> Add Field
                    </Button>
                  </div>

                  {Object.keys(modelFields).length === 0 ? (
                    <div className="rounded-lg border border-dashed py-4 text-center dark:border-slate-700">
                      <p className="text-slate-500 dark:text-slate-300">No fields defined</p>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {Object.values(modelFields).map((field, fieldIndex) => (
                        <FieldConfig
                          key={field.id || `${modelId}-field-${fieldIndex}`}
                          modelId={modelId}
                          field={field}
                          parentPath={null}
                          depth={0}
                          updateConfig={updateConfig}
                          removeField={removeField}
                        />
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
