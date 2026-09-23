# VDB Echo Command

The `echo` command in VDB allows you to output messages in the console or add a note object to the result in the http server interface.

## Usage

The basic syntax is:

```text
echo value "Your message here"
```

## Example

Here's a simple example of using the `echo` command:

```text
echo value "Moni, Dziko!"
echo value "Mwapoleni, Icalo!"
echo value "Hello, World!"
```

Output (console):
```
Moni, Dziko!
Mwapoleni, Icalo!
Hello, World!
```

or 

Output (http server interface):
```json
{
    ":>": "Moni, Dziko!"
}
{
    ":>": "Mwapoleni, Icalo!"
}
{
    ":>": "Hello, World!"
}
```
