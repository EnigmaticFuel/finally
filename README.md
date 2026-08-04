# FinAlly - AI Trading Workstation

A Bloomberg-style trading terminal with an AI copilot: live streaming prices, a simulated
$10,000 portfolio, and an LLM chat assistant that analyses positions and executes trades from
natural language.

Built entirely by coding agents as the capstone project for an agentic AI coding course.

## Prerequisites

Docker Desktop, running. Nothing else - Node and Python live inside the image.

## Start

macOS / Linux:

```bash
./scripts/start_mac.sh
```

Windows PowerShell:

```powershell
.\scripts\start_windows.ps1
```

The script creates `.env` from `.env.example` if you have none, builds the image on first run,
starts the container and opens <http://localhost:8000>. Pass `--build` (`-Build` on Windows) to
force a rebuild after changing the code.

## Stop

```bash
./scripts/stop_mac.sh          # macOS / Linux
.\scripts\stop_windows.ps1     # Windows
```

Stopping removes the container and leaves your data alone.

## API keys

All optional. Edit `.env`:

| Variable | Effect |
|---|---|
| `OPENROUTER_API_KEY` | Enables the AI chat panel. Without it every other feature works and chat replies that no key is configured. |
| `MASSIVE_API_KEY` | Uses real Polygon.io market data. Leave blank for the built-in simulator, which is the recommended default - real quotes are flat outside market hours. |
| `LLM_MOCK` | `true` gives deterministic mock LLM responses, used by the end-to-end tests. |

Restart the container after editing `.env`.

## The database

SQLite, at `db/finally.db` in this directory, bind-mounted into the container. It is created and
seeded on first launch and survives restarts. To reset your portfolio to $10,000 and the default
watchlist, stop the app, delete the file and start again.

## Development

```bash
cd backend && uv run --extra dev pytest    # backend tests
cd frontend && npm test                    # frontend tests
npx playwright test                        # end-to-end, against a running container
```

`docker compose up --build` is an equivalent alternative to the start scripts.

## Documentation

- `planning/PLAN.md` - the full specification and the authority for all agent work
- `planning/TEAM.md` - the engineering contract between the agents

## License

See [LICENSE](LICENSE).
