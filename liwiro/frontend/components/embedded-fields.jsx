// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

"use client"
import { Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"

export function EmbeddedFields({ fields, onChange }) {
  const addField = () => {
    const newField = {
      id: Date.now().toString(),
      name: "",
      type: "string",
      required: false,
      unique: false,
      default: false,
      defaultValue: "",
    }
    onChange([...fields, newField])
  }

  const removeField = (id) => {
    onChange(fields.filter((field) => field.id !== id))
  }

  const updateField = (id, key, value) => {
    onChange(fields.map((field) => (field.id === id ? { ...field, [key]: value } : field)))
  }

  return (
    <div className="space-y-3 border rounded-md p-3 bg-slate-50">
      <div className="flex justify-between items-center">
        <Label>Embedded Fields</Label>
        <Button variant="outline" size="sm" onClick={addField}>
          <Plus className="h-4 w-4 mr-1" /> Add Field
        </Button>
      </div>

      {fields.length === 0 ? (
        <div className="text-center py-4 border border-dashed rounded-lg">
          <p className="text-slate-500">No embedded fields defined yet.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {fields.map((field) => (
            <div key={field.id} className="grid grid-cols-12 gap-2 items-center border-b pb-2">
              <div className="col-span-3">
                <Input
                  placeholder="Field name"
                  value={field.name}
                  onChange={(e) => updateField(field.id, "name", e.target.value)}
                />
              </div>
              <div className="col-span-2">
                <Select value={field.type} onValueChange={(value) => updateField(field.id, "type", value)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="string">String</SelectItem>
                    <SelectItem value="number">Number</SelectItem>
                    <SelectItem value="boolean">Boolean</SelectItem>
                    <SelectItem value="date">Date</SelectItem>
                    <SelectItem value="array">Array</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="col-span-2 flex items-center space-x-2">
                <Switch
                  id={`required-${field.id}`}
                  checked={field.required}
                  onCheckedChange={(checked) => updateField(field.id, "required", checked)}
                />
                <Label htmlFor={`required-${field.id}`} className="text-xs">
                  Required
                </Label>
              </div>
              <div className="col-span-2 flex items-center space-x-2">
                <Switch
                  id={`default-${field.id}`}
                  checked={field.default}
                  onCheckedChange={(checked) => updateField(field.id, "default", checked)}
                />
                <Label htmlFor={`default-${field.id}`} className="text-xs">
                  Default
                </Label>
              </div>
              <div className="col-span-2 flex items-center space-x-2">
                <Switch
                  id={`unique-${field.id}`}
                  checked={field.unique}
                  onCheckedChange={(checked) => updateField(field.id, "unique", checked)}
                />
                <Label htmlFor={`unique-${field.id}`} className="text-xs">
                  Unique
                </Label>
              </div>
              <div className="col-span-1 text-right">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => removeField(field.id)}
                  className="text-red-500 hover:text-red-700 h-8 w-8 p-0"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>

              {field.default && (
                <div className="col-span-12 pl-6 mt-1">
                  <Label className="text-xs mb-1 block">Default Value</Label>
                  {field.type === "boolean" ? (
                    <Select
                      value={field.defaultValue}
                      onValueChange={(value) => updateField(field.id, "defaultValue", value)}
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder="Select default value" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="true">True</SelectItem>
                        <SelectItem value="false">False</SelectItem>
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input
                      placeholder={`Default value for ${field.type}`}
                      value={field.defaultValue}
                      type={field.type === "number" ? "number" : "text"}
                      onChange={(e) => updateField(field.id, "defaultValue", e.target.value)}
                    />
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

