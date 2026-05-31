// ── Helpers ───────────────────────────────────────────────────────────────────

function parseCookies(header: string | undefined) {
  return Object.fromEntries(
    (header || "").split(";").map((part) => part.trim()).filter(Boolean).map((part) => {
      const index = part.indexOf("=");
      return index === -1 ? [part, ""] : [part.slice(0, index), decodeURIComponent(part.slice(index + 1))];
    })
  );
}

function getField(body: unknown, field: string): string {
  if (body && typeof body === "object" && field in body) {
    const val = (body as Record<string, unknown>)[field];
    return typeof val === "string" ? val.trim() : "";
  }
  return "";
}

function getMessages(body: unknown): Array<{ role: string; content: string }> {
  if (body && typeof body === "object" && "messages" in body) {
    const msgs = (body as Record<string, unknown>).messages;
    if (Array.isArray(msgs)) return msgs as Array<{ role: string; content: string }>;
  }
  return [];
}

function jsonReply(res: any, status: number, payload: unknown) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(payload));
}

// ── Error classification ───────────────────────────────────────────────────────

function classifyError(message: string): string {
  if (
    message.includes("No AI API key") ||
    message.includes("API key in Settings") ||
    message.includes("Rate limit") ||
    message.includes("Invalid or expired API key") ||
    message.includes("Could not reach") ||
    message.includes("AI API error:")
  ) {
    return message; // already user-friendly
  }
  const lower = message.toLowerCase();
  if (lower.includes("401") || lower.includes("unauthorized") || lower.includes("invalid_api_key") || lower.includes("authentication")) {
    return "Invalid or expired API key. Please check your key in Settings.";
  }
  if (lower.includes("429") || lower.includes("rate limit") || lower.includes("too many requests") || lower.includes("quota")) {
    return "Rate limit reached. Please try again later.";
  }
  if (lower.includes("econnrefused") || lower.includes("failed to connect") || lower.includes("failed to fetch") || lower.includes("network")) {
    return "Could not reach the AI provider. Please check your connection and API base URL.";
  }
  // Never expose raw JS exceptions (e.g. "Cannot read properties of undefined") to users.
  return "AI summary generation failed. Please verify your API key and try again.";
}

// ── OpenAI / OpenAI-compatible (GPT, custom) ──────────────────────────────────

async function callOpenAiCompatible(
  apiBaseUrl: string,
  apiKey: string,
  model: string,
  messages: Array<{ role: string; content: string }>,
  context?: string
): Promise<string> {
  const allMessages = context
    ? [{ role: "system", content: context }, ...messages]
    : messages;

  const response = await fetch(`${apiBaseUrl}/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({ model, messages: allMessages, max_tokens: 2000 }),
  });

  const data = await response.json().catch(() => ({})) as Record<string, unknown>;

  if (!response.ok) {
    const errData = data as any;
    const msg = errData?.error?.message || errData?.error || `HTTP ${response.status}`;
    if (response.status === 401) throw new Error("Invalid or expired API key. Please check your key in Settings.");
    if (response.status === 429) throw new Error("Rate limit reached. Please try again later.");
    throw new Error(`AI API error: ${msg}`);
  }

  const answer = (data as any)?.choices?.[0]?.message?.content;
  if (!answer) throw new Error("AI response did not include an answer.");
  return answer;
}

// ── Anthropic Claude ──────────────────────────────────────────────────────────

async function callClaude(
  apiBaseUrl: string,
  apiKey: string,
  model: string,
  messages: Array<{ role: string; content: string }>,
  context?: string
): Promise<string> {
  const systemParts = messages.filter((m) => m.role === "system").map((m) => m.content);
  if (context) systemParts.unshift(context);
  const userMessages = messages
    .filter((m) => m.role !== "system")
    .map((m) => ({ role: m.role === "user" ? "user" : "assistant", content: m.content }));

  const requestBody: Record<string, unknown> = {
    model,
    messages: userMessages,
    max_tokens: 2000,
  };
  if (systemParts.length) requestBody.system = systemParts.join("\n\n");

  const response = await fetch(`${apiBaseUrl}/messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify(requestBody),
  });

  const data = await response.json().catch(() => ({})) as Record<string, unknown>;

  if (!response.ok) {
    const msg = (data as any)?.error?.message || `HTTP ${response.status}`;
    if (response.status === 401) throw new Error("Invalid or expired API key. Please check your key in Settings.");
    if (response.status === 429) throw new Error("Rate limit reached. Please try again later.");
    throw new Error(`AI API error: ${msg}`);
  }

  const answer = (data as any)?.content?.[0]?.text;
  if (!answer) throw new Error("AI response did not include an answer.");
  return answer;
}

// ── Google Gemini ──────────────────────────────────────────────────────────────

async function callGemini(
  apiBaseUrl: string,
  apiKey: string,
  model: string,
  messages: Array<{ role: string; content: string }>,
  context?: string
): Promise<string> {
  const contents = messages
    .filter((m) => m.role !== "system")
    .map((m) => ({
      role: m.role === "user" ? "user" : "model",
      parts: [{ text: m.content }],
    }));

  const requestBody: Record<string, unknown> = { contents };
  if (context) requestBody.systemInstruction = { parts: [{ text: context }] };

  const url = `${apiBaseUrl}/models/${model}:generateContent?key=${apiKey}`;

  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(requestBody),
  });

  const data = await response.json().catch(() => ({})) as Record<string, unknown>;

  if (!response.ok) {
    const msg = (data as any)?.error?.message || `HTTP ${response.status}`;
    if (response.status === 400 || response.status === 401 || response.status === 403) {
      throw new Error("Invalid or expired API key. Please check your key in Settings.");
    }
    if (response.status === 429) throw new Error("Rate limit reached. Please try again later.");
    throw new Error(`AI API error: ${msg}`);
  }

  const answer = (data as any)?.candidates?.[0]?.content?.parts?.[0]?.text;
  if (!answer) throw new Error("AI response did not include an answer.");
  return answer;
}

