import { readFile, stat } from "node:fs/promises";

const MAX_TRANSCRIPT_BYTES = 16 * 1024 * 1024;

export type TranscriptEnvelope = { type?: unknown; customType?: unknown; details?: unknown; message?: unknown; id?: unknown; timestamp?: unknown };
export type MessageEnvelope = { role?: unknown; content?: unknown; toolName?: unknown; toolCallId?: unknown; details?: unknown; isError?: unknown; stopReason?: unknown; errorStatus?: unknown; errorMessage?: unknown; timestamp?: unknown };

export function messageRecord(value: unknown): MessageEnvelope | undefined {
	if (!value || typeof value !== "object") return undefined;
	const envelope = value as TranscriptEnvelope;
	if (envelope.type === "message" && envelope.message && typeof envelope.message === "object") return envelope.message as MessageEnvelope;
	return value as MessageEnvelope;
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
