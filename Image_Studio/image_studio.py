#!/usr/bin/env python3
"""Image Studio: generate an image, then keep editing it from chat prompts."""

from __future__ import annotations

import base64
import os
from io import BytesIO
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image

IMAGE_MODEL = "gpt-image-1-mini"
IMAGE_SIZE = "1024x1024"
STOP_PHRASES = {
    "stop",
    "done",
    "quit",
    "exit",
    "finish",
    "no more",
    "that's enough",
    "thats enough",
    "stop editing",
}


def load_api_key() -> None:
    load_dotenv(override=True)
    for parent in Path(__file__).resolve().parents:
        env_path = parent / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=True)
            break


load_api_key()
openai = OpenAI()


def decode_image(b64_json: str) -> Image.Image:
    return Image.open(BytesIO(base64.b64decode(b64_json)))


def image_as_png_file(image: Image.Image) -> BytesIO:
    buf = BytesIO()
    image.convert("RGBA").save(buf, format="PNG")
    buf.seek(0)
    buf.name = "current.png"
    return buf


def generate_image(prompt: str) -> Image.Image:
    response = openai.images.generate(
        model=IMAGE_MODEL,
        prompt=prompt,
        size=IMAGE_SIZE,
        n=1,
    )
    return decode_image(response.data[0].b64_json)


def edit_image(image: Image.Image, prompt: str) -> Image.Image:
    response = openai.images.edit(
        model=IMAGE_MODEL,
        image=image_as_png_file(image),
        prompt=(
            "Edit this existing image. Keep the same main subject and overall look "
            f"unless the user asks to change them. User request: {prompt}"
        ),
        size=IMAGE_SIZE,
        n=1,
    )
    return decode_image(response.data[0].b64_json)


def wants_to_stop(text: str) -> bool:
    return text.strip().lower() in STOP_PHRASES


def put_message_in_chatbot(message, history):
    history = history or []
    if not message or not str(message).strip():
        return (
            message or "",
            history,
            "Type a prompt, then click Generate / Edit (or press Enter).",
        )
    return (
        "",
        history + [{"role": "user", "content": str(message).strip()}],
        "Working... image generation can take 20–40 seconds.",
    )


def generate_or_edit(history, current_image, stopped):
    history = history or []
    if not history:
        return (
            history,
            current_image,
            current_image,
            stopped,
            "Type a prompt, then click Generate / Edit.",
        )

    user_text = history[-1]["content"]

    if stopped:
        history = history + [
            {
                "role": "assistant",
                "content": "Editing is stopped. Click New image to start a fresh picture.",
            }
        ]
        return (
            history,
            current_image,
            current_image,
            True,
            "Stopped. Click New image to start again.",
        )

    if wants_to_stop(user_text):
        history = history + [
            {
                "role": "assistant",
                "content": "Stopped. The last image is kept. Click New image when you want a new one.",
            }
        ]
        return history, current_image, current_image, True, "Stopped. Last image kept."

    try:
        if current_image is None:
            image = generate_image(user_text)
            reply = (
                "Created the image. Describe a change, then click Generate / Edit again. Or type stop."
            )
            status = "New image generated. Keep chatting to edit it."
        else:
            image = edit_image(current_image, user_text)
            reply = "Updated the image from your last instruction. Keep going, or type stop."
            status = "Image edited from your last message."
    except Exception as e:
        history = history + [{"role": "assistant", "content": f"Image request failed: {e}"}]
        return history, current_image, current_image, stopped, f"Error: {e}"

    history = history + [{"role": "assistant", "content": reply}]
    return history, image, image, False, status


def stop_editing(history, current_image):
    history = (history or []) + [
        {
            "role": "assistant",
            "content": "Stopped. Click New image to start a fresh picture.",
        }
    ]
    return history, current_image, True, "Stopped. Last image kept."


def new_image():
    return [], None, None, False, "Ready. Describe the first image, then click Generate / Edit."


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Image Studio") as ui:
        current_image = gr.State(None)
        stopped = gr.State(False)

        gr.Markdown(
            "## Image Studio\n"
            "Type a prompt and click **Generate / Edit** (or press Enter). "
            "The first prompt creates an image. Later prompts edit **that** image. "
            "Example: `funky monkey` then `change the background to a lake and trees where the monkey is sitting`."
        )

        with gr.Row():
            chatbot = gr.Chatbot(height=500, type="messages", label="Instructions")
            image_output = gr.Image(
                height=500, interactive=False, label="Current image", type="pil"
            )

        status = gr.Textbox(
            value="Ready. Describe the first image, then click Generate / Edit.",
            label="Status",
            interactive=False,
        )

        with gr.Row():
            message = gr.Textbox(
                label="Prompt",
                placeholder="funky monkey",
                scale=4,
                submit_btn=False,
            )
            send_btn = gr.Button("Generate / Edit", variant="primary", scale=1)

        with gr.Row():
            stop_btn = gr.Button("Stop editing")
            reset_btn = gr.Button("New image")

        send_btn.click(
            put_message_in_chatbot,
            inputs=[message, chatbot],
            outputs=[message, chatbot, status],
        ).then(
            generate_or_edit,
            inputs=[chatbot, current_image, stopped],
            outputs=[chatbot, image_output, current_image, stopped, status],
        )

        message.submit(
            put_message_in_chatbot,
            inputs=[message, chatbot],
            outputs=[message, chatbot, status],
        ).then(
            generate_or_edit,
            inputs=[chatbot, current_image, stopped],
            outputs=[chatbot, image_output, current_image, stopped, status],
        )

        stop_btn.click(
            stop_editing,
            inputs=[chatbot, current_image],
            outputs=[chatbot, current_image, stopped, status],
        )

        reset_btn.click(
            new_image,
            outputs=[chatbot, image_output, current_image, stopped, status],
        )

    return ui


def main() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit(
            "OPENAI_API_KEY is not set. Add it to a .env file in this folder or the course root."
        )
    print(f"OpenAI API Key exists and begins {os.environ['OPENAI_API_KEY'][:8]}")
    ui = build_ui()
    ui.queue()
    ui.launch()


if __name__ == "__main__":
    main()
