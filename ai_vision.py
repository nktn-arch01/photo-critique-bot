"""マルチプロバイダ向け Vision API アダプタ（モデル差し替えはここと環境変数で行う）。"""

import base64
import os
from pathlib import Path
from typing import Literal

from openai import OpenAI

VisionProvider = Literal["openai", "gemini"]

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"


def sniff_image_mime(data: bytes) -> str:
    """ファイル内容から MIME を判定（LINE 画像は .jpg 名でも PNG のことがある）。"""
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 2 and data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def image_mime_type(image_path: Path) -> str:
    data = _read_image_bytes(image_path)
    return sniff_image_mime(data)


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


def _extract_gemini_text(response) -> str:
    """response.text が安全ブロック等で例外になる場合のフォールバック。"""
    try:
        text = response.text
        if text and text.strip():
            return text.strip()
    except ValueError:
        pass

    candidates = getattr(response, "candidates", None) or []
    for cand in candidates:
        content = getattr(cand, "content", None)
        if not content:
            continue
        for part in getattr(content, "parts", []) or []:
            part_text = getattr(part, "text", None)
            if part_text and part_text.strip():
                return part_text.strip()

    feedback = getattr(response, "prompt_feedback", None)
    finish = None
    if candidates:
        finish = getattr(candidates[0], "finish_reason", None)
    raise ValueError(
        f"Gemini API が空またはブロックされました (finish_reason={finish}, prompt_feedback={feedback})"
    )


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
        from google.generativeai.types import HarmBlockThreshold, HarmCategory
    except ImportError as e:
        raise ImportError(
            "Gemini 用パッケージ google-generativeai が未インストールです。"
            " pip install google-generativeai を実行してください。"
        ) from e

    safety_settings = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    }

    genai.configure(api_key=api_key)
    gemini_model = genai.GenerativeModel(model_name)
    raw = _read_image_bytes(image_path)
    mime = sniff_image_mime(raw)
    image_part = {"mime_type": mime, "data": raw}

    response = gemini_model.generate_content(
        [prompt, image_part],
        generation_config={
            "max_output_tokens": max_tokens,
            "temperature": temperature,
        },
        safety_settings=safety_settings,
    )

    return _extract_gemini_text(response)


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
