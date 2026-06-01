import crypto from "crypto";

const GOOGLE_STATE_TTL_SECONDS = 10 * 60;
const SESSION_DAYS = 14;

// ── Backend proxy helper ───────────────────────────────────────────────────

function backendBaseUrl() {
  return (process.env.RANKING_API_URL || "").trim().replace(/\/+$/, "");
}

async function backendCall(path: string, options: RequestInit = {}, sessionToken?: string): Promise<Response> {
  const url = `${backendBaseUrl()}${path}`;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const authToken = process.env.RANKING_API_AUTH_TOKEN?.trim();
  if (authToken) headers["Authorization"] = `Bearer ${authToken}`;
  if (sessionToken) headers["X-Session-Token"] = sessionToken;
  return fetch(url, { ...options, headers: { ...headers, ...(options.headers as Record<string, string> | undefined) } });
}

function getSessionToken(req: any): string | undefined {
  return parseCookies(req.headers?.cookie).research_ai_session;
}

function createToken() {
  return crypto.randomBytes(32).toString("hex");
}

function parseCookies(header: string | undefined) {
  return Object.fromEntries((header || "").split(";").map((part) => part.trim()).filter(Boolean).map((part) => {
    const index = part.indexOf("=");
    return index === -1 ? [part, ""] : [part.slice(0, index), decodeURIComponent(part.slice(index + 1))];
  }));
}

function sendJson(res: any, status: number, payload: unknown, cookies: string[] = []) {
  const headers: Record<string, string | string[]> = { "Content-Type": "application/json" };
  if (cookies.length) headers["Set-Cookie"] = cookies;
  res.writeHead(status, headers);
  res.end(JSON.stringify(payload));
}

function secureCookieSuffix() {
  return process.env.NODE_ENV === "production" ? "; Secure" : "";
}

function sessionCookie(token: string) {
  return `research_ai_session=${encodeURIComponent(token)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${SESSION_DAYS * 24 * 60 * 60}${secureCookieSuffix()}`;
}

function clearSessionCookie() {
  return `research_ai_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0${secureCookieSuffix()}`;
}

function googleStateCookie(state: string) {
  return `research_ai_google_state=${encodeURIComponent(state)}; Path=/api/auth/google; HttpOnly; SameSite=Lax; Max-Age=${GOOGLE_STATE_TTL_SECONDS}${secureCookieSuffix()}`;
}

function clearGoogleStateCookie() {
  return `research_ai_google_state=; Path=/api/auth/google; HttpOnly; SameSite=Lax; Max-Age=0${secureCookieSuffix()}`;
}

function redirect(res: any, location: string, cookies: string[] = []) {
  const headers: Record<string, string | string[]> = { Location: location, "Cache-Control": "no-store" };
  if (cookies.length) headers["Set-Cookie"] = cookies;
  res.writeHead(302, headers);
  res.end();
}

function requestOrigin(req: any) {
  const forwardedProto = String(req.headers?.["x-forwarded-proto"] || "").split(",")[0].trim();
  const proto = forwardedProto || (process.env.NODE_ENV === "production" ? "https" : "http");
  const host = String(req.headers?.["x-forwarded-host"] || req.headers?.host || "localhost:3000").split(",")[0].trim();
  return `${proto}://${host}`;
}

function googleRedirectUri(req: any) {
  return process.env.GOOGLE_REDIRECT_URI?.trim() || `${requestOrigin(req)}/api/auth/google/callback`;
}

export async function getCurrentUser(req: any): Promise<{ id: string; [key: string]: unknown } | undefined> {
  const token = getSessionToken(req);
  if (!token) return undefined;
  const r = await backendCall("/auth/me", {}, token).catch(() => null);
  if (!r?.ok) return undefined;
  const data = await r.json().catch(() => ({}));
  return data.user ? { ...data.user, _sessionToken: token } : undefined;
}

