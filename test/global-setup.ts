import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, rmSync } from "node:fs";
import path from "node:path";

/**
 * Every run starts from a genuinely fresh database.
 *
 * The container is removed, db/finally.db is deleted, and the normal start
 * script brings it back. The backend then lazily recreates the schema and
 * seeds $10,000 plus the ten default tickers, which is the state the fresh
 * start test asserts against. Running the real start script also proves it is
 * idempotent, which is one of its stated requirements.
 */

const ROOT = path.resolve(__dirname, "..");
const BASE_URL = process.env.FINALLY_URL ?? "http://localhost:8000";
const CONTAINER = "finally";

function docker(args: string[], allowFailure = false): void {
  try {
    execFileSync("docker", args, { stdio: "pipe" });
  } catch (error) {
    if (!allowFailure) throw error;
  }
}

function requireMockMode(): void {
  const envPath = path.join(ROOT, ".env");
  if (!existsSync(envPath)) {
    throw new Error(`No .env at ${envPath}. The suite needs LLM_MOCK=true.`);
  }
  const contents = readFileSync(envPath, "utf8");
  if (!/^\s*LLM_MOCK\s*=\s*true\s*$/im.test(contents)) {
    throw new Error(
      "The E2E suite asserts against the deterministic LLM mock contract in " +
        "PLAN.md section 9. Set LLM_MOCK=true in the project root .env before " +
        "running it, otherwise the chat tests would hit the real model.",
    );
  }
}

function resetDatabase(): void {
  docker(["rm", "-f", CONTAINER], true);
  for (const suffix of ["", "-wal", "-shm"]) {
    rmSync(path.join(ROOT, "db", `finally.db${suffix}`), { force: true });
  }
}

/**
 * The container serves the frontend baked into the image, so backend or
 * frontend changes are invisible until the image is rebuilt. Set
 * FINALLY_REBUILD=1 after changing app code; the default reuses the image
 * because a rebuild costs minutes.
 */
function startApp(): void {
  const args = [
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    path.join(ROOT, "scripts", "start_windows.ps1"),
    "-NoBrowser",
  ];
  if (process.env.FINALLY_REBUILD === "1") args.push("-Build");

  execFileSync("powershell.exe", args, { cwd: ROOT, stdio: "inherit" });
}

async function waitForSeededApp(): Promise<void> {
  const deadline = Date.now() + 60_000;
  let lastError = "never reached";

  while (Date.now() < deadline) {
    try {
      const health = await fetch(`${BASE_URL}/api/health`);
      const portfolio = await (await fetch(`${BASE_URL}/api/portfolio`)).json();
      if (health.ok && portfolio.cash_balance === 10000) return;
      lastError = `cash_balance was ${portfolio.cash_balance}, expected 10000`;
    } catch (error) {
      lastError = String(error);
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }

  throw new Error(`App never reached a freshly seeded state: ${lastError}`);
}

export default async function globalSetup(): Promise<void> {
  requireMockMode();
  console.log("Resetting the database and restarting the container...");
  resetDatabase();
  startApp();
  await waitForSeededApp();
  console.log("Fresh database seeded. Running the suite.");
}
