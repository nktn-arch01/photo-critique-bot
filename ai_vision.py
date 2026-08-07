"""マルチプロバイダ向け Vision API アダプタ（モデル差し替えはここと環境変数で行う）。"""

import base64
import os
from pathlib import Path
from typing import Literal

from openai import OpenAI

VisionProvider = Literal["openai", "gemini"]

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"


def image_mime_type(image_path: Path) -> str:
    if image_path.suffix.lower() == ".png":
        return "image/png"
    return "image/jpeg"


def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        key_file = Path.home() / ".openai_api_key"
        if key_file.exists():
            api_key = key_file.read_text(encoding="utf-8").strip()
    if not api_key:
        raise ValueError(
            "OpenAI APIキーが見つかりません。~/.openai_api_key または環境変数 OPENAI_API_KEY を設定してください。"
        )
    return OpenAI(api_key=api_key)


def _read_image_bytes(image_path: Path) -> bytes:
    return image_path.read_bytes()


def complete_with_image_openai(
    image_path: Path,
    prompt: str,
    *,
    model: str = DEFAULT_OPENAI_MODEL,
    max_tokens: int = 800,
    temperature: float = 0.7,
    image_detail: str = "low",
) -> str:
    client = get_openai_client()
    mime = image_mime_type(image_path)
    b64 = base64.b64encode(_read_image_bytes(image_path)).decode("utf-8")
    image_url_data = f"data:{mime};base64,{b64}"

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url_data, "detail": image_detail}},
                ],
            }
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    content = response.choices[0].message.content
    if not content or not content.strip():
        raise ValueError("OpenAI API が空の応答を返しました。")
    return content.strip()


def complete_with_image_gemini(
    image_path: Path,
    prompt: str,
    *,
    model: str | None = None,
    max_tokens: int = 800,
    temperature: float = 0.7,
) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 環境変数が設定されていません。")

    model_name = model or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)

    try:
        import google.generativeai as genai
    except ImportError as e:
        raise ImportError(
            "Gemini 用パッケージ google-generativeai が未インストールです。"
            " pip install google-generativeai を実行してください。"
        ) from e

    genai.configure(api_key=api_key)
    gemini_model = genai.GenerativeModel(model_name)
    mime = image_mime_type(image_path)
    image_part = {"mime_type": mime, "data": _read_image_bytes(image_path)}

    response = gemini_model.generate_content(
        [prompt, image_part],
        generation_config={
            "max_output_tokens": max_tokens,
            "temperature": temperature,
        },
    )

    text = getattr(response, "text", None)
    if text and text.strip():
        return text.strip()

    raise ValueError("Gemini API が空の応答を返しました（安全フィルタ等の可能性があります）。")


def complete_with_image(
    provider: VisionProvider,
    image_path: Path,
    prompt: str,
    *,
    model: str | None = None,
    max_tokens: int = 800,
    temperature: float = 0.7,
) -> str:
    if provider == "openai":
        openai_model = model or DEFAULT_OPENAI_MODEL
        return complete_with_image_openai(
            image_path, prompt, model=openai_model, max_tokens=max_tokens, temperature=temperature
        )
    if provider == "gemini":
        return complete_with_image_gemini(
            image_path, prompt, model=model, max_tokens=max_tokens, temperature=temperature
        )
    raise ValueError(f"未対応の Vision プロバイダ: {provider}")
