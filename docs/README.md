# Liwiro Documentation

Find guides for building services, running Versa scripts, and managing your data.

## Start Here

1. [Set up and use Liwiro](liwiro/README.md)
2. [Explore Versa and VDB](verun/README.md)
3. [Connect services and runtimes](integration/README.md)
4. [Look up commands](reference/command-cheatsheet.md)

## Local Startup

Follow the [quick start](../README.md#quick-start) to copy the environment templates, add your local credentials, and run `./liwiro/scripts/start_all.sh`.

Open the frontend address shown in the startup output. The launcher detects your platform and Python installation, and uses the next free local port if a default port is busy.

## Browse by Task

- [Build and manage services](liwiro/service-management-and-governance.md)
- [Configure AI providers and usage](liwiro/ai-setup.md)
- [Explore service data with Ananse](liwiro/ananse.md)
- [Manage settings and access](liwiro/settings-and-access.md)
- [Work with Verse specialists](liwiro/verse-chat.md)
- [Choose a LAPIS example](integration/lapis-examples.md)
- [Write and run Versa](verun/versa/README.md)
- [Set up and query VDB](verun/vdb/README.md)
- [Manage Liwiro from the command line](integration/liwiro-cli.md)
- [Understand how the platform fits together](integration/system-description.md)
- [Browse the documentation map](reference/documentation-map.md)

## Service API Documentation

Generated services can expose their own API reference at `/liwiro/docs` and `/liwiro/docs.json`. Open a service in Service Manager to find its documentation and test its routes.

## Other Resources

- `legal/`: licenses, third-party credits, and commercial-policy notes
- `compliance/`: operational guidance for license acceptance
- `assets/`: screenshots and shared documentation images

## Keeping the Wiki in Sync

The public wiki uses the Markdown pages listed in `docs/wiki/catalog.json`. After editing a listed guide or its catalog entry, run `python scripts/build_wiki.py` from the repository root. Use `python scripts/build_wiki.py --check` to verify that the published wiki matches its sources.

The Versa and combined Versa/VDB references are rebuilt with `python verun/vi/versa-wiki/build_reference.py`. Update the source guides and generator together when changing documented syntax.
