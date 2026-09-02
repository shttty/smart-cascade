import { lstat, readFile, stat } from "node:fs/promises";
import { join } from "node:path";

const MAX_TRANSCRIPT_BYTES = 16 * 1024 * 1024;

export type NativeTaskEnvelope = {
	id: string;
	agent: string;
	agentSource: "user";
	parentToolCallId?: string;
	parentSessionFile?: string;
	sessionSource?: "lifecycle" | "rpc_snapshot" | "native_session_tree";
	jobStatus: "completed";
	envelopeStatus: "completed";
	schemaMode: "strict";
	isolated: true;
	patchPath: string;
	settlement: Record<string, unknown>;
	modelRole: string;
	resolvedModel?: string;
	sessionFile: string;
};

export type TranscriptEnvelope = { type?: unknown; customType?: unknown; details?: unknown; message?: unknown; id?: unknown; timestamp?: unknown };
export type MessageEnvelope = { role?: unknown; content?: unknown; toolName?: unknown; toolCallId?: unknown; details?: unknown; isError?: unknown; stopReason?: unknown; errorStatus?: unknown; errorMessage?: unknown; timestamp?: unknown };
type ToolCallEnvelope = { type?: unknown; id?: unknown; name?: unknown; arguments?: unknown };
type TaskSpawnMetadata = { agentSource?: unknown; modelRole?: unknown };
type HubJob = { id?: unknown; type?: unknown; status?: unknown; resolvedModel?: unknown; resultText?: unknown; agentSource?: unknown; modelRole?: unknown };
export type NativeSessionTreeEvidence = { sessionFile: string; parentToolCallId: string; nativeSessionId: string; cwd: string; parentCwd: string };

export function messageRecord(value: unknown): MessageEnvelope | undefined {
	if (!value || typeof value !== "object") return undefined;
	const envelope = value as TranscriptEnvelope;
	if (envelope.type === "message" && envelope.message && typeof envelope.message === "object") return envelope.message as MessageEnvelope;
	return value as MessageEnvelope;
}

export function strictTaskInvocationObserved(entries: readonly unknown[], id: string, agent: string): boolean {
	const localName = id.includes(".") ? id.slice(id.lastIndexOf(".") + 1) : id;
	for (const entry of entries) {
		const message = messageRecord(entry);
		if (message?.role !== "assistant" || !Array.isArray(message.content)) continue;
		for (const value of message.content) {
			if (!value || typeof value !== "object") continue;
			const item = value as ToolCallEnvelope;
			if (item.type !== "toolCall" || item.name !== "task") continue;
			const outer = item.arguments as { tasks?: unknown } | undefined;
			const candidates = Array.isArray(outer?.tasks) ? outer.tasks : [outer];
			for (const candidate of candidates) {
				const args = candidate as { name?: unknown; agent?: unknown; isolated?: unknown; schemaMode?: unknown; outputSchema?: unknown } | undefined;
				const schemaPresent = (typeof args?.outputSchema === "string" && args.outputSchema.length > 0) || (!!args?.outputSchema && typeof args.outputSchema === "object");
				const nameMatches = args?.name === id || args?.name === localName;
				if (nameMatches && args?.agent === agent && args.isolated === true && args.schemaMode === "strict" && schemaPresent) return true;
			}
		}
	}
	return false;
}

export function taskInvocationToolCallId(entries: readonly unknown[], name: string, agent: string): string | undefined {
	for (const entry of entries) {
		const message = messageRecord(entry);
		if (message?.role !== "assistant" || !Array.isArray(message.content)) continue;
		for (const value of message.content) {
			if (!value || typeof value !== "object") continue;
			const item = value as ToolCallEnvelope;
			if (item.type !== "toolCall" || item.name !== "task" || typeof item.id !== "string") continue;
			const outer = item.arguments as { tasks?: unknown } | undefined;
			const candidates = Array.isArray(outer?.tasks) ? outer.tasks : [outer];
			if (candidates.some(candidate => {
				const args = candidate as { name?: unknown; agent?: unknown } | undefined;
				return args?.name === name && args.agent === agent;
			})) return item.id;
		}
	}
	return undefined;
}

export function taskSpawnMetadata(entries: readonly unknown[], id: string): TaskSpawnMetadata | undefined {
	for (const entry of entries) {
		const message = messageRecord(entry);
		if (message?.role !== "toolResult" || message.toolName !== "task" || !message.details || typeof message.details !== "object") continue;
		const progress = (message.details as { progress?: unknown }).progress;
		if (!Array.isArray(progress)) continue;
		for (const value of progress) {
			if (value && typeof value === "object" && "id" in value && value.id === id) return value as TaskSpawnMetadata;
		}
	}
	return undefined;
}

