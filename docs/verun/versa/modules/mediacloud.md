# MediaCloud and Custom Modules

MediaCloud is a bundled custom Versa module for Cloudinary uploads. Liwiro provides its source through the custom module registry; it is not a native Java module. Use VI Portal's module tools to inspect available modules and their domain assignments.

## Import and check readiness

```versa
mediacloud import *;
print(mediacloud.status({}));
```

`status(config)` returns the selected provider and provider readiness. `providers(config)` returns provider details. The bundled adapter supports Cloudinary. A readiness result checks for configured values; it does not make an upload or prove that the credentials are accepted.

## Configure Cloudinary

Use these local environment values:

```env
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret
CLOUDINARY_FOLDER=optional-folder
MEDIA_DEFAULT_PROVIDER=cloudinary
```

The module resolves values from the call's config, module configuration, and runtime environment. Config keys include `cloudName`, `apiKey`, `apiSecret`, `folder`, and `defaultProvider`. Generated-service scripts receive environment settings from their service configuration; standalone files need their own environment.

## Upload

`mediacloud.upload(payload)` accepts a body directly or under `body`. Supply one of `sourceUrl`, `dataUri`, `dataBase64`, or `textBody`. Optional values include `mimeType`, `filename`, `folder`, `publicId`, `provider`, and `config`.

The adapter chooses the file content in this order: data URI, base64 data, text body, then source URL. It sends the upload using the HTTP module. An upload is an external side effect; use a test folder and inspect the provider result before applying the workflow to real data.

Results include `ok`, `statusCode`, and `provider`. A successful result can include `providerAssetId`, `storagePath`, `publicUrl`, `secureUrl`, `sizeBytes`, and `providerResponse`. Missing credentials produce an error result; missing file content and unsupported providers also produce explicit error results.

Use `liwiro/data/lapis-examples/15-media-storage-bridge-service.json` for a complete service example. Its status routes can be inspected before supplying live credentials.

## Your own modules

Use **VI Portal → Modules** to inspect or edit reusable Versa modules, configuration, and domain availability. Service Builder supports shared module definitions and module configuration in a LAPIS contract. Keep imports at the top of module source and validate the complete service before generating it.

Module contexts can expose `module_config` and `module_meta`. Service context and VDB access depend on where the module runs. Do not assume that a helper loaded in a standalone file has authenticated database access or the request parameters of a service endpoint.
