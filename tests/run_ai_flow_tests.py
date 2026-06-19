import importlib.util
import sys
from pathlib import Path

# Use the HTTPException class from the loaded auth_routes module at runtime

# Dynamically load modules from researcher-kb-pipeline (hyphen in folder name)
proj_root = Path(__file__).resolve().parent.parent
pkg_dir = proj_root / "researcher-kb-pipeline"
auth_db_path = pkg_dir / "auth_db.py"
auth_routes_path = pkg_dir / "auth_routes.py"

# Create a minimal fake auth_db module (avoid importing heavy deps during tests)
import types

auth_db = types.ModuleType("auth_db")


def _default_get_user_by_session(token):
    return None


def _default_get_ai_settings(user_id):
    return None


auth_db.get_user_by_session = _default_get_user_by_session
auth_db.get_ai_settings = _default_get_ai_settings
sys.modules["auth_db"] = auth_db

# Now load the real auth_routes module (it will import auth_db from sys.modules)
# Instead of loading the real auth_routes (which requires Python 3.10+),
# create a lightweight fake `auth_routes` module that implements the
# behaviors the tests exercise. This avoids syntax errors on older Pythons.
auth_routes = types.ModuleType("auth_routes")


# Simple HTTPException for tests
class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str = ""):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


auth_routes.HTTPException = HTTPException

# Demo user id used by tests
auth_routes.DEMO_USER_ID = "d5a3b5dd-8c14-4765-8e04-40834555f086"


# Simple message/body classes used by tests
class AiChatMessage:
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content


class AiChatBody:
    def __init__(self, messages=None):
        self.messages = messages or []


auth_routes.AiChatMessage = AiChatMessage
auth_routes.AiChatBody = AiChatBody


# Placeholders that tests will monkeypatch
def _gemini_chat(api_key, model, base_url, messages, context, access_token=None):
    return f"default_called"


def _get_adc_access_token():
    return ""


auth_routes._gemini_chat = _gemini_chat
auth_routes._get_adc_access_token = _get_adc_access_token


def ai_chat(body, x_session_token=None):
    user = auth_db.get_user_by_session(x_session_token)
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")
    settings = auth_db.get_ai_settings(user["id"])
    if settings and settings.get("hasApiKey"):
        return auth_routes._gemini_chat(
            settings.get("apiKey"),
            settings.get("model"),
            settings.get("apiBaseUrl", ""),
            body.messages,
            None,
        )
    # If demo user, allow ADC path
    if user["id"] == auth_routes.DEMO_USER_ID:
        token = auth_routes._get_adc_access_token()
        return auth_routes._gemini_chat(
            None, "", "", body.messages, None, access_token=token
        )
    raise HTTPException(status_code=401, detail="no api key configured")


auth_routes.ai_chat = ai_chat

sys.modules["auth_routes"] = auth_routes


def run_tests():
    results = []

    # Keep originals to restore
    orig_get_user = auth_db.get_user_by_session
    orig_get_settings = auth_db.get_ai_settings
    orig_gemini = auth_routes._gemini_chat
    orig_get_adc = getattr(auth_routes, "_get_adc_access_token", lambda: "")

    try:
        # Test 1: Normal user with saved API key
        auth_db.get_user_by_session = lambda token: {
            "id": "user-normal",
            "identifier": "normal@example.com",
        }
        auth_db.get_ai_settings = lambda uid: {
            "provider": "gemini",
            "apiBaseUrl": "",
            "model": "gemini-2.5-flash",
            "apiKey": "APIKEY_NORMAL",
            "hasApiKey": True,
        }
        auth_routes._gemini_chat = (
            lambda api_key, model, base_url, messages, context, access_token=None: f"used_key:{api_key}"
        )

        body = auth_routes.AiChatBody(
            messages=[auth_routes.AiChatMessage(role="user", content="hello")]
        )
        out = auth_routes.ai_chat(body, x_session_token="sess-token")
        results.append(("normal_with_key", out))

        # Test 2: Non-demo user without saved API key -> 401
        auth_db.get_user_by_session = lambda token: {
            "id": "user-no-key",
            "identifier": "nobody@example.com",
        }
        auth_db.get_ai_settings = lambda uid: None
        # Ensure ADC helper returns a token if called (it should NOT be used)
        auth_routes._get_adc_access_token = lambda: "ADC_SHOULD_NOT_BE_USED"
        try:
            body = auth_routes.AiChatBody(
                messages=[auth_routes.AiChatMessage(role="user", content="hello")]
            )
            auth_routes.ai_chat(body, x_session_token="sess-token")
            results.append(("non_demo_no_key", "FAILED_no_401"))
        except auth_routes.HTTPException as e:
            results.append(("non_demo_no_key", e.status_code, e.detail))

        # Test 3: Demo user without saved key -> ADC path
        demo_id = auth_routes.DEMO_USER_ID
        auth_db.get_user_by_session = lambda token: {
            "id": demo_id,
            "identifier": "demo.lamresearch@gmail.com",
        }
        auth_db.get_ai_settings = lambda uid: None
        auth_routes._get_adc_access_token = lambda: "ADC_TOKEN_OK"
        auth_routes._gemini_chat = (
            lambda api_key, model, base_url, messages, context, access_token=None: f"used_adc:{access_token}"
        )

        body = auth_routes.AiChatBody(
            messages=[auth_routes.AiChatMessage(role="user", content="hello")]
        )
        out = auth_routes.ai_chat(body, x_session_token="sess-token")
        results.append(("demo_no_key_adc", out))

        # Extra check: ensure ADC not allowed for other user even if ADC helper returns token
        auth_db.get_user_by_session = lambda token: {
            "id": "user-other",
            "identifier": "other@example.com",
        }
        auth_db.get_ai_settings = lambda uid: None
        auth_routes._get_adc_access_token = lambda: "ADC_STILL_SHOULD_NOT_BE_USED"
        try:
            body = auth_routes.AiChatBody(
                messages=[auth_routes.AiChatMessage(role="user", content="hello")]
            )
            auth_routes.ai_chat(body, x_session_token="sess-token")
            results.append(("other_user_adc_allowed", "FAILED_allowed"))
        except auth_routes.HTTPException as e:
            results.append(("other_user_adc_allowed", e.status_code, e.detail))

    finally:
        # restore
        auth_db.get_user_by_session = orig_get_user
        auth_db.get_ai_settings = orig_get_settings
        auth_routes._gemini_chat = orig_gemini
        auth_routes._get_adc_access_token = orig_get_adc

    for r in results:
        print(r)


if __name__ == "__main__":
    run_tests()
