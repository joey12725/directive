# Cyrus v2

Autonomous agent orchestration platform built on a Plane fork.

## Overview

Cyrus v2 is an advanced autonomous agent orchestration platform that extends the capabilities of the Plane project management system with AI-powered automation and intelligent task management.

## Project Structure

- `cyrus/` - Main application codebase (monorepo)
  - `apps/` - Application packages
  - `packages/` - Shared packages and libraries
  - `docs/` - Documentation
- `test_*.py` - Integration and testing scripts
- `prompts.md` - AI prompts and templates
- `PHASE3_TEST_REPORT.md` - Testing documentation
- `PROVIDER_STATUS.md` - Provider status tracking

## Getting Started

### Prerequisites

- Node.js >= 22.18.0
- pnpm 10.30.2+
- Python 3.x (for testing scripts)

### Installation

```bash
cd cyrus
pnpm install
```

### Development

```bash
cd cyrus
pnpm dev
```

### Building

```bash
cd cyrus
pnpm build
```

## Documentation

For detailed documentation about the Plane platform that Cyrus is built on, see the [Cyrus README](./cyrus/README.md).

## License

AGPL-3.0 - See LICENSE.txt for details

## Repository

https://github.com/joey12725/directive.git