export async function handleRequestCode(body: any, res: any) {
  const r = await backendCall("/auth/request-code", { method: "POST", body: JSON.stringify(body) }).catch(() => null);
  if (!r) return sendJson(res, 502, { error: "Backend unavailable." });
  const data = await r.json().catch(() => ({}));
  sendJson(res, r.status, data);
}

export async function handleRegister(body: any, res: any) {
  const r = await backendCall("/auth/register", { method: "POST", body: JSON.stringify(body) }).catch(() => null);
  if (!r) return sendJson(res, 502, { error: "Backend unavailable." });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) return sendJson(res, r.status, { error: data.detail || "Registration failed." });
  sendJson(res, 200, { user: data.user }, [sessionCookie(data.token)]);
}

export async function handleLogin(body: any, res: any) {
  const r = await backendCall("/auth/login", { method: "POST", body: JSON.stringify(body) }).catch(() => null);
  if (!r) return sendJson(res, 502, { error: "Backend unavailable." });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) return sendJson(res, r.status, { error: data.detail || "Login failed." });
  sendJson(res, 200, { user: data.user }, [sessionCookie(data.token)]);
}

export function handleGoogleStart(req: any, res: any) {
  const clientId = process.env.GOOGLE_CLIENT_ID?.trim();
  const clientSecret = process.env.GOOGLE_CLIENT_SECRET?.trim();
  if (!clientId || !clientSecret) return sendJson(res, 503, { error: "Google sign-in is not configured. Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and the matching Google OAuth redirect URL." });
  const state = createToken();
  const authUrl = new URL("https://accounts.google.com/o/oauth2/v2/auth");
  authUrl.searchParams.set("client_id", clientId);
  authUrl.searchParams.set("redirect_uri", googleRedirectUri(req));
  authUrl.searchParams.set("response_type", "code");
  authUrl.searchParams.set("scope", "openid email profile");
  authUrl.searchParams.set("state", state);
  authUrl.searchParams.set("prompt", "select_account");
  redirect(res, authUrl.toString(), [googleStateCookie(state)]);
}

export async function handleGoogleCallback(req: any, res: any) {
  const url = new URL(req.url || "/api/auth/google/callback", requestOrigin(req));
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  const storedState = parseCookies(req.headers?.cookie).research_ai_google_state;
  if (!code || !state || !storedState || state !== storedState) return sendJson(res, 400, { error: "Invalid Google sign-in response." }, [clearGoogleStateCookie()]);
  const clientId = process.env.GOOGLE_CLIENT_ID?.trim();
  const clientSecret = process.env.GOOGLE_CLIENT_SECRET?.trim();
  if (!clientId || !clientSecret) return sendJson(res, 503, { error: "Google sign-in is not configured on the server." }, [clearGoogleStateCookie()]);

  const tokenResponse = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      code,
      client_id: clientId,
      client_secret: clientSecret,
      redirect_uri: googleRedirectUri(req),
      grant_type: "authorization_code",
    }),
  });
  if (!tokenResponse.ok) return sendJson(res, 502, { error: "Google token exchange failed." }, [clearGoogleStateCookie()]);
  const tokenPayload = await tokenResponse.json() as { access_token?: string };
  if (!tokenPayload.access_token) return sendJson(res, 502, { error: "Google did not return an access token." }, [clearGoogleStateCookie()]);

  const profileResponse = await fetch("https://www.googleapis.com/oauth2/v3/userinfo", {
    headers: { Authorization: `Bearer ${tokenPayload.access_token}` },
  });
  if (!profileResponse.ok) return sendJson(res, 502, { error: "Google profile lookup failed." }, [clearGoogleStateCookie()]);
  const profile = await profileResponse.json() as { sub?: string; email?: string; name?: string; picture?: string };
  if (!profile.sub) return sendJson(res, 502, { error: "Google profile is missing a stable user id." }, [clearGoogleStateCookie()]);

  // Delegate user upsert + session creation to backend.
  const upsertRes = await backendCall("/auth/google-upsert", {
    method: "POST",
    body: JSON.stringify({ sub: profile.sub, email: profile.email ?? null, name: profile.name ?? null, picture: profile.picture ?? null }),
  }).catch(() => null);
  if (!upsertRes?.ok) return sendJson(res, 502, { error: "Google sign-in could not complete." }, [clearGoogleStateCookie()]);
  const upsertData = await upsertRes.json().catch(() => ({})) as { token?: string };
  if (!upsertData.token) return sendJson(res, 502, { error: "Google sign-in did not return a session." }, [clearGoogleStateCookie()]);
  redirect(res, "/", [sessionCookie(upsertData.token), clearGoogleStateCookie()]);
}

