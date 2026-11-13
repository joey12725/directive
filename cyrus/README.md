# cyrus/

The application monorepo for [Directive](../README.md). Codename: **Cyrus**.

This tree started as [Plane](https://github.com/makeplane/plane) v1.2.3 by Plane Software, Inc. Plane provides the project-management foundation: work items, cycles, modules, pages, views, auth and the admin app. Plane's source files keep their original copyright headers, and the tree stays under Plane's license, the [GNU AGPL-3.0](LICENSE.txt) (see also [COPYRIGHT.txt](COPYRIGHT.txt)).

The orchestration layer added on top lives in:

- `apps/api/plane/app/{agents,orchestrator,schedules,metering,sessions,dashboard_metrics,wiki_sync}`
- `apps/api/plane/db/models/cyrus.py` and migrations `0121` to `0125`
- `apps/web/core/components/{dashboard,goals,schedules,sessions,cyrus-lists,cyrus-settings}`
- `relay/`

Development setup, architecture and configuration are documented at the repository root and in [`../docs`](../docs). Plane's upstream contributor docs ([CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)) are kept for reference.