export function parseNativeTaskEnvelope(resultText: string, job: HubJob, entries: readonly unknown[]): NativeTaskEnvelope | undefined {
	const closeTag = "</task-result>";
	if (!resultText.startsWith("<task-result ") || resultText.indexOf("<task-result ", 1) !== -1 || resultText.indexOf(closeTag) !== resultText.lastIndexOf(closeTag)) return undefined;
	const close = resultText.indexOf(closeTag);
	if (close < 0) return undefined;
	const frame = resultText.slice(0, close + closeTag.length);
	const trailer = resultText.slice(frame.length);
	const expectedTrailer = `\n\n${job.id} is now idle — message it via \`hub\` to follow up; transcript at history://${job.id}`;
	if (trailer && trailer !== expectedTrailer) return undefined;
	for (const tag of ["<output>", "</output>", "<merge-summary>", "</merge-summary>"]) {
		if (frame.indexOf(tag) < 0 || frame.indexOf(tag) !== frame.lastIndexOf(tag)) return undefined;
	}
	if (frame.includes("<preview")) return undefined;
	const envelope = frame.match(/^<task-result id="([^"]+)" agent="([^"]+)" status="([^"]+)" duration="[^"]+">\n(?:<meta lines="\d+" size="[^"\n]+" \/>\n)?<output>\n([\s\S]*?)\n<\/output>\n<merge-summary>\nIsolation: changes captured at `([^`]+)` \(apply=false\)\. Not applied\.\n<\/merge-summary>\n<\/task-result>$/);
	if (!envelope || envelope[3] !== "completed" || job.id !== envelope[1] || !strictTaskInvocationObserved(entries, envelope[1], envelope[2])) return undefined;
	let settlement: unknown;
	try { settlement = JSON.parse(envelope[4]); } catch { return undefined; }
	if (!settlement || typeof settlement !== "object" || Array.isArray(settlement)) return undefined;
	const spawn = taskSpawnMetadata(entries, envelope[1]);
	const metadata = spawn ?? job;
	if (metadata.agentSource !== "user" || typeof metadata.modelRole !== "string") return undefined;
	return {
		id: envelope[1], agent: envelope[2], agentSource: "user", jobStatus: "completed", envelopeStatus: "completed",
		schemaMode: "strict", isolated: true, patchPath: envelope[5], settlement: settlement as Record<string, unknown>,
		modelRole: metadata.modelRole, resolvedModel: typeof job.resolvedModel === "string" ? job.resolvedModel : undefined,
		sessionFile: "",
	};
}

export function nativeTaskEnvelopes(entries: readonly unknown[]): NativeTaskEnvelope[] {
	const envelopes: NativeTaskEnvelope[] = [];
	for (const entry of entries) {
		const message = messageRecord(entry);
		if (message?.role !== "toolResult" || message.toolName !== "hub" || !message.details || typeof message.details !== "object") continue;
		const jobs = (message.details as { jobs?: unknown }).jobs;
		if (!Array.isArray(jobs)) continue;
		for (const value of jobs) {
			if (!value || typeof value !== "object") continue;
			const job = value as HubJob;
			if (job.type !== "task" || job.status !== "completed" || typeof job.resultText !== "string") continue;
			const envelope = parseNativeTaskEnvelope(job.resultText, job, entries);
			if (envelope) envelopes.push(envelope);
		}
	}
	return envelopes;
}

export function nativeTaskEnvelopeById(envelopes: readonly NativeTaskEnvelope[], id: string): NativeTaskEnvelope | undefined {
	return envelopes.find(envelope => envelope.id === id);
}

export async function transcriptEntries(path: string): Promise<unknown[]> {
	const info = await stat(path);
	if (info.size > MAX_TRANSCRIPT_BYTES) throw new Error(`native transcript exceeds ${MAX_TRANSCRIPT_BYTES} bytes: ${path}`);
	const entries: unknown[] = [];
	for (const [index, line] of (await readFile(path, "utf8")).split("\n").entries()) {
		if (!line.trim()) continue;
		try { entries.push(JSON.parse(line)); }
		catch { throw new Error(`invalid native transcript JSON at ${path}:${index + 1}`); }
	}
	return entries;
}

export function sessionHeader(entries: readonly unknown[]): { id: string; cwd: string } | undefined {
	const matches = entries.filter(value => value && typeof value === "object" && "type" in value && value.type === "session");
	if (matches.length !== 1) return undefined;
	const header = matches[0] as { id?: unknown; cwd?: unknown };
	return typeof header.id === "string" && header.id.length > 0 && typeof header.cwd === "string" && header.cwd.length > 0 ? { id: header.id, cwd: header.cwd } : undefined;
}

export async function nativeChildSessionFromTree(
	parentSessionFile: string,
	runtimeId: string,
	taskName: string,
	agent: string,
	cwdAllowed: (cwd: string, parentCwd: string) => boolean,
): Promise<NativeSessionTreeEvidence | undefined> {
	try {
		if (!parentSessionFile.endsWith(".jsonl") || !(await lstat(parentSessionFile)).isFile()) return undefined;
		const parentEntries = await transcriptEntries(parentSessionFile);
		const parent = sessionHeader(parentEntries);
		const parentToolCallId = taskInvocationToolCallId(parentEntries, taskName, agent);
		if (!parent || !parentToolCallId || !strictTaskInvocationObserved(parentEntries, runtimeId, agent)) return undefined;
		const parentStem = parentSessionFile.slice(0, -".jsonl".length);
		if (!(await lstat(parentStem)).isDirectory()) return undefined;
		const sessionFile = join(parentStem, `${runtimeId}.jsonl`);
		if (!(await lstat(sessionFile)).isFile()) return undefined;
		const childEntries = await transcriptEntries(sessionFile);
		const child = sessionHeader(childEntries);
		const inits = childEntries.filter(value => value && typeof value === "object" && "type" in value && value.type === "session_init") as Array<{ agent?: unknown }>;
		if (!child || inits.length !== 1 || inits[0].agent !== agent || !cwdAllowed(child.cwd, parent.cwd)) return undefined;
		return { sessionFile, parentToolCallId, nativeSessionId: child.id, cwd: child.cwd, parentCwd: parent.cwd };
	} catch {
		return undefined;
	}
}
