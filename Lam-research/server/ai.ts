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

// ── Stored key retrieval for authenticated users ───────────────────────────────

async function fetchStoredAiSettings(sessionToken: string): Promise<{
  apiKey?: string;
  provider?: string;
  model?: string;
  apiBaseUrl?: string;
} | null> {
  const backendUrl = (process.env.RANKING_API_URL || "").trim().replace(/\/+$/, "");
  if (!backendUrl) return null;
  try {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "X-Session-Token": sessionToken,
    };
    const authToken = process.env.RANKING_API_AUTH_TOKEN?.trim();
    if (authToken) headers["Authorization"] = `Bearer ${authToken}`;
    const r = await fetch(`${backendUrl}/settings/ai`, { headers });
    if (!r.ok) return null;
    const data = await r.json().catch(() => null) as Record<string, unknown> | null;
    if (!data?.hasApiKey) return null;
    return {
      apiKey: typeof data.apiKey === "string" ? data.apiKey : undefined,
      provider: typeof data.provider === "string" ? data.provider : undefined,
      model: typeof data.model === "string" ? data.model : undefined,
      apiBaseUrl: typeof data.apiBaseUrl === "string" ? data.apiBaseUrl : undefined,
    };
  } catch {
    return null;
  }
}

// ── Main handler ──────────────────────────────────────────────────────────────

export async function handleAiChatRequest(body: unknown, req: any, res: any) {
  try {
    const provider = getField(body, "provider") || "gpt";
    const apiBaseUrl = getField(body, "apiBaseUrl");
    const clientApiKey = getField(body, "apiKey");
    const model = getField(body, "model");
    const context = getField(body, "context") || undefined;
    const messages = getMessages(body);

    if (!messages.length) {
      return jsonReply(res, 400, { error: "No messages provided." });
    }

    // Resolve effective credentials: prefer client-supplied key, then fall back to
    // server-side stored key for authenticated users.
    let effectiveApiKey = clientApiKey;
    let effectiveProvider = provider;
    let effectiveModel = model;
    let effectiveBaseUrl = apiBaseUrl;

    if (!effectiveApiKey) {
      const sessionToken = parseCookies(req.headers?.cookie).research_ai_session;
      if (sessionToken) {
        const stored = await fetchStoredAiSettings(sessionToken);
        if (stored?.apiKey) {
          effectiveApiKey = stored.apiKey;
          effectiveProvider = stored.provider || provider;
          effectiveModel = stored.model || model;
          effectiveBaseUrl = stored.apiBaseUrl || apiBaseUrl;
        }
      }
    }

    if (!effectiveApiKey) {
      return jsonReply(res, 400, {
        error: "No AI API key configured. Please add an API key in Settings.",
      });
    }

    let answer: string;

    if (effectiveProvider === "claude") {
      answer = await callClaude(
        effectiveBaseUrl || "https://api.anthropic.com/v1",
        effectiveApiKey,
        effectiveModel || "claude-sonnet-4-20250514",
        messages,
        context
      );
    } else if (effectiveProvider === "gemini") {
      answer = await callGemini(
        effectiveBaseUrl || "https://generativelanguage.googleapis.com/v1beta",
        effectiveApiKey,
        effectiveModel || "gemini-2.5-flash",
        messages,
        context
      );
    } else {
      // OpenAI or any OpenAI-compatible custom endpoint
      answer = await callOpenAiCompatible(
        effectiveBaseUrl || "https://api.openai.com/v1",
        effectiveApiKey,
        effectiveModel || "gpt-4.1",
        messages,
        context
      );
    }

    jsonReply(res, 200, { answer });
  } catch (error) {
    const raw = error instanceof Error ? error.message : String(error);
    jsonReply(res, 500, { error: classifyError(raw) });
  }
}
