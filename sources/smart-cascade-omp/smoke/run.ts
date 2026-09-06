#!/usr/bin/env bun
/**
 * CLI: `bun run sources/smart-cascade-omp/smoke/run.ts [--model provider/id]`
 *
 * Disposable real admitted OMP RPC smoke. It creates a Git fixture and a
 * throw-away HOME/profile, then proves Root→isolated Leader→isolated Executor,
 * plain-prose Hub delivery, retained patch artifacts (apply=false/merge=patch),
 * deliberate parent apply, and native isolation cleanup. No production profile
 * or service is touched. Output is one structured JSON report.
 */

import { copyFile, mkdtemp, readdir, readFile, rm, writeFile } from "node:fs/promises";
import { existsSync, mkdirSync, readFileSync, realpathSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { RpcClient } from "@oh-my-pi/pi-coding-agent/modes/rpc/rpc-client";
import { messageRecord, transcriptEntries, type TranscriptEnvelope } from "./native-evidence";

const PACKAGE_ROOT = dirname(dirname(realpathSync(fileURLToPath(import.meta.resolve("@oh-my-pi/pi-coding-agent")))));
const OMP_CLI = process.env.OMP_CLI ?? join(PACKAGE_ROOT, "dist", "cli.js");
const PROJECT_ROOT = dirname(dirname(dirname(import.meta.dir)));
const SKILL_ROOT = join(PROJECT_ROOT, "sources", "smart-cascade-skill");
const FIXTURE = "smoke/fixture.txt";
const MODELS_SOURCE = process.env.SMART_CASCADE_SMOKE_MODELS ?? join(homedir(), ".omp", "profiles", "smart-cascade-omp", "agent", "models.yml");
const HUB_MESSAGE = "smart-cascade-native-hub-message";
const BEFORE = "ROOT_BASELINE\n";
const EXECUTOR_BYTES = `${BEFORE}EXECUTOR_PATCH\n`;
const FINAL_BYTES = `${EXECUTOR_BYTES}LEADER_ASSEMBLED\n`;

type Phase = "bootstrap" | "repository" | "profile" | "rpc" | "root" | "observe" | "patches" | "parent" | "verify" | "apply" | "cleanup";
type PhaseRecord = { phase: Phase; status: "passed" | "failed"; detail?: string };
type Observations = {
	tempRoot?: string;
	repository?: string;
	profile?: string;
	agentIds: string[];
	lifecycle: unknown[];
	subagents: unknown[];
	plainHubMessageObserved: boolean;
	patchPaths: { executor?: string; leader?: string; all: string[] };
	lifecycleEvidence?: { leader: unknown; executor: unknown };
	hubEvidence?: { leaderToRoot: boolean; executorToLeader: boolean };
	parentBeforeApply?: { status: string; content: string };
	parentAfterApply?: { status: string; content: string };
	finalFileContent?: string;
	isolationCleanup?: { base: string; existsAfterStop: boolean; remainingEntries: string[] };
	rootAcceptanceVerified?: boolean;
	noActiveWriterObserved?: boolean;
};
type Report = { version: 1; status: "passed" | "failed"; phase?: Phase; error?: string; phases: PhaseRecord[]; observations: Observations };

class PhaseError extends Error {
	constructor(readonly phase: Phase, message: string) {
		super(message);
	}
}

function argModel(): { model: string; mode: "run" | "help" | "self-test" } {
	const args = process.argv.slice(2);
	if (args.includes("-h") || args.includes("--help")) return { model: "", mode: "help" };
	if (args.includes("--self-test-evidence")) {
		if (args.length !== 1) throw new Error("--self-test-evidence does not accept other arguments");
		return { model: "", mode: "self-test" };
	}
	let model = process.env.SMART_CASCADE_SMOKE_MODEL ?? "";
	for (let i = 0; i < args.length; i++) {
		if (args[i] === "--model") model = args[++i] ?? "";
		else if (args[i]?.startsWith("--model=")) model = args[i].slice(8);
		else throw new Error(`unknown argument ${args[i]}`);
	}
	if (!model) throw new Error("--model requires provider/model");
	return { model, mode: "run" };
}

async function shell(cwd: string, ...args: string[]): Promise<string> {
	const child = Bun.spawn(args, { cwd, stdout: "pipe", stderr: "pipe" });
	const [stdout, stderr, code] = await Promise.all([new Response(child.stdout).text(), new Response(child.stderr).text(), child.exited]);
	if (code !== 0) throw new Error(`${args.join(" ")} (${code}): ${stderr.trim() || stdout.trim()}`);
	return stdout;
}

async function phase<T>(records: PhaseRecord[], name: Phase, run: () => Promise<T>): Promise<T> {
	try {
		const result = await run();
		records.push({ phase: name, status: "passed" });
		return result;
	} catch (error) {
		const detail = error instanceof Error ? error.message : String(error);
		records.push({ phase: name, status: "failed", detail });
		throw error instanceof PhaseError ? error : new PhaseError(name, detail);
	}
}


async function patchFiles(root: string): Promise<string[]> {
	if (!existsSync(root)) return [];
	const result: string[] = [];
	const walk = async (dir: string): Promise<void> => {
		for (const entry of await readdir(dir, { withFileTypes: true })) {
			const path = join(dir, entry.name);
			if (entry.isDirectory()) await walk(path);
			else if (entry.isFile() && path.endsWith(".patch")) result.push(path);
		}
	};
	await walk(root);
	return result.sort();
}

type ToolCallEnvelope = { type?: unknown; id?: unknown; name?: unknown; arguments?: unknown };
type HubArguments = { op?: unknown; to?: unknown; message?: unknown };
type HubDetails = { op?: unknown; from?: unknown; to?: unknown; receipts?: unknown };
type HubReceipt = { to?: unknown; outcome?: unknown };

function expectedHubMessage(sender: string): string {
	if (sender === "smoke-leader-id") return `${HUB_MESSAGE} slice smoke-slice attempt leader-attempt-1 nonce smoke-nonce`;
	if (sender === "smoke-leader-id.smoke-executor-id") return `${HUB_MESSAGE} slice smoke-slice attempt child-attempt-1 nonce child-nonce`;
	return HUB_MESSAGE;
}

function isSmokeHubMessage(value: unknown, sender: string): boolean {
	return value === expectedHubMessage(sender);
}

function hubMessageObserved(entries: readonly unknown[], sender: string, recipient: string): boolean {
	const sends = new Map<string, string>();
	for (const entry of entries) {
		if (entry && typeof entry === "object") {
			const envelope = entry as TranscriptEnvelope;
			const details = envelope.details as { from?: unknown; message?: unknown } | undefined;
			if (envelope.type === "custom_message" && envelope.customType === "irc:incoming" && details?.from === sender && isSmokeHubMessage(details.message, sender)) return true;
		}
		const message = messageRecord(entry);
		if (!message) continue;
		const waited = message.details as { op?: unknown; from?: unknown; waited?: unknown } | undefined;
		if (message.role === "toolResult" && message.toolName === "hub" && waited?.op === "wait" && waited.waited && typeof waited.waited === "object") {
			const receipt = waited.waited as { from?: unknown; to?: unknown; body?: unknown };
			if (receipt.from === sender && receipt.to === recipient && isSmokeHubMessage(receipt.body, sender)) return true;
		}
		if (message.role === "assistant" && Array.isArray(message.content)) {
			for (const value of message.content) {
				if (!value || typeof value !== "object") continue;
				const item = value as ToolCallEnvelope;
				const args = item.arguments as HubArguments | undefined;
				if (item.type !== "toolCall" || item.name !== "hub" || typeof item.id !== "string" || args?.op !== "send" || args.to !== recipient || !isSmokeHubMessage(args.message, sender)) continue;
				sends.set(item.id, recipient);
			}
			continue;
		}
		const details = message.details as HubDetails | undefined;
		if (message.role !== "toolResult" || message.toolName !== "hub" || message.isError === true || typeof message.toolCallId !== "string" || sends.get(message.toolCallId) !== recipient) continue;
		if (details?.op !== "send" || details.from !== sender || details.to !== recipient || !Array.isArray(details.receipts)) continue;
		if (details.receipts.some(value => {
			if (!value || typeof value !== "object") return false;
			const receipt = value as HubReceipt;
			return receipt.to === recipient && (receipt.outcome === "delivered" || receipt.outcome === "injected");
		})) return true;
	}
	return false;
}

async function evidenceSelfTest(): Promise<void> {
	const promptOnly = [{ role: "user", content: [{ type: "text", text: HUB_MESSAGE }] }];
	if (hubMessageObserved(promptOnly, "smoke-leader-id", "Main")) throw new Error("prompt text counted as Hub evidence");
	const incoming = [{ type: "custom_message", customType: "irc:incoming", details: { from: "smoke-leader-id", message: `${HUB_MESSAGE} slice smoke-slice attempt leader-attempt-1 nonce smoke-nonce` } }];
	if (!hubMessageObserved(incoming, "smoke-leader-id", "Main")) throw new Error("structured incoming Hub evidence was missed");
	const uncorrelated = [{ type: "custom_message", customType: "irc:incoming", details: { from: "smoke-leader-id", message: `${HUB_MESSAGE} wrong labels` } }];
	if (hubMessageObserved(uncorrelated, "smoke-leader-id", "Main")) throw new Error("incorrect Hub correlation labels counted as evidence");
	const delivered = [
		{ type: "message", message: { role: "assistant", content: [{ type: "toolCall", id: "hub-call", name: "hub", arguments: { op: "send", to: "Main", message: expectedHubMessage("smoke-leader-id") } }] } },
		{ type: "message", message: { role: "toolResult", toolCallId: "hub-call", toolName: "hub", isError: false, details: { op: "send", from: "smoke-leader-id", to: "Main", receipts: [{ to: "Main", outcome: "injected" }] } } },
	];
	if (!hubMessageObserved(delivered, "smoke-leader-id", "Main")) throw new Error("delivered Hub send receipt fixture was missed");
	const waited = [{ type: "message", message: { role: "toolResult", toolName: "hub", details: { op: "wait", from: "smoke-leader-id", waited: { from: "smoke-leader-id.smoke-executor-id", to: "smoke-leader-id", body: `${HUB_MESSAGE} slice smoke-slice attempt child-attempt-1 nonce child-nonce` } } } }];
	if (!hubMessageObserved(waited, "smoke-leader-id.smoke-executor-id", "smoke-leader-id")) throw new Error("real Hub wait receipt fixture was missed");
	process.stdout.write(`${JSON.stringify({ status: "passed", evidence: "Hub delivery observation helpers" })}\n`);
}


function resolvedModelMatches(value: unknown, model: string): boolean {
	return typeof value === "string" && (value === model || value.startsWith(`${model}:`));
}

function profileAgents(): Record<string, string> {
	return {
		"smart-cascade-leader.md": `${readFileSync(join(SKILL_ROOT, "runners", "omp", "roles", "smart-cascade-leader.md"), "utf8")}\n\nDisposable smoke override: execute this fixture mechanically. Spawn exactly one smart-cascade-executor with local task name smoke-executor-id, isolated=true, schemaMode=strict, and the supplied Executor output schema. Wait for its terminal task result. Keep every retained patch copy and other control artifact outside the repository candidate; the only repository path you may change is ${FIXTURE}. Verify the retained patch, apply it serially inside your isolation, verify ${FIXTURE} is exactly ${JSON.stringify(EXECUTOR_BYTES)}, then append LEADER_ASSEMBLED so it becomes exactly ${JSON.stringify(FINAL_BYTES)}. Call Hub send to Main with exactly ${HUB_MESSAGE} slice smoke-slice attempt leader-attempt-1 nonce smoke-nonce. Settle with {"status":"READY_FOR_ROOT_REVIEW","slice_id":"smoke-slice","attempt_id":"leader-attempt-1","execution_path":"delegated","children":["smoke-child"],"candidate_evidence":{"base":"<use exact supplied base>","changed_paths":[${JSON.stringify(FIXTURE)}],"checks":["fixture bytes passed"],"evidence":"serial exact bytes verified"},"preserved_attempts":[]}. Never mutate Root directly or commit.\n`,
		"smart-cascade-executor.md": `${readFileSync(join(SKILL_ROOT, "runners", "omp", "roles", "smart-cascade-executor.md"), "utf8")}\n\nDisposable smoke override: call Hub send to smoke-leader-id with exactly ${HUB_MESSAGE} slice smoke-slice attempt child-attempt-1 nonce child-nonce. Then overwrite ${FIXTURE} with exactly these literal bytes: ROOT_BASELINE newline EXECUTOR_PATCH newline. Read the file back and require exact equality with ${JSON.stringify(EXECUTOR_BYTES)} before settling as {"status":"DONE","child_id":"smoke-child","slice_id":"smoke-slice","attempt_id":"child-attempt-1","changed_paths":[${JSON.stringify(FIXTURE)}],"checks":["fixture bytes passed"],"evidence":"exact bytes verified"}. Do not include patchPath; OMP supplies it. Do not spawn, apply to a parent, or commit.\n`,
	};
}

function rootPrompt(leaderPacket: Record<string, unknown>, executorPacket: Record<string, unknown>): string {
	const rootContract = readFileSync(join(SKILL_ROOT, "bootstrap", "root-init.md"), "utf8");
	return `${rootContract}\n\nSmoke authorization: initialization and explicit run authorization are already complete for this disposable fixture; do not emit the initialization receipt. Execute the production loop now. Keep patch copies, receipts, and all other control artifacts outside the repository; the retained candidate must change only ${FIXTURE}. The admitted profile requires the native batch task form with context plus one tasks[] item. Dispatch one Leader with this assignment: ${JSON.stringify(leaderPacket)}. Use agent smart-cascade-leader, name smoke-leader-id, isolated=true, schemaMode=strict, outputSchema ${JSON.stringify(leaderPacket.result_schema)}. The Leader must give its Executor this assignment ${JSON.stringify(executorPacket)} in its own batch task call with outputSchema ${JSON.stringify(executorPacket.result_schema)}. Wait for settlement, call Hub send to smoke-leader-id with ${HUB_MESSAGE} slice smoke-slice attempt leader-attempt-1 nonce smoke-nonce, verify the candidate against the real diff, prove the Root parent is unchanged, then stop before applying it and report {"status":"READY_TO_APPLY","slice_id":"smoke-slice","attempt_id":"leader-attempt-1","committed":false}. Never apply or commit; the smoke harness will deliberately apply the verified retained Leader patch after independently proving pre-apply state.`;
}

async function main(): Promise<void> {
	const phases: PhaseRecord[] = [];
	const observations: Observations = { agentIds: [], lifecycle: [], subagents: [], plainHubMessageObserved: false, patchPaths: { all: [] } };
	let client: RpcClient | undefined;
	let root: string | undefined;
	let isolationBase: string | undefined;
	let runnerConfig: string | undefined;
	let cleanupError: string | undefined;
	try {
		const parsed = await phase(phases, "bootstrap", async () => argModel());
		if (parsed.mode === "help") {
			process.stdout.write("Usage: bun run sources/smart-cascade-omp/smoke/run.ts [--model provider/id] [--self-test-evidence]\n");
			return;
		}
		if (parsed.mode === "self-test") {
			await evidenceSelfTest();
			return;
		}
		root = await phase(phases, "repository", async () => {
			const temp = await mkdtemp(join(tmpdir(), "smart-cascade-omp-smoke-"));
			const repo = join(temp, "repo");
			mkdirSync(repo, { recursive: true });
			await shell(repo, "git", "init", "--quiet");
			mkdirSync(join(repo, "smoke"), { recursive: true });
			await writeFile(join(repo, FIXTURE), BEFORE);
			mkdirSync(join(repo, ".smart-cascade"), { recursive: true });
			await writeFile(join(repo, ".smart-cascade", "queue.toml"), `[[slices]]\nid = "smoke-slice"\ndepends_on = []\nscope = "mutate only ${FIXTURE}"\nchecks = ["read fixture bytes"]\n`);
			await copyFile(join(SKILL_ROOT, "bootstrap", "validate-queue.py"), join(repo, "validate-queue.py"));
			await shell(repo, "git", "config", "user.email", "smart-cascade-smoke@example.invalid");
			await shell(repo, "git", "config", "user.name", "Smart Cascade Smoke");
			await shell(repo, "git", "add", FIXTURE, "validate-queue.py", ".smart-cascade/queue.toml");
			await shell(repo, "git", "commit", "--quiet", "-m", "smoke baseline");
			observations.tempRoot = temp;
			observations.repository = repo;
			return temp;
		});
		const repo = observations.repository!;
		const base = (await shell(repo, "git", "rev-parse", "HEAD")).trim();
		const home = join(root, "home");
		mkdirSync(home, { recursive: true });
		const profile = `smart-cascade-smoke-${process.pid}`;
		isolationBase = join(root, "omp-worktrees");
		observations.profile = profile;
		const config = await phase(phases, "profile", async () => {
			const profileAgentDir = join(home, ".omp", "profiles", profile, "agent");
			const profileAgentsDir = join(profileAgentDir, "agents");
			mkdirSync(profileAgentsDir, { recursive: true });
			if (!existsSync(MODELS_SOURCE)) throw new Error(`model config not found: ${MODELS_SOURCE}`);
			await copyFile(MODELS_SOURCE, join(profileAgentDir, "models.yml"));
			for (const [name, content] of Object.entries(profileAgents())) await writeFile(join(profileAgentsDir, name), content);
			const path = join(root!, "config.yml");
			await writeFile(path, `modelRoles:\n  smart-cascade-leader: ${parsed.model}\n  smart-cascade-semantic: ${parsed.model}\ntask:\n  isolation:\n    mode: auto\n    apply: false\n    merge: patch\n  maxRecursionDepth: 2\n  batch: true\nasync:\n  enabled: true\nworktree:\n  base: '${isolationBase!.replaceAll("'", "''")}'\n`);
			runnerConfig = join(root!, "runner-launch.yaml");
			await writeFile(runnerConfig, `roles:\n  leader:\n    agent: smart-cascade-leader\n    model_role: smart-cascade-leader\n    model: ${parsed.model}\n  semantic_executor:\n    agent: smart-cascade-executor\n    model_role: smart-cascade-semantic\n    model: ${parsed.model}\n`);
			return path;
		});
		const leaderSchema = { type: "object", properties: { status: { const: "READY_FOR_ROOT_REVIEW" }, slice_id: { const: "smoke-slice" }, attempt_id: { const: "leader-attempt-1" }, execution_path: { const: "delegated" }, children: { const: ["smoke-child"] }, candidate_evidence: { type: "object", properties: { base: { const: base }, changed_paths: { const: [FIXTURE] }, checks: { const: ["fixture bytes passed"] }, evidence: { type: "string" } }, required: ["base", "changed_paths", "checks", "evidence"], additionalProperties: false }, preserved_attempts: { const: [] } }, required: ["status", "slice_id", "attempt_id", "execution_path", "children", "candidate_evidence", "preserved_attempts"], additionalProperties: false };
		const executorSchema = { type: "object", properties: { status: { const: "DONE" }, child_id: { const: "smoke-child" }, slice_id: { const: "smoke-slice" }, attempt_id: { const: "child-attempt-1" }, changed_paths: { const: [FIXTURE] }, checks: { const: ["fixture bytes passed"] }, evidence: { type: "string" } }, required: ["status", "child_id", "slice_id", "attempt_id", "changed_paths", "checks", "evidence"], additionalProperties: false };
		const leaderPacket = { role: "leader", task_name: "smoke-leader-id", slice_id: "smoke-slice", attempt_id: "leader-attempt-1", base, scope: `mutate only ${FIXTURE}`, dependencies: [], checks: ["read fixture bytes"], non_goals: ["no Root mutation", "no commit"], result_schema: leaderSchema };
		const executorPacket = { role: "executor", task_name: "smoke-executor-id", slice_id: "smoke-slice", child_id: "smoke-child", attempt_id: "child-attempt-1", base, checks: ["read fixture bytes"], non_goals: ["no parent mutation", "no commit"], postcondition: `${FIXTURE} has exact Executor bytes`, result_schema: executorSchema };
		client = await phase(phases, "rpc", async () => {
			const rpc = new RpcClient({ cliPath: OMP_CLI, cwd: repo, model: parsed.model, env: { HOME: home, OMP_PROFILE: profile, PI_PROFILE: profile, OMP_WORKTREE_DIR: isolationBase! }, args: ["--profile", profile, "--config", config, "--no-extensions", "--no-skills", "--no-rules", "--no-lsp", "--approval-mode", "yolo"] });
			rpc.onSubagentLifecycle(payload => observations.lifecycle.push(payload));
			await rpc.start();
			await rpc.setSubagentSubscription("events");
			return rpc;
		});
		await phase(phases, "root", async () => {
			await client!.prompt(rootPrompt(leaderPacket, executorPacket));
			await client!.waitForIdle(15 * 60 * 1000);
		});
		const messages = await client.getMessages();
		const state = await client.getState();
		let rootEntries: unknown[] = messages;
		if (state.sessionFile) rootEntries = await transcriptEntries(state.sessionFile);
		const leaderLifecycle = [...observations.lifecycle, ...(await client.getSubagents())].reverse().find(value => value && typeof value === "object" && "id" in value && value.id === "smoke-leader-id" && "sessionFile" in value && typeof value.sessionFile === "string") as { id: string; sessionFile: string; status?: unknown; agent?: unknown } | undefined;
		const leaderEntries = leaderLifecycle && existsSync(leaderLifecycle.sessionFile) ? await transcriptEntries(leaderLifecycle.sessionFile) : [];
		await phase(phases, "observe", async () => {
			observations.subagents = await client!.getSubagents();
			const terminalLeader = [...observations.lifecycle, ...observations.subagents].reverse().find(value => value && typeof value === "object" && "id" in value && value.id === "smoke-leader-id" && "status" in value && value.status === "completed");
			if (!terminalLeader || typeof terminalLeader !== "object" || !("agent" in terminalLeader) || terminalLeader.agent !== "smart-cascade-leader") throw new Error(`Leader did not reach a completed native state: ${JSON.stringify(terminalLeader)}`);
			const executor = [...observations.lifecycle, ...observations.subagents].reverse().find(value => value && typeof value === "object" && "id" in value && value.id === "smoke-leader-id.smoke-executor-id");
			if (!executor) throw new Error("Executor child was never observed under the Leader");
			observations.lifecycleEvidence = { leader: terminalLeader, executor };
			observations.agentIds = ["smoke-leader-id", "smoke-leader-id.smoke-executor-id"];
			const executorSession = executor && typeof executor === "object" && "sessionFile" in executor && typeof executor.sessionFile === "string" ? executor.sessionFile : undefined;
			const executorEntries = executorSession && existsSync(executorSession) ? await transcriptEntries(executorSession) : [];
			const leaderToRoot = hubMessageObserved(rootEntries, "smoke-leader-id", "Main") || hubMessageObserved(leaderEntries, "smoke-leader-id", "Main");
			const executorToLeader = hubMessageObserved(leaderEntries, "smoke-leader-id.smoke-executor-id", "smoke-leader-id") || hubMessageObserved(executorEntries, "smoke-leader-id.smoke-executor-id", "smoke-leader-id");
			observations.hubEvidence = { leaderToRoot, executorToLeader };
			observations.plainHubMessageObserved = leaderToRoot && executorToLeader;
			if (!observations.plainHubMessageObserved) throw new Error(`real Hub evidence not observed: ${JSON.stringify(observations.hubEvidence)}`);
			const projected = (value: unknown): string | undefined => value && typeof value === "object" && "resolvedModel" in value && typeof value.resolvedModel === "string" ? value.resolvedModel : undefined;
			if (!resolvedModelMatches(projected(terminalLeader), parsed.model) || !resolvedModelMatches(projected(executor), parsed.model)) throw new Error(`production model projection not observed: ${JSON.stringify({ leader: projected(terminalLeader), executor: projected(executor) })}`);
		});
		await phase(phases, "patches", async () => {
			const all = await patchFiles(home);
			observations.patchPaths.all = all;
			if (!all.length) throw new Error("no retained isolation patch was captured on disk");
			// Claim each retained patch by what it actually produces, not by parsing the
			// runner's result text: apply it to a clean checkout of the base and look at
			// the resulting bytes.
			const applied: Array<{ path: string; bytes: string; changed: string[] }> = [];
			for (const [index, path] of all.entries()) {
				const candidate = join(root!, `patch-candidate-${index}`);
				await shell(root!, "git", "clone", "--quiet", repo, candidate);
				await shell(candidate, "git", "checkout", "--quiet", base);
				try { await shell(candidate, "git", "apply", path); } catch { continue; }
				const changed = (await shell(candidate, "git", "diff", "--name-only", "--no-renames", "--")).trim().split("\n").filter(Boolean);
				applied.push({ path, bytes: readFileSync(join(candidate, FIXTURE), "utf8"), changed });
			}
			const executorPatch = applied.find(item => item.bytes === EXECUTOR_BYTES);
			const leaderPatch = applied.find(item => item.bytes === FINAL_BYTES);
			observations.patchPaths.executor = executorPatch?.path;
			observations.patchPaths.leader = leaderPatch?.path;
			if (!executorPatch || !leaderPatch) throw new Error(`retained patches did not reproduce the expected Executor/Leader postimages: ${JSON.stringify({ discovered: all, applied: applied.map(item => ({ path: item.path, bytes: item.bytes })) })}`);
			if (JSON.stringify(leaderPatch.changed) !== JSON.stringify([FIXTURE])) throw new Error(`Leader candidate touched unexpected paths: ${JSON.stringify(leaderPatch.changed)}`);
			if (!leaderPatch.bytes.startsWith(executorPatch.bytes)) throw new Error("Leader candidate does not contain the verified Executor postimage before Leader assembly bytes");
		});
		await phase(phases, "parent", async () => {
			const status = await shell(repo, "git", "status", "--porcelain");
			const content = readFileSync(join(repo, FIXTURE), "utf8");
			observations.parentBeforeApply = { status, content };
			if (status || content !== BEFORE) throw new Error("Root parent changed before deliberate apply");
		});
		await client.stop();
		client = undefined;
		await phase(phases, "verify", async () => {
			const terminalLeader = [...observations.lifecycle].reverse().find(value => value && typeof value === "object" && "id" in value && value.id === "smoke-leader-id");
			if (!terminalLeader || !("status" in terminalLeader) || terminalLeader.status !== "completed") throw new Error(`terminal no-active-writer evidence missing: ${JSON.stringify(terminalLeader)}`);
			observations.noActiveWriterObserved = true;
			const candidate = join(root!, "root-verification-candidate");
			await shell(root!, "git", "clone", "--quiet", repo, candidate);
			await shell(candidate, "git", "checkout", "--quiet", base);
			const patch = observations.patchPaths.leader!;
			await shell(candidate, "git", "apply", "--check", patch);
			await shell(candidate, "git", "apply", patch);
			const content = readFileSync(join(candidate, FIXTURE), "utf8");
			const changed = (await shell(candidate, "git", "diff", "--name-only", "--no-renames", "--")).trim().split("\n").filter(Boolean);
			if (content !== FINAL_BYTES || JSON.stringify(changed) !== JSON.stringify([FIXTURE])) throw new Error(`Root verification candidate failed exact bytes/write set: ${JSON.stringify({ content, changed })}`);
			observations.rootAcceptanceVerified = true;
		});
		await phase(phases, "apply", async () => {
			const patch = observations.patchPaths.leader!;
			await shell(repo, "git", "apply", "--check", patch);
			await shell(repo, "git", "apply", patch);
			const content = readFileSync(join(repo, FIXTURE), "utf8");
			const status = await shell(repo, "git", "status", "--porcelain");
			observations.parentAfterApply = { status, content };
			observations.finalFileContent = content;
			if (content !== FINAL_BYTES) throw new Error(`candidate bytes mismatch: ${JSON.stringify(content)}`);
		});
	} catch (error) {
		const report: Report = { version: 1, status: "failed", phase: error instanceof PhaseError ? error.phase : phases.at(-1)?.phase, error: error instanceof Error ? error.message : String(error), phases, observations };
		try { await cleanup(client, root, isolationBase, observations, phases); } catch (cleanupFailure) { report.error += `; cleanup: ${cleanupFailure instanceof Error ? cleanupFailure.message : String(cleanupFailure)}`; }
		process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
		process.exitCode = 1;
		return;
	}
	try { await cleanup(client, root, isolationBase, observations, phases); } catch (error) { cleanupError = error instanceof Error ? error.message : String(error); }
	process.stdout.write(`${JSON.stringify({ version: 1, status: cleanupError ? "failed" : "passed", phase: cleanupError ? "cleanup" : undefined, error: cleanupError, phases, observations }, null, 2)}\n`);
	if (cleanupError) process.exitCode = 1;
}
async function cleanup(client: RpcClient | undefined, root: string | undefined, isolationBase: string | undefined, observations: Observations, phases: PhaseRecord[]): Promise<void> {
	try { if (client) await client.stop(); }
	finally {
		if (isolationBase) {
			const existsAfterStop = existsSync(isolationBase);
			const remainingEntries = existsAfterStop ? await readdir(isolationBase) : [];
			observations.isolationCleanup = { base: isolationBase, existsAfterStop, remainingEntries };
			if (remainingEntries.length) throw new Error(`native isolation cleanup left ${remainingEntries.join(", ")}`);
		}
		if (root && !process.env.SMART_CASCADE_SMOKE_KEEP) await rm(root, { recursive: true, force: true });
		phases.push({ phase: "cleanup", status: "passed" });
	}
}

main().catch(error => {
	process.stdout.write(`${JSON.stringify({ version: 1, status: "failed", phase: "bootstrap", error: error instanceof Error ? error.message : String(error), phases: [], observations: { agentIds: [], lifecycle: [], subagents: [], plainHubMessageObserved: false, patchPaths: { all: [] } } }, null, 2)}\n`);
	process.exitCode = 1;
});
