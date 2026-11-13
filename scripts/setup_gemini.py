"""Prepare private local Gemini/Bifrost settings. Does not print keys or start services."""

import json
import os
import secrets
import shutil
from pathlib import Path

from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[1]
MODELS = ["gemini-3.5-flash-lite"]


def gateway_config():
    return {
        "$schema": "https://www.getbifrost.ai/schema", "source_of_truth": "config.json",
        "setup_token": "env.BIFROST_SETUP_TOKEN",
        "auth_config": {"admin_username": "leancode", "admin_password": "env.LEANCODE_BIFROST_ADMIN_PASSWORD", "is_enabled": True},
        "client": {"enable_logging": False, "disable_content_logging": True, "enforce_auth_on_inference": True},
        "governance": {"virtual_keys": [{
            "id": "leancode-local-gemini", "name": "leancode-local-gemini",
            "value": "env.LEANCODE_BIFROST_VIRTUAL_KEY", "is_active": True,
            "disable_content_logging": True, "allow_all_providers": False,
            "provider_configs": [{"provider": "gemini", "allowed_models": MODELS, "key_ids": ["*"]}],
        }]},
        "providers": {"gemini": {
            "keys": [{"name": "leancode-gemini", "value": "env.GEMINI_API_KEY", "models": MODELS, "weight": 1}],
            "network_config": {"max_retries": 0, "default_request_timeout_in_seconds": 45},
            "concurrency_and_buffer_size": {"concurrency": 1, "buffer_size": 10},
            "send_back_raw_request": False, "send_back_raw_response": False, "store_raw_request_response": False,
        }},
    }


def routes():
    # Standard text rates verified 2026-11-13: https://ai.google.dev/gemini-api/docs/pricing
    return [
        {"name": "Gemini 3.5 Flash-Lite", "model": f"gemini/{MODELS[0]}", "local": False,
         "primary": True, "tier": "small", "bounded_output": True, "input_rate": 300000, "output_rate": 2500000},
    ]


def private_write(path, text):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(text)
    path.chmod(0o600)


def main():
    env = ROOT / ".env"
    values = dotenv_values(env)
    key = values.get("GEMINI_API_KEY") or values.get("GOOGLE_API_KEY")
    if not key or "\n" in key or "\r" in key:
        raise SystemExit("Add a valid single-line Gemini key to your private .env first")
    data = ROOT / ".leancode" / "bifrost"
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    config_path = data / "config.json"
    if config_path.exists():
        current = json.loads(config_path.read_text())
        if current.get("providers", {}).keys() != {"gemini"}:
            raise SystemExit("Existing gateway configuration has other providers; preserve it and configure manually")
    password_file = data / "admin-password"
    password = password_file.read_text().strip() if password_file.exists() else secrets.token_urlsafe(32)
    virtual_key_file = data / "virtual-key"
    virtual_key = virtual_key_file.read_text().strip() if virtual_key_file.exists() else "sk-bf-" + secrets.token_urlsafe(32)
    private_write(password_file, password + "\n")
    private_write(virtual_key_file, virtual_key + "\n")
    private_write(data / "gateway.env", f"GEMINI_API_KEY={key}\nLEANCODE_BIFROST_ADMIN_PASSWORD={password}\nLEANCODE_BIFROST_VIRTUAL_KEY={virtual_key}\nBIFROST_SETUP_TOKEN={secrets.token_urlsafe(32)}\n")
    private_write(config_path, json.dumps(gateway_config(), indent=2) + "\n")
    private_write(data / "image-version", "maximhq/bifrost:v2.4.0\n")
    private_write(data / "README", "Local gateway admin username: leancode\nPassword is in admin-password. Never commit this directory.\n")
    set_key(str(env), "BIFROST_KEY", virtual_key)
    set_key(str(env), "BIFROST_URL", "http://127.0.0.1:8080/openai")
    set_key(str(env), "LEANCODE_ROUTES", json.dumps(routes()))
    set_key(str(env), "LEANCODE_GATEWAY_SINGLE_ATTEMPT", "true", quote_mode="never")
    # Only this synthetic fixture is classified public; preserve the user's repository policies.
    demo = ROOT / ".leancode" / "cloud-demo"
    if not demo.exists():
        shutil.copytree(ROOT / "benchmarks" / "tasks" / "boundary", demo)
    repositories = json.loads(values.get("LEANCODE_REPOSITORIES") or "{}")
    repositories.setdefault("cloud-demo", {"path": str(demo), "confidential": False})
    set_key(str(env), "LEANCODE_REPOSITORIES", json.dumps(repositories))
    env.chmod(0o600)
    print("Prepared private Gemini routes, authenticated gateway configuration, and a public synthetic demo.")
    print("No credentials were printed. Existing repository privacy settings were preserved.")


if __name__ == "__main__":
    main()
