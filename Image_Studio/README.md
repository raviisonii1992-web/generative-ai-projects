# Image Studio

A Gradio app pattern: custom Blocks UI, chat history, and OpenAI image generation.

The first prompt **creates** an image. Later prompts **edit that same image** (keep the subject, change the background, add details). Stop when you are done, or start over with a new canvas.

Each generate/edit call costs a few cents. Do not loop endlessly.

## Setup

From this folder:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Put your OpenAI key in a `.env` file in this folder **or** in the course repo root:

```env
OPENAI_API_KEY=sk-...
```

## Run

```bash
python image_studio.py
```

Open the local URL Gradio prints (usually `http://127.0.0.1:7860`).

You can also run `image_studio.ipynb` in Jupyter with the course environment.

## How to use

1. Type a prompt, for example `funky monkey`.
2. Click **Generate / Edit** (or press Enter). Wait 20–40 seconds.
3. Type a change, for example `change the background to a lake and trees where the monkey is sitting`.
4. Click **Generate / Edit** again. The app sends the **last picture** plus your new text to `images.edit`.
5. Type `stop` / `done` / `quit`, or click **Stop editing**, when you are finished.
6. Click **New image** to clear chat and start a fresh generate.

**Generate / Edit** creates or edits. **New image** only resets. It does not draw a picture by itself.

## How it works

- If there is no saved picture, the app calls `openai.images.generate`.
- If there is a saved picture, it calls `openai.images.edit` with that PNG.
- The last PIL image is kept in Gradio `State` (`current_image`) so follow-up prompts modify the same canvas.
- Model: `gpt-image-1-mini` at `1024x1024`.
