# Generative AI projects

Hands-on Python projects that use LLMs and AI APIs: image generate/edit, YouTube transcript summaries, a three-persona debate, and Python → C++ conversion.

Each folder is a standalone project with its own README, dependencies, and setup.

## Projects

| Project | What it does | How to run |
| --- | --- | --- |
| [Image Studio](Image_Studio/) | Gradio app: first prompt **creates** an image, later prompts **edit the same picture** (OpenAI `gpt-image-1-mini`) | `python image_studio.py` or the notebook |
| [YouTube transcript summariser](Youtube-Transcript-summariser/) | Fetch a transcript and stream a structured Markdown summary (OpenAI or local Ollama). Same notebook has `explain()` for code/questions | Jupyter notebook |
| [3-way LLM debate](three-way-llm-debate/) | Turn-taking debate among three personas — paid APIs (OpenAI, Anthropic, Gemini) or three local Ollama “users” | Jupyter notebook |
| [Python → C++](Python_to_Cplus/) | Gradio app: convert a Python snippet or small repo to C++ with an LLM, compile for this machine, run both, and compare timings | `python app.py` |

## Quick start

Pick one folder, then follow that project’s README. Pattern is the same:

```bash
cd <project-folder>
python3.12 -m venv .venv    # Python 3.10+; Python 3.11+ for Python_to_Cplus
source .venv/bin/activate   # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Create a `.env` in that folder (or this repo root). **Do not commit `.env` or API keys.**

```env
OPENAI_API_KEY=your_key
# 3-way debate / Python → C++ (paid providers you use):
ANTHROPIC_API_KEY=your_key
GOOGLE_API_KEY=your_key
```

Then:

- **Image Studio** — `python image_studio.py` and open the Gradio URL
- **Python → C++** — `python app.py` and open the Gradio URL (optional C++ compiler for Compile & run)
- **Summariser / debate** — open the `.ipynb` in Jupyter, VS Code, or Cursor and run cells from the top

Ollama is optional: install it, run `ollama serve`, and pull a model (`llama3.2` or `qwen2.5-coder` for conversion).

## Repo layout

```
generative-ai-projects/
├── Image_Studio/
├── Youtube-Transcript-summariser/
├── three-way-llm-debate/
└── Python_to_Cplus/
```

## Author

Ravi Soni
