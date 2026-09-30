# Versa Guided Path

Learn Versa by running small scripts, adding modules, then moving into service workflows.

## 1. Run your first script

Open the REPL from the repository root:

```bash
cd verun
./vi/scripts/run_repl.sh
```

Try a value, a list, and a small function:

```versa
let names = ["Ada", "Lin"];
func greet(name) {
  return "Hello, " + name;
}
print(greet(names[0]));
```

Save the same source in a `.versa` file and run it with `./vi/scripts/run_file.sh /path/to/hello.versa` from `verun/`. Read [syntax](../versa/syntax.md) and [common authoring rules](../versa/syntax-rules.md) before adding more constructs.

## 2. Work with modules

Read the [module reference](../versa/modules.md), import a module at the top of a file, and try one documented call. Use [runtime and REPL guidance](../versa/runtime-cli-repl.md) for execution behavior.

For database work, import `vdb`, authenticate, and select a domain/database before reading data. Follow [the VDB bridge guide](../versa/vdb-module.md); keep its method calls distinct from native VQL command text.

In Liwiro, open VI Portal to select a workspace, edit files, validate source, and run scripts. A standalone file has different inputs from a service script.

## 3. Use Versa in services

Add a script endpoint to a LAPIS service. Read request values from the documented service context and put service-specific settings in `service.env`. Validate the full service definition, save it, and test the restarted route in Service Manager.

Use [VDB script examples](../versa/vdb-scripts-demo.md) for stored-script workflows. Explore the runnable catalog in `verun/vi/demo/README.md` for language, module, database, and media examples.

## Troubleshoot

Start with the reported line and error message. Check missing semicolons, imports, invalid syntax, and the expected runtime inputs. Use the smallest script that reproduces the problem, then return to the full workflow after it passes.

The machine-readable combined reference is `verun/vi/verse-verun-reference/reference.json`; the public HTML viewer is next to it. Use the detailed guides alongside it for context and examples.
