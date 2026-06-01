import express from "express";
import { createServer } from "http";
import path from "path";
import { fileURLToPath } from "url";
import { handleAiChatRequest } from "./ai";
import { handleGetAiSettings, handleGetSaved, handleGoogleCallback, handleGoogleStart, handleLogin, handleLogout, handleMe, handleRegister, handleRequestCode, handleResetPassword, handleSaveAiSettings, handleSetSaved, handleSupportTicket } from "./auth";
import { handleRankingHealthRequest, handleRankingRankRequest } from "./ranking";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function startServer() {
  const app = express();
  const server = createServer(app);
  app.use(express.json({ limit: "1mb" }));

  app.post("/api/ai/chat", async (req, res) => {
    await handleAiChatRequest(req.body, req, res);
  });

  app.post("/api/auth/request-code", async (req, res) => {
    await handleRequestCode(req.body, res);
  });

  app.post("/api/auth/register", async (req, res) => {
    await handleRegister(req.body, res);
  });

  app.post("/api/auth/login", async (req, res) => {
    await handleLogin(req.body, res);
  });

  app.post("/api/auth/reset-password", async (req, res) => {
    await handleResetPassword(req.body, res);
  });

  app.get("/api/auth/google/start", (req, res) => {
    handleGoogleStart(req, res);
  });

  app.get("/api/auth/google/callback", async (req, res) => {
    await handleGoogleCallback(req, res);
  });

  app.post("/api/auth/logout", async (req, res) => {
    await handleLogout(req, res);
  });

  app.get("/api/auth/me", async (req, res) => {
    await handleMe(req, res);
  });

  app.get("/api/saved-researchers", async (req, res) => {
    await handleGetSaved(req, res);
  });

  app.put("/api/saved-researchers", async (req, res) => {
    await handleSetSaved(req, req.body, res);
  });

  app.get("/api/settings/ai", async (req, res) => {
    await handleGetAiSettings(req, res);
  });

  app.put("/api/settings/ai", async (req, res) => {
    await handleSaveAiSettings(req, req.body, res);
  });

  app.get("/api/ranking/health", async (_req, res) => {
    await handleRankingHealthRequest({}, res);
  });

  app.post("/api/ranking/rank", async (req, res) => {
    await handleRankingRankRequest(req.body, res);
  });

  app.post("/api/support", async (req, res) => {
    await handleSupportTicket(req.body, req, res);
  });

  app.get("/health", (_req, res) => {
    res.json({ ok: true, service: "research-ai" });
  });

  // Serve static files from dist/public in production
  const staticPath =
    process.env.NODE_ENV === "production"
      ? path.resolve(__dirname, "public")
      : path.resolve(__dirname, "..", "dist", "public");

  app.use(express.static(staticPath));

  // Handle client-side routing - serve index.html for all routes
  app.get("*", (_req, res) => {
    res.sendFile(path.join(staticPath, "index.html"));
  });

  const port = Number(process.env.PORT || 3000);
  const host = process.env.HOST || "0.0.0.0";

  server.listen(port, host, () => {
    console.log(`Server running on http://${host}:${port}/`);
  });
}

startServer().catch((error) => {
  console.error("Failed to start ResearchAI server:", error);
  process.exit(1);
});
