import importlib.util
import sys
from pathlib import Path

proj_root = Path(__file__).resolve().parent.parent
pkg_dir = proj_root / "researcher-kb-pipeline"
auth_db_path = pkg_dir / "auth_db.py"
auth_routes_path = pkg_dir / "auth_routes.py"

# Load real auth_db module
spec_db = importlib.util.spec_from_file_location("auth_db", str(auth_db_path))
auth_db = importlib.util.module_from_spec(spec_db)
sys.modules["auth_db"] = auth_db
spec_db.loader.exec_module(auth_db)

# Load real auth_routes module (it will import auth_db from sys.modules)
spec_ar = importlib.util.spec_from_file_location("auth_routes", str(auth_routes_path))
auth_routes = importlib.util.module_from_spec(spec_ar)
sys.modules["auth_routes"] = auth_routes
spec_ar.loader.exec_module(auth_routes)


def run_tests():
    results = []

    # Keep originals to restore
    orig_get_user = getattr(auth_db, "get_user_by_session", None)
    orig_get_settings = getattr(auth_db, "get_ai_settings", None)
    orig_gemini = getattr(auth_routes, "_gemini_chat", None)
    orig_get_adc = getattr(auth_routes, "_get_adc_access_token", None)

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
        if hasattr(auth_routes, "_get_adc_access_token"):
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
        if hasattr(auth_routes, "_get_adc_access_token"):
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
        if hasattr(auth_routes, "_get_adc_access_token"):
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
        if orig_get_user is not None:
            auth_db.get_user_by_session = orig_get_user
        if orig_get_settings is not None:
            auth_db.get_ai_settings = orig_get_settings
        if orig_gemini is not None:
            auth_routes._gemini_chat = orig_gemini
        if orig_get_adc is not None:
            auth_routes._get_adc_access_token = orig_get_adc

    for r in results:
        print(r)


if __name__ == "__main__":
    run_tests()
