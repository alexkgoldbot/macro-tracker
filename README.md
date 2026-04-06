# KiloClaw examples

A collection of example projects built with [KiloClaw](https://kilo.ai) — an agentic chat interface powered by OpenClaw skills.

Each example is a self-contained project demonstrating how to structure an OpenClaw agent, its skills, and any supporting backend or scripts.

## Examples

| Project | Description |
|---|---|
| [`macro-tracker`](./macro-tracker) | A personal macro tracking assistant. Logs food, manages recipes, and suggests meals based on remaining daily macro budget. |

## Structure

Each example follows the same layout:

```
example-name/
├── AGENTS.md              # Agent role, behavioral rules, and dietary/user preferences
├── USER.md                # User-specific preferences (gitignored — copy from USER.md.example)
├── .env                   # API keys (gitignored — copy from .env.example)
├── .env.example           # Template for required environment variables
├── .kilo/
│   ├── plans/             # Design docs and specs
│   └── command/           # Skill definitions (one .md per skill)
└── ...                    # Backend code, Python modules, etc.
```

## Getting started

1. Clone this repo
2. Navigate into an example directory
3. Copy `.env.example` to `.env` and fill in any required API keys
4. Copy `USER.md.example` to `USER.md` (if present) and set your personal preferences
5. Open the project in KiloClaw
