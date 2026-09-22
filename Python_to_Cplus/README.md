# Python → C++ converter (Gradio)

Turn a Python snippet or a small Python repo into C++ using an LLM, then compile with a command chosen for **this machine**.

Works on macOS, Linux, and Windows as long as Python 3.11+ is installed. A C++ compiler is only required if you click **Compile & run**.

## What you need

1. **Python 3.11 or newer** (`python3 --version` / `py --version`). On macOS, `/usr/bin/python3` can still be 3.8 — use `python3.12` or `python3.11` if needed.
2. An **API key** for at least one provider, **or** [Ollama](https://ollama.com) running locally
3. Optional, for compiling: a C++ toolchain
   - **macOS:** `xcode-select --install` (Apple Clang). Optional: `brew install cmake ninja`
   - **Linux (Debian/Ubuntu):** `sudo apt install -y build-essential cmake ninja-build`
   - **Linux (Fedora):** `sudo dnf install -y gcc-c++ cmake ninja-build`
   - **Windows:** Visual Studio Build Tools, LLVM, or MinGW-w64, plus CMake if you convert a repo

## Setup (all platforms)

Open a terminal in this folder (`week4/Python_to_Cplus`).

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

You can also paste a key in the Gradio UI. The UI key overrides `.env` for that request. Keys typed in the UI are not written to disk.

Ollama needs no cloud key. Start the daemon and pull a code model, for example:

```bash
ollama pull qwen2.5-coder
```

## Run the app

With the virtual environment activated:

```bash
python app.py
```

Then open the URL Gradio prints (usually http://127.0.0.1:7860).

## How to use it

1. **System & compile command** — confirms OS, CPU, and compiler. Edit the compile/run lines if you want different flags.
2. **Snippet** — Python on the left, C++ on the right. Convert, then **Run Python**, **Compile & run C++** (live compiler log), or **Run both & compare** for a timing table. **C++ repeats** runs the binary several times so the first (cold) run does not dominate.
3. **Python repo** — folder path or `.zip`. The model writes `generated/cpp_project`. Build with **Build & run generated C++ project**.

Repo conversion is meant for small projects. Very large trees are truncated so the prompt stays within model context.

## Layout

| File | Role |
| --- | --- |
| `app.py` | Gradio UI and compile/run wiring |
| `compiler.py` | Detect toolchain and pick compile commands |
| `converter.py` | Provider clients and Python → C++ prompts |
| `system_info.py` | OS / CPU / compiler inventory |
| `generated/` | Written C++ (`main.cpp` or a CMake project) |

## Troubleshooting

- **No API key** — set the matching variable in `.env` or paste it in the UI.
- **No compiler** — install one using the hints on the System tab, then click **Re-scan this machine**.
- **Ollama connection error** — confirm `ollama serve` is running and the model name matches `ollama list`.
- **Windows `cl` not found** — open “x64 Native Tools Command Prompt for VS” (or equivalent) before `python app.py`, or use `clang++` / MinGW `g++` instead.
- **Permission / venv issues** — delete `.venv` and recreate it with the commands above.

## 🎬 Demo

See the **Python → C++ Converter** in action:

<p align="center">
  <img src="./assets/python_to_cpp_demo.gif"
       alt="Python to C++ Converter Demo"
       width="100%">
</p>