export async function handleMe(req: any, res: any) {
  const token = getSessionToken(req);
  if (!token) return sendJson(res, 200, { user: null });
  const r = await backendCall("/auth/me", {}, token).catch(() => null);
  if (!r) return sendJson(res, 200, { user: null });
  const data = await r.json().catch(() => ({}));
  sendJson(res, 200, data);
}

export async function handleLogout(req: any, res: any) {
  const token = getSessionToken(req);
  if (token) await backendCall("/auth/logout", { method: "POST" }, token).catch(() => {});
  sendJson(res, 200, { ok: true }, [clearSessionCookie()]);
}

export async function handleGetAiSettings(req: any, res: any) {
  const token = getSessionToken(req);
  if (!token) return sendJson(res, 401, { error: "Login required." });
  const r = await backendCall("/settings/ai", {}, token).catch(() => null);
  if (!r) return sendJson(res, 502, { error: "Backend unavailable." });
  const data = await r.json().catch(() => ({}));
  sendJson(res, r.status, data);
}

export async function handleSaveAiSettings(req: any, body: any, res: any) {
  const token = getSessionToken(req);
  if (!token) return sendJson(res, 401, { error: "Login required." });
  const r = await backendCall("/settings/ai", { method: "PUT", body: JSON.stringify(body) }, token).catch(() => null);
  if (!r) return sendJson(res, 502, { error: "Backend unavailable." });
  const data = await r.json().catch(() => ({}));
  sendJson(res, r.status, data);
}

export async function handleGetSaved(req: any, res: any) {
  const token = getSessionToken(req);
  if (!token) return sendJson(res, 401, { error: "Login required." });
  const r = await backendCall("/saved-researchers", {}, token).catch(() => null);
  if (!r) return sendJson(res, 502, { error: "Backend unavailable." });
  const data = await r.json().catch(() => ({}));
  sendJson(res, r.status, data);
}

export async function handleSetSaved(req: any, body: any, res: any) {
  const token = getSessionToken(req);
  if (!token) return sendJson(res, 401, { error: "Login required." });
  const r = await backendCall("/saved-researchers", { method: "PUT", body: JSON.stringify(body) }, token).catch(() => null);
  if (!r) return sendJson(res, 502, { error: "Backend unavailable." });
  const data = await r.json().catch(() => ({}));
  sendJson(res, r.status, data);
}

export async function handleResetPassword(body: any, res: any) {
  const r = await backendCall("/auth/reset-password", { method: "POST", body: JSON.stringify(body) }).catch(() => null);
  if (!r) return sendJson(res, 502, { error: "Backend unavailable." });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) return sendJson(res, r.status, { error: data.detail || "Password reset failed." });
  sendJson(res, 200, data);
}

export async function handleSupportTicket(body: any, res: any) {
  // TODO: Connect to a ticketing/email service (SendGrid, Resend, Jira, Linear, etc.)
  // For now, log to server console. Replace with actual notification logic before go-live.
  const { name, email, message } = body || {};
  console.log("[Support Ticket]", {
    name: name || "(anonymous)",
    email: email || "(no email)",
    message: (message || "").slice(0, 2000),
    ts: new Date().toISOString(),
  });
  sendJson(res, 200, { ok: true });
}