// ── Proxy headers helper ───────────────────────────────────────────────────────

function buildProxyHeaders(sessionToken?: string): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const authToken = process.env.RANKING_API_AUTH_TOKEN?.trim();
  if (authToken) headers["Authorization"] = `Bearer ${authToken}`;
  if (sessionToken) headers["X-Session-Token"] = sessionToken;
  return headers;
}

// Converts FastAPI {"detail":"..."} error responses to user-friendly {"error":"..."}.
function classifyBackendError(status: number, detail: string): string {
  // The ranking backend's /ai/chat already returns user-friendly detail strings —
  // pass them through directly, only fall back for empty/technical messages.
  if (detail && !detail.match(/^(internal server error|unexpected error)/i)) {
    return detail;
  }
  if (status === 401 || status === 403) return "Invalid or expired API key. Please check your key in Settings.";
  if (status === 429) return "Rate limit reached. Please try again later.";
  return "AI summary generation failed. Please try again.";
}

// ── Main handler ──────────────────────────────────────────────────────────────
//
// Design: The ranking backend owns AI key storage (encrypted with AI_SETTINGS_ENCRYPTION_KEY).
// GET /settings/ai intentionally does NOT return the decrypted key — it only returns hasApiKey.
// Therefore the Express layer CANNOT decrypt the stored key itself.
// The correct approach is to proxy /api/ai/chat → ${RANKING_API_URL}/ai/chat, which handles:
//   - Authenticated users: looks up session → decrypts stored key → calls AI provider
//   - Unauthenticated (BYOK): uses body.apiKey directly → calls AI provider
// When RANKING_API_URL is absent (local dev without backend), fall back to direct provider calls.

export async function handleAiChatRequest(body: unknown, req: any, res: any) {
  const sessionToken = parseCookies(req.headers?.cookie).research_ai_session;
  const clientApiKey = getField(body, "apiKey");
  const backendUrl = (process.env.RANKING_API_URL || "").trim().replace(/\/+$/, "");

  // ── Temporary debug logs (no actual key values logged) ────────────────────
  console.log("[ai/chat] body.apiKey present:", Boolean(clientApiKey));
  console.log("[ai/chat] session cookie present:", Boolean(sessionToken));

  if (sessionToken && backendUrl) {
    // Check whether the session has a configured key — purely for diagnostic logging.
    try {
      const sr = await fetch(`${backendUrl}/settings/ai`, { headers: buildProxyHeaders(sessionToken) });
      const sd = await sr.json().catch(() => ({})) as Record<string, unknown>;
      console.log("[ai/chat] /settings/ai →", sr.status, "hasApiKey:", sd.hasApiKey, "provider:", sd.provider);
    } catch (e) {
      console.log("[ai/chat] /settings/ai check failed:", e instanceof Error ? e.message : String(e));
    }
  }
  // ── End debug logs ─────────────────────────────────────────────────────────

  if (backendUrl) {
    // ── Path A: proxy to ranking backend (production / dev with backend) ────
    try {
      const r = await fetch(`${backendUrl}/ai/chat`, {
        method: "POST",
        headers: buildProxyHeaders(sessionToken),
        body: JSON.stringify(body),
      });
      const data = await r.json().catch(() => ({})) as Record<string, unknown>;

      if (!r.ok) {
        const detail = String((data as any).detail || (data as any).error || "");
        const userMsg = classifyBackendError(r.status, detail);
        console.log("[ai/chat] backend error", r.status, "->", userMsg);
        return jsonReply(res, r.status, { error: userMsg });
      }

      return jsonReply(res, 200, data);
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      console.error("[ai/chat] proxy network error:", msg);
      return jsonReply(res, 502, { error: "Could not reach the AI service. Please check your connection and try again." });
    }
  }

  // ── Path B: no RANKING_API_URL — dev fallback, call provider directly ─────
  try {
    const provider = getField(body, "provider") || "gpt";
    const apiBaseUrl = getField(body, "apiBaseUrl");
    const model = getField(body, "model");
    const context = getField(body, "context") || undefined;
    const messages = getMessages(body);

    if (!messages.length) return jsonReply(res, 400, { error: "No messages provided." });
    if (!clientApiKey) return jsonReply(res, 400, { error: "No AI API key configured. Please add an API key in Settings." });

    let answer: string;
    if (provider === "claude") {
      answer = await callClaude(apiBaseUrl || "https://api.anthropic.com/v1", clientApiKey, model || "claude-sonnet-4-20250514", messages, context);
    } else if (provider === "gemini") {
      answer = await callGemini(apiBaseUrl || "https://generativelanguage.googleapis.com/v1beta", clientApiKey, model || "gemini-2.5-flash", messages, context);
    } else {
      answer = await callOpenAiCompatible(apiBaseUrl || "https://api.openai.com/v1", clientApiKey, model || "gpt-4.1", messages, context);
    }
    jsonReply(res, 200, { answer });
  } catch (error) {
    const raw = error instanceof Error ? error.message : String(error);
    jsonReply(res, 500, { error: classifyError(raw) });
  }
}
