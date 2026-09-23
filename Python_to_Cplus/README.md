# CppLift

**CppLift** turns a Python snippet or a small Python repo into C++ with an LLM, then compiles and runs it on **this machine**.

The Gradio app lives in `Python_to_Cplus/`. Works on macOS, Linux, and Windows with Python 3.11+. A C++ compiler is only required if you click **Compile & run**.

The window is a studio that stays inside the browser. The left rail is the section list. The center is the work area. The bottom bar is the model and the convert action. Zooming the browser rescales that layout; panels scroll inside themselves when the window is short.

## What you need

1. **Python 3.11 or newer** (`python3 --version` / `py --version`). On macOS, `/usr/bin/python3` can still be 3.8 — use `python3.12` or `python3.11` if needed.
2. An **API key** for at least one cloud provider, **or** [Ollama](https://ollama.com) for local models
3. Optional, for compiling: a C++ toolchain
   - **macOS:** `xcode-select --install` (Apple Clang). Optional: `brew install cmake ninja`
   - **Linux (Debian/Ubuntu):** `sudo apt install -y build-essential cmake ninja-build`
   - **Linux (Fedora):** `sudo dnf install -y gcc-c++ cmake ninja-build`
   - **Windows:** Visual Studio Build Tools, LLVM, or MinGW-w64, plus CMake if you convert a repo

## Setup (all platforms)

Open a terminal in this folder (`Python_to_Cplus`).

### macOS / Linux

```bash
python3.12 -m venv .venv
# If 3.12 is missing: python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Windows (Command Prompt)

```bat
py -3 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Windows (PowerShell)

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks the activate script, run once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## API keys

Copy the example env file and fill in **only the providers you use**:

```bash
cp .env.example .env
```

On Windows (Command Prompt): `copy .env.example .env`

Supported providers: **OpenAI**, **Anthropic**, **Google Gemini**, **xAI Grok**, **Groq**, **OpenRouter**, and **Ollama (local)**.

You can also paste a key in the UI. The UI key overrides `.env` for that request and is not written to disk.

For the **Scores** tab, set `ARTIFICIAL_ANALYSIS_API_KEY` (from [Artificial Analysis](https://artificialanalysis.ai)) or paste it there. That key is only used when you click **Load leaderboard**.

Ollama needs no cloud key.

## Run the app

With the virtual environment activated:

```bash
python app.py
```

Then open the URL Gradio prints (usually http://127.0.0.1:7860).

## User instructions

Open the URL Gradio prints. The app uses the full browser window.

| Area | What it is |
| --- | --- |
| Left rail | **Snippet**, **Repo**, **System**, **Scores**, **Suggest**. **Appearance** (Light / Dark) is under the list. |
| Center | The page for the selected section. On **Snippet**, Python is above or beside the generated C++, depending on window width. Output and timing sit under the editors. |
| Bottom bar | Shown only on **Snippet** and **Repo**. **Cloud / Local**, **Provider**, **Model**, **API key**, the token line, and the action buttons (**Convert to C++**, **Run Python**, **Compile & run**, **Compare both**, **Stop**, **C++ repeats**). On **Repo** the actions are **Convert repo to C++**, **Build & run**, and **Stop run**. |

**Provider**, **Model**, and **API key** stay in sync when you move between **Snippet** and **Repo**. **System**, **Scores**, and **Suggest** hide the bottom bar.

If you zoom in and the window is tight, the rail stays a vertical list, the editors stack, and the action buttons wrap. Scroll inside the center or the bottom bar to reach anything that does not fit.

### 1. Pick a model (Snippet or Repo)

1. Stay on **Snippet** or **Repo** so the bottom bar is visible.
2. Choose **Cloud** or **Local** at the top of that bar.

**Cloud**

1. Set **Provider** (OpenAI, Anthropic, Google Gemini, xAI Grok, Groq, or OpenRouter).
2. Set **Model**. If the list looks stale, click **Refresh catalog** (does not run at startup). Retired ids are dropped; the log says what is still working today.
3. Leave **API key** empty if the matching variable is already in `.env`. Paste a key only to override for this session. UI keys are not saved to disk.

**Local**

1. Click **Local**. CppLift probes Ollama, shows this machine’s RAM, and lists models already on disk.
2. Pick a suggested model (or an installed one).
3. Click **Download & use**. Watch the progress panel. If you need to cancel, click **Stop download & clean** (that also deletes the incomplete pull).
4. When it is ready, **Provider** is **Ollama (local)** and Convert needs no cloud key. If Ollama is missing, follow the install hint in the panel, then run `ollama serve`.

The line under the dropdowns is the **token bar**: context-window size for the selected model. After a conversion it also shows prompt/completion tokens, latency, and estimated $ (local Ollama is $0).

### 2. Convert a snippet

1. Open **Snippet**.
2. Paste or edit Python on the left (a sample is already there).
3. Click **Convert to C++**. Status shows **Converting…**, then **Done** with the token/cost line. Generated C++ appears on the right.
4. Optional:
   - **Run Python** — execute the left pane.
   - **Compile & run** — compile `generated/main.cpp` with the **System** compile command, then run it. **C++ repeats** (1–5) times the C++ binary for a more stable wall-clock average.
   - **Compare both** — run Python and C++, then show timing plus last-convert tokens / latency / $.
   - **Stop** — cancel convert, Python, or C++ that is still running so you can edit and try again.

If compile fails, CppLift sends the compiler log back to the same model (up to 4 repair passes), writes a successful fix into `generated/repair_memory.json`, and retries. Later compiles can reuse that memory.

### 3. Convert a small Python repo

1. Open **Repo**.
2. Enter a local folder path, or upload a `.zip`.
3. Click **Convert repo to C++**. Output is `generated/cpp_project` (`CMakeLists.txt` + `src/`). Very large trees are truncated so the prompt fits the model context.
4. Click **Build & run** to configure/build (CMake when available, otherwise a direct compiler line) and run the binary. **Stop run** cancels that job.

From a terminal, after a successful build:

```bash
cd generated/cpp_project
./app
```

Rebuild after you edit the C++:

```bash
clang++ -std=c++17 -O3 -o app src/main.cpp
./app
```

On Windows the binary is `app.exe`. With CMake: `cmake -S . -B build && cmake --build build`, then run `build/app` (or `build/Release/app.exe` on MSVC).

Interactive programs (games, prompts) work best from this terminal, not from the Gradio log box.

### 4. Check the toolchain (System)

1. Open **System**.
2. Read OS, CPU, SIMD, and detected compilers.
3. Edit **Snippet compile command** and **Snippet run command** if you want different flags (sanitizers, another compiler).
4. After installing a toolchain, click **Re-scan this machine**.

### 5. Compare models (Scores)

1. Open **Scores**.
2. Optionally paste an Artificial Analysis `x-api-key`, or set `ARTIFICIAL_ANALYSIS_API_KEY` in `.env`.
3. Click **Load leaderboard**. Nothing is downloaded until you do.
4. Use the table (intelligence, coding, speed, price) to decide which convert model to pick back on **Snippet** / **Repo**.

### 6. Get a recommendation (Suggest)

1. Open **Suggest**.
2. Choose a category: Coding / Python → C++, General intelligence, Math / reasoning, Speed, Low latency, Lowest cost, or Local (Ollama).
3. Click **Get suggestions**. If you already loaded Scores, ranks come from Artificial Analysis; otherwise CppLift uses built-in defaults.
4. Switch back to **Snippet** or **Repo** and select that provider/model.

### Typical first run

1. `python app.py` → open http://127.0.0.1:7860
2. **Snippet** → **Cloud** → Provider + Model (or **Local** → **Download & use**)
3. **Convert to C++** → wait for **Done**
4. **Compare both**
5. Or **Repo** → folder or zip → **Convert repo to C++** → **Build & run** / `./app`

## Layout

| File | Role |
| --- | --- |
| `app.py` | Gradio studio UI (left rail, work area, bottom model bar, convert, compile) |
| `compiler.py` | Detect toolchain and pick compile commands |
| `converter.py` | Provider clients, Python → C++ prompts, usage stats |
| `model_catalog.py` | Live model lists, Ollama probe/pull, Scores / Suggest |
| `research.py` | Token/cost line and compile-error repair memory |
| `runner.py` | Stream subprocess output and **Stop** |
| `generated/` | Written C++ (`main.cpp` or a CMake `cpp_project`) |

## Troubleshooting

- **No API key** — set the matching variable in `.env` or paste it in the UI on Snippet/Repo.
- **No compiler** — install one using the hints on **System**, then **Re-scan this machine**.
- **Ollama connection error** — on **Snippet** or **Repo**, click **Local** in the bottom bar. If Ollama is not installed, follow the download hint. If it is installed, run `ollama serve`, pick a suggested model, then **Download & use**.
- **Windows `cl` not found** — open “x64 Native Tools Command Prompt for VS” (or equivalent) before `python app.py`, or use `clang++` / MinGW `g++` instead.
- **Permission / venv issues** — delete `.venv` and recreate it with the commands above.

## 🎬 Demo

See **CppLift** in action:

<p align="center">
  <img src="./assets/python_to_cpp_demo.gif"
       alt="CppLift demo"
       width="100%">
</p>

## 📜 License

This project is licensed under the MIT License. See the
[LICENSE](../LICENSE) file for details.
