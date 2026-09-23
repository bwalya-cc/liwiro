// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import { AlertTriangle } from "lucide-react";
import { Input } from "@/components/ui/input";
import PasswordInput from "@/components/ui/password-input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

export default function AuthConfig({ config, updateConfig, hasAuthModel }) {
  const resetPage = config.auth.passwordResetPage || {};
  const resetPageMode = resetPage.submissionMode === "custom_page"
    ? "custom_page"
    : (resetPage.enabled === false ? "custom_page" : "auto_form");
  const updateResetPage = (updates) => updateConfig("auth", null, "passwordResetPage", {
    ...resetPage,
    ...updates,
  });

  return (
    <div className="app-card p-6">
      <div className="mb-5 flex items-center justify-between">
        <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">Authentication</h2>
        <Switch
          checked={config.auth.enabled}
          onCheckedChange={(checked) => updateConfig("auth", null, "enabled", checked)}
        />
      </div>

      {config.auth.enabled && (
        <div className="space-y-6">
          {/* Authentication Service Configuration */}
          <div className="space-y-4 rounded-lg border border-slate-200 bg-slate-50/50 p-4 dark:border-slate-700 dark:bg-slate-800/60">
            <div className="flex items-center gap-2">
              <Switch
                checked={config.auth.isAuthService}
                onCheckedChange={(checked) => {
                  updateConfig("auth", null, "isAuthService", checked);
                  if (checked) {
                    updateConfig("auth", null, "useAsymmetricJWT", false);
                  }
                }}
              />
              <Label className="font-medium">Act as Authentication Service</Label>
            </div>

            {config.auth.isAuthService && (
              <div className="space-y-6 border-l-2 border-primary/30 pl-6">
                <Alert className="border-primary/30 bg-primary/10 dark:border-primary/40 dark:bg-primary/20">
                  <AlertTitle>Authentication Service Setup</AlertTitle>
                  <AlertDescription>
                    Enable this if this service will handle user authentication directly. 
                    You&apos;ll need to provide signing keys and configure authentication endpoints.
                  </AlertDescription>
                </Alert>

                {/* Key Management */}
                <div className="space-y-4 mt-4 mb-4">
                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2">
                      <input
                        type="radio"
                        checked={config.auth.keyManagement === 'auto'}
                        onChange={() => updateConfig("auth", null, "keyManagement", 'auto')}
                        className="h-4 w-4 mb-2"
                      />
                      <Label>Auto Generate Signing Keys</Label>
                    </div>
                    <div className="flex items-center gap-2">
                      <input
                        type="radio"
                        checked={config.auth.keyManagement === 'manual'}
                        onChange={() => updateConfig("auth", null, "keyManagement", 'manual')}
                        className="h-4 w-4 mb-2"
                      />
                      <Label>Provide Signing Keys</Label>
                    </div>
                  </div>

                  {config.auth.keyManagement === 'manual' && (
                    <div className="grid md:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label>Private Key (Signing)</Label>
                        <Textarea
                          value={config.auth.privateKey}
                          onChange={(e) => updateConfig("auth", null, "privateKey", e.target.value)}
                          className="h-32 font-mono"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Public Key (Verification)</Label>
                        <Textarea
                          value={config.auth.publicKey}
                          onChange={(e) => updateConfig("auth", null, "publicKey", e.target.value)}
                          className="h-32 font-mono"
                        />
                      </div>
                    </div>
                  )}
                </div>

                {/* Custom Endpoints */}
                <div className="space-y-4">
                  <div className="flex items-center gap-2">
                    <Switch
                      checked={config.auth.customEndpoints.enabled}
                      disabled={!hasAuthModel}
                      onCheckedChange={(checked) => updateConfig("auth", null, "customEndpoints", {
                        ...config.auth.customEndpoints,
                        enabled: checked,
                      })}
                    />
                    <Label className={!hasAuthModel ? "opacity-50" : ""}>Enable Authentication Endpoints</Label>
                  </div>

                  {!hasAuthModel && (
                    <Alert className="border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300">
                      <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-300" />
                      <AlertTitle>Authentication Model Required</AlertTitle>
                      <AlertDescription>
                        Create a model with username, email, and password fields to enable endpoints.
                      </AlertDescription>
                    </Alert>
                  )}

                  {hasAuthModel && config.auth.customEndpoints.enabled && (
                    <div className="space-y-4 border-l-2 border-slate-200 pl-6 dark:border-slate-600">
                      <div className="space-y-2">
                        <Label>Sign-In Endpoint</Label>
                        <Input
                          value={config.auth.customEndpoints.signIn}
                          onChange={(e) => updateConfig("auth", null, "customEndpoints", {
                            ...config.auth.customEndpoints,
                            signIn: e.target.value,
                          })}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Sign-Up Endpoint</Label>
                        <Input
                          value={config.auth.customEndpoints.signUp}
                          onChange={(e) => updateConfig("auth", null, "customEndpoints", {
                            ...config.auth.customEndpoints,
                            signUp: e.target.value,
                          })}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Sign-Out Endpoint</Label>
                        <Input
                          value={config.auth.customEndpoints.signOut || "/signout"}
                          onChange={(e) => updateConfig("auth", null, "customEndpoints", {
                            ...config.auth.customEndpoints,
                            signOut: e.target.value,
                          })}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Register Endpoint (Super Admin Only)</Label>
                        <Input
                          value={config.auth.customEndpoints.register || "/auth/register"}
                          onChange={(e) => updateConfig("auth", null, "customEndpoints", {
                            ...config.auth.customEndpoints,
                            register: e.target.value,
                          })}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Forgot Password Endpoint</Label>
                        <Input
                          value={config.auth.customEndpoints.forgotPassword || "/auth/forgot-password"}
                          onChange={(e) => updateConfig("auth", null, "customEndpoints", {
                            ...config.auth.customEndpoints,
                            forgotPassword: e.target.value,
                          })}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Reset Password Endpoint</Label>
                        <Input
                          value={config.auth.customEndpoints.resetPassword || "/reset-password"}
                          onChange={(e) => updateConfig("auth", null, "customEndpoints", {
                            ...config.auth.customEndpoints,
                            resetPassword: e.target.value,
                          })}
                        />
                      </div>
                      <div className="space-y-4 rounded-md border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900/60">
                        <div className="space-y-2">
                          <Label className="font-medium">Reset Password Submission</Label>
                          <select
                            value={resetPageMode}
                            onChange={(e) => {
                              const nextMode = e.target.value === "custom_page" ? "custom_page" : "auto_form";
                              updateResetPage({
                                submissionMode: nextMode,
                                enabled: nextMode === "auto_form",
                              });
                            }}
                            className="flex h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                          >
                            <option value="auto_form">Auto-generated reset form</option>
                            <option value="custom_page">Custom submission page link</option>
                          </select>
                        </div>
                        <p className="text-xs text-slate-500 dark:text-slate-300">
                          Choose whether reset emails open the built-in browser form or a custom page link where the token is appended as a query parameter.
                        </p>
                        {resetPageMode === "custom_page" ? (
                          <div className="space-y-2">
                            <Label>Token Email Link Base</Label>
                            <Input
                              value={resetPage.customPageBaseUrl || ""}
                              onChange={(e) => updateResetPage({ customPageBaseUrl: e.target.value })}
                              placeholder="https://app.example.com/reset-password"
                            />
                            <p className="text-xs text-slate-500 dark:text-slate-300">
                              Liwiro appends `?token=...` or `&token=...` to this link when the forgot-password email is sent.
                            </p>
                          </div>
                        ) : (
                          <div className="grid gap-3 md:grid-cols-2">
                            <div className="space-y-2 md:col-span-2">
                              <Label>Page Title</Label>
                              <Input
                                value={resetPage.title || ""}
                                onChange={(e) => updateResetPage({ title: e.target.value })}
                                placeholder="AuthCoreService Password Reset"
                              />
                            </div>
                            <div className="space-y-2 md:col-span-2">
                              <Label>Page Description</Label>
                              <Textarea
                                value={resetPage.description || ""}
                                onChange={(e) => updateResetPage({ description: e.target.value })}
                                className="min-h-[100px]"
                                placeholder="Use the emailed reset link or paste the token to set a new password."
                              />
                            </div>
                            <div className="space-y-2">
                              <Label>Submit Button Label</Label>
                              <Input
                                value={resetPage.submitLabel || ""}
                                onChange={(e) => updateResetPage({ submitLabel: e.target.value })}
                                placeholder="Reset Password"
                              />
                            </div>
                            <div className="space-y-2">
                              <Label>Loading Message</Label>
                              <Input
                                value={resetPage.loadingMessage || ""}
                                onChange={(e) => updateResetPage({ loadingMessage: e.target.value })}
                                placeholder="Submitting password reset request..."
                              />
                            </div>
                            <div className="space-y-2">
                              <Label>Success Message</Label>
                              <Input
                                value={resetPage.successMessage || ""}
                                onChange={(e) => updateResetPage({ successMessage: e.target.value })}
                                placeholder="Password reset completed."
                              />
                            </div>
                            <div className="space-y-2">
                              <Label>Failure Message</Label>
                              <Input
                                value={resetPage.failureMessage || ""}
                                onChange={(e) => updateResetPage({ failureMessage: e.target.value })}
                                placeholder="Password reset failed."
                              />
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>

                <div className="space-y-4 rounded-md border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900/60">
                  <div className="flex items-center gap-2">
                    <Switch
                      checked={config.auth.defaultSuperAdmin?.enabled || false}
                      onCheckedChange={(checked) =>
                        updateConfig("auth", null, "defaultSuperAdmin", { ...config.auth.defaultSuperAdmin, enabled: checked })
                      }
                    />
                    <Label className="font-medium">Enable Reset Super Admin Route</Label>
                  </div>
                  {config.auth.defaultSuperAdmin?.enabled && (
                    <div className="grid gap-3 md:grid-cols-2">
                      <div className="space-y-2">
                        <Label>Username</Label>
                        <Input
                          value={config.auth.defaultSuperAdmin?.username || ""}
                          onChange={(e) =>
                            updateConfig("auth", null, "defaultSuperAdmin", { ...config.auth.defaultSuperAdmin, username: e.target.value })
                          }
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Email</Label>
                        <Input
                          value={config.auth.defaultSuperAdmin?.email || ""}
                          onChange={(e) =>
                            updateConfig("auth", null, "defaultSuperAdmin", { ...config.auth.defaultSuperAdmin, email: e.target.value })
                          }
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Password</Label>
                        <PasswordInput
                          value={config.auth.defaultSuperAdmin?.password || ""}
                          onChange={(e) =>
                            updateConfig("auth", null, "defaultSuperAdmin", { ...config.auth.defaultSuperAdmin, password: e.target.value })
                          }
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Role</Label>
                        <Input
                          value={config.auth.defaultSuperAdmin?.role || "SUPER_ADMIN"}
                          onChange={(e) =>
                            updateConfig("auth", null, "defaultSuperAdmin", { ...config.auth.defaultSuperAdmin, role: e.target.value })
                          }
                        />
                      </div>
                      <p className="md:col-span-2 text-xs text-slate-500 dark:text-slate-300">
                        Exposes `POST /liwiro/setup/reset-super-admin` as an idempotent super-admin reset/bootstrap route using LAPIS defaults.
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Service Consumer Configuration */}
          <div className="space-y-4 rounded-lg border border-slate-200 bg-slate-50/50 p-4 dark:border-slate-700 dark:bg-slate-800/60">
            <div className="flex items-center gap-2">
              <Switch
                checked={config.auth.useAsymmetricJWT}
                disabled={config.auth.isAuthService}
                onCheckedChange={(checked) => {
                  updateConfig("auth", null, "useAsymmetricJWT", checked);
                  if (checked) {
                    updateConfig("auth", null, "isAuthService", false);
                  }
                }}
              />
              <Label className={`font-medium ${config.auth.isAuthService ? "opacity-50" : ""}`}>
                Verify External Authentication Tokens
              </Label>
            </div>

            {config.auth.useAsymmetricJWT && !config.auth.isAuthService && (
              <div className="space-y-4 border-l-2 border-primary/30 pl-6 dark:border-primary/40">
                <Alert className="border-primary/30 bg-primary/10 dark:border-primary/40 dark:bg-primary/20">
                  <AlertTitle>Service Consumer Setup</AlertTitle>
                  <AlertDescription>
                    Use this configuration if this service needs to verify tokens issued by an external authentication service.
                    Create and run the authentication service first, then provide its verification key here.
                  </AlertDescription>
                </Alert>

                <div className="space-y-2">
                  <Label>Authentication Service Name (Dependency)</Label>
                  <Input
                    value={config.auth.authServiceName || ""}
                    onChange={(e) => updateConfig("auth", null, "authServiceName", e.target.value)}
                    placeholder="e.g. auth-core-service"
                  />
                </div>

                <div className="space-y-2">
                  <Label>Authentication Service Public Key</Label>
                  <Textarea
                    value={config.auth.authServicePublicKey || ""}
                    onChange={(e) => updateConfig("auth", null, "authServicePublicKey", e.target.value)}
                    className="h-32 font-mono"
                    placeholder="Paste the public key here"
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
