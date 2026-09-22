# Image Studio

A Gradio app pattern: custom Blocks UI, chat history, and OpenAI image generation.

The first prompt **creates** an image. Later prompts **edit that same image** (keep the subject, change the background, add details). Stop when you are done, or start over with a new canvas.

Each generate/edit call costs a few cents. Do not loop endlessly.

## Setup

**Python 3.10+ is required** (3.12 recommended). `openai` and Gradio no longer install cleanly on 3.8.

If `python -V` shows 3.8 (typical when conda `base` is active), do **not** use `python -m venv`. Use 3.12 explicitly:

```bash
cd Image_Studio
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If `.venv` was already created with 3.8, delete it first: `rm -rf .venv`, then run the commands above.

Put your OpenAI key in a `.env` file in this folder **or** in the course repo root:

```env
OPENAI_API_KEY=sk-...
```

## Run

```bash
python image_studio.py
```

Open the local URL Gradio prints (usually `http://127.0.0.1:7860`).

You can also run `image_studio.ipynb`. Cursor often does not list a venv that lives in a subfolder.

1. Open the notebook.
2. Click **Select Kernel** (top right) → **Select Another Kernel** → **Python Environments**.
3. If **Image_Studio/.venv** is not listed, choose **Enter interpreter path…** and paste:

   `/Users/ravi1992/projects/generative-ai-projects/Image_Studio/.venv/bin/python`

4. Re-run the import cell.

This workspace also sets that path as the default Python interpreter (`.vscode/settings.json`). Reload the window if the kernel list is stale: Command Palette → **Developer: Reload Window**.

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

## 📜 License

This project is licensed under the MIT License. See the
[LICENSE](../LICENSE) file for details.
