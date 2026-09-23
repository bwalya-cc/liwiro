// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

"use client"
import { Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"

export function EndpointParameters({ parameters, onChange }) {
  const addParameter = () => {
    const newParameter = {
      id: Date.now().toString(),
      name: "",
      type: "string",
      required: false,
      description: "",
      location: "query",
      default: false,
      defaultValue: "",
    }
    onChange([...parameters, newParameter])
  }

  const removeParameter = (id) => {
    onChange(parameters.filter((param) => param.id !== id))
  }

  const updateParameter = (id, key, value) => {
    onChange(parameters.map((param) => (param.id === id ? { ...param, [key]: value } : param)))
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <Label>Parameters</Label>
        <Button variant="outline" size="sm" onClick={addParameter}>
          <Plus className="h-4 w-4 mr-1" /> Add Parameter
        </Button>
      </div>

      {parameters.length === 0 ? (
        <div className="text-center py-4 border border-dashed rounded-lg">
          <p className="text-slate-500">No parameters defined yet.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {parameters.map((param) => (
            <div key={param.id} className="border rounded-md p-3 bg-slate-50">
              <div className="flex justify-between items-center mb-3">
                <h4 className="font-medium">Parameter</h4>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => removeParameter(param.id)}
                  className="text-red-500 hover:text-red-700 h-8 w-8 p-0"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>

              <div className="grid grid-cols-2 gap-3 mb-3">
                <div className="space-y-1">
                  <Label htmlFor={`param-name-${param.id}`} className="text-xs">
                    Name
                  </Label>
                  <Input
                    id={`param-name-${param.id}`}
                    placeholder="Parameter name"
                    value={param.name}
                    onChange={(e) => updateParameter(param.id, "name", e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor={`param-type-${param.id}`} className="text-xs">
                    Type
                  </Label>
                  <Select value={param.type} onValueChange={(value) => updateParameter(param.id, "type", value)}>
                    <SelectTrigger id={`param-type-${param.id}`}>
                      <SelectValue placeholder="Type" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="string">String</SelectItem>
                      <SelectItem value="number">Number</SelectItem>
                      <SelectItem value="boolean">Boolean</SelectItem>
                      <SelectItem value="date">Date</SelectItem>
                      <SelectItem value="object">Object</SelectItem>
                      <SelectItem value="array">Array</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 mb-3">
                <div className="space-y-1">
                  <Label htmlFor={`param-location-${param.id}`} className="text-xs">
                    Location
                  </Label>
                  <Select
                    value={param.location}
                    onValueChange={(value) => updateParameter(param.id, "location", value)}
                  >
                    <SelectTrigger id={`param-location-${param.id}`}>
                      <SelectValue placeholder="Location" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="path">Path</SelectItem>
                      <SelectItem value="query">Query</SelectItem>
                      <SelectItem value="header">Header</SelectItem>
                      <SelectItem value="body">Body</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex items-end space-x-4">
                  <div className="flex items-center space-x-2">
                    <Switch
                      id={`param-required-${param.id}`}
                      checked={param.required}
                      onCheckedChange={(checked) => updateParameter(param.id, "required", checked)}
                    />
                    <Label htmlFor={`param-required-${param.id}`} className="text-xs">
                      Required
                    </Label>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Switch
                      id={`param-default-${param.id}`}
                      checked={param.default}
                      onCheckedChange={(checked) => updateParameter(param.id, "default", checked)}
                    />
                    <Label htmlFor={`param-default-${param.id}`} className="text-xs">
                      Default
                    </Label>
                  </div>
                </div>
              </div>

              <div className="space-y-1 mb-3">
                <Label htmlFor={`param-desc-${param.id}`} className="text-xs">
                  Description
                </Label>
                <Textarea
                  id={`param-desc-${param.id}`}
                  placeholder="Parameter description"
                  value={param.description}
                  onChange={(e) => updateParameter(param.id, "description", e.target.value)}
                  className="h-20"
                />
              </div>

              {param.default && (
                <div className="space-y-1">
                  <Label htmlFor={`param-default-value-${param.id}`} className="text-xs">
                    Default Value
                  </Label>
                  {param.type === "boolean" ? (
                    <Select
                      value={param.defaultValue}
                      onValueChange={(value) => updateParameter(param.id, "defaultValue", value)}
                    >
                      <SelectTrigger id={`param-default-value-${param.id}`}>
                        <SelectValue placeholder="Select default value" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="true">True</SelectItem>
                        <SelectItem value="false">False</SelectItem>
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input
                      id={`param-default-value-${param.id}`}
                      placeholder={`Default value for ${param.type}`}
                      value={param.defaultValue}
                      type={param.type === "number" ? "number" : "text"}
                      onChange={(e) => updateParameter(param.id, "defaultValue", e.target.value)}
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

