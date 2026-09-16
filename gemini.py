"""
Minimal Gemini client over plain HTTPS/REST.

The official google-generativeai SDK pulls in grpc, whose native cygrpc DLL
is blocked by this machine's Windows Application Control policy. The REST
API (generativelanguage.googleapis.com) does the same job over plain HTTP,
so we call it directly with `requests` instead.
"""

import json
import os

import requests

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def generate_json(prompt: str, schema: dict, model: str = "gemini-3.5-flash-lite", timeout: int = 30) -> dict:
    """Call Gemini with a JSON response schema and return the parsed dict."""
    api_key = os.environ["GEMINI_API_KEY"]
    resp = requests.post(
        API_URL.format(model=model),
        params={"key": api_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    test_schema = {
        "type": "object",
        "properties": {"capital": {"type": "string"}, "population_estimate": {"type": "string"}},
        "required": ["capital", "population_estimate"],
    }
    print(generate_json("What is the capital of France? Give a rough population estimate too.", test_schema))
