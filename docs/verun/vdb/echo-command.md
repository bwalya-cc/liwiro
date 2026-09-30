# VDB Echo Command

Use `echo` to return a literal value and print it to the VDB process output. It can help confirm that a command reaches the expected runtime.

```text
echo "Moni, Dziko!";
echo "Mwapoleni, Icalo!";
echo "Hello, World!";
```

`echo value "hello";` is also accepted. A single HTTP command returns the normal success response with the echoed value as `data`:

```json
{"status":"success","data":"Hello, World!"}
```

A multi-command batch returns individual command results in its result list. Echo does not create a database document. Authenticate before submitting it through the native command endpoint.
