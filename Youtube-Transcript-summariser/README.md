# YouTube transcript summariser

`Youtube-transcript-summariser.ipynb` fetches a YouTube transcript and streams a structured summary in Markdown. You can use **OpenAI** (cloud) or **Ollama** (local). The same notebook also includes `explain()` for technical questions or code snippets.

## 1. Create a virtual environment

From this folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

## 2. Install requirements

```bash
pip install -r requirements.txt
```

That installs the OpenAI SDK, `python-dotenv`, `requests`, `youtube-transcript-api`, and Jupyter.

## 3. Create an OpenAI API key

1. Sign in at [https://platform.openai.com](https://platform.openai.com).
2. Open **API keys** and create a new secret key.
3. Copy the key (it starts with `sk-`). You will only see it once.

Add billing / usage limits in the OpenAI dashboard if you have not already.

## 4. Put the key in a `.env` file

In this folder (or the project root), create a file named `.env`:

```
OPENAI_API_KEY=sk-your-key-here
```

Do not commit `.env`. The notebook loads this file with `load_dotenv()` via `load_openai_api_key()`.

## 5. Optional: local Ollama

If you want summaries without calling OpenAI:

1. Install [Ollama](https://ollama.com) and start it.
2. Pull a model:

   ```bash
   ollama pull llama3.2
   ```

The notebook talks to Ollama at `http://localhost:11434`.

## 6. Run the notebook

```bash
jupyter notebook Youtube-transcript-summariser.ipynb
```

Or open the file in VS Code / Cursor and run the cells in order (imports, defaults, helper functions, then usage).

### Summarize a video

Set `VIDEO` to a video id or a full URL, then call `summarize_youtube`:

```python
VIDEO = "NvgMnsaKmZU"
# or VIDEO = "https://www.youtube.com/watch?v=NvgMnsaKmZU"

summarize_youtube(VIDEO, provider="openai")   # uses gpt-4o-mini by default
summarize_youtube(VIDEO, provider="ollama")   # uses llama3.2 by default
```

Optional arguments:

- `model=` — any model name your provider supports
- `languages=` — transcript languages, default `["en"]`
- `system_prompt=` — custom summariser instructions

The video must have a generated transcript in one of those languages.

### Explain code (same notebook)

```python
explain(QUESTION, provider="openai")
explain(QUESTION, provider="ollama")
```

Paste any question or snippet into `QUESTION` in the usage cell.

### Custom prompts

`ask_llm(messages, provider=..., model=...)` is the shared streaming helper if you want your own system/user messages.


## 📜 License

This project is licensed under the MIT License. See the
[LICENSE](../LICENSE) file for details.
