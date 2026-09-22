# 🤖 Generative AI Projects

A collection of hands-on **Generative AI and LLM projects** built with Python, OpenAI, Anthropic, Google Gemini, Ollama, Gradio, and Jupyter.

The repository explores practical applications of Large Language Models — from image generation and multi-model conversations to code generation and YouTube content summarization.

> ⭐ If you find these projects useful, consider starring the repository!

---

## 🚀 Projects

| Project                                                                 | Description                                                                                                     | Technologies                      |
| ----------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | --------------------------------- |
| 🎨 **[Image Studio](./Image_Studio)**                                   | Generate an image from a prompt and iteratively edit the same image through natural-language instructions.      | Python, OpenAI, Gradio            |
| 📺 **[YouTube Transcript Summariser](./Youtube-Transcript-summariser)** | Fetch YouTube transcripts and generate structured Markdown summaries using cloud or local LLMs.                 | Python, OpenAI, Ollama, Jupyter   |
| 🧠 **[3-Way LLM Debate](./three-way-llm-debate)**                       | Run turn-based debates between three AI personas using different LLM providers or local Ollama models.          | OpenAI, Anthropic, Gemini, Ollama |
| ⚡ **[CppLift](./Python_to_Cplus)**                                      | Convert Python snippets or small repos to C++ with cloud or local (Ollama) models, compile on this machine, and compare runtimes. App lives in `Python_to_Cplus/`. | Python, C++, Gradio, OpenAI, Anthropic, Gemini, Groq, Ollama |

Each project is self-contained and includes its own README, dependencies, and setup instructions.

---

## 🛠️ Tech Stack

**Languages**

* Python
* C++

**Generative AI / LLMs**

* OpenAI
* Anthropic Claude
* Google Gemini
* xAI Grok
* Groq
* OpenRouter
* Ollama

**Tools & Frameworks**

* Gradio
* Jupyter Notebook
* REST APIs
* Python virtual environments

---

## ⚡ Quick Start

Clone the repository:

```bash
git clone https://github.com/raviisonii1992-web/generative-ai-projects.git
cd generative-ai-projects
```

Choose the project you want to run:

```bash
cd <project-folder>
```

Create a virtual environment:

```bash
python3 -m venv .venv
```

Activate it.

### macOS / Linux

```bash
source .venv/bin/activate
```

### Windows

```bash
.venv\Scripts\activate
```

Install the dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## 🔑 API Keys

Some projects use external LLM providers.

Create a `.env` file inside the project folder or repository root:

```env
OPENAI_API_KEY=your_key
ANTHROPIC_API_KEY=your_key
GOOGLE_API_KEY=your_key
GROK_API_KEY=your_key
GROQ_API_KEY=your_key
OPENROUTER_API_KEY=your_key
ARTIFICIAL_ANALYSIS_API_KEY=your_key
```

**Never commit your `.env` file or API keys to GitHub.**

The repository `.gitignore` should keep these files out of version control.

---

## 🖥️ Running the Projects

### 🎨 Image Studio

```bash
cd Image_Studio
python image_studio.py
```

Open the generated Gradio URL in your browser.

---

### ⚡ CppLift

The product name is **CppLift**. The folder is still `Python_to_Cplus`.

```bash
cd Python_to_Cplus
python app.py
```

Open http://127.0.0.1:7860.

Use **Snippet** or **Repo** with the shared Provider / Model bar. Switch **Cloud** (API providers + Refresh catalog) or **Local** (Ollama download on this machine). **System** lists the compiler; **Scores** and **Suggest** help pick a model. Convert, compile, and compare Python vs C++ runtimes. Generated repos land in `Python_to_Cplus/generated/cpp_project` — run with `./app` after a successful build.

Step-by-step UI instructions (Cloud/Local, convert, compile repair, Scores, Suggest) are in [Python_to_Cplus/README.md](./Python_to_Cplus/README.md#user-instructions).

---

### 📺 YouTube Transcript Summariser

Open the project's Jupyter notebook in:

* Jupyter
* VS Code
* Cursor

Then run the cells from the top.

---

### 🧠 3-Way LLM Debate

Open the project's notebook and configure the LLM providers you want to use.

The project supports cloud providers as well as local Ollama models.

---

## 🦙 Running with Ollama

Some projects can run using local models through Ollama.

After installing Ollama:

```bash
ollama serve
```

Pull a model, for example:

```bash
ollama pull llama3.2
```

For coding-oriented tasks:

```bash
ollama pull qwen2.5-coder
```

This allows supported projects to run locally without sending prompts to a cloud LLM provider.

---

## 📁 Repository Structure

```text
generative-ai-projects/
│
├── Image_Studio/
│
├── Youtube-Transcript-summariser/
│
├── three-way-llm-debate/
│
├── Python_to_Cplus/          # CppLift (Python → C++ app)
│
├── .gitignore
├── LICENSE
└── README.md
```

---

## 🗺️ Future Projects

This repository will continue to grow with experiments involving:

* 🤖 AI agents
* 🔎 Retrieval-Augmented Generation (RAG)
* 🧠 Multi-agent systems
* 📚 Document Q&A
* 🖼️ Multimodal AI
* 🛠️ LLM-powered developer tools
* 🏠 Local LLM applications

---

## 🤝 Contributing

Contributions, ideas, and improvements are welcome.

To contribute:

1. Fork the repository.
2. Create a new branch.

```bash
git checkout -b feature/my-feature
```

3. Make your changes.
4. Commit your changes.

```bash
git commit -m "Add new feature"
```

5. Push your branch.

```bash
git push origin feature/my-feature
```

6. Open a **Pull Request**.

---

## ⭐ Support

If you find these projects useful:

* ⭐ Star the repository
* 🍴 Fork it and experiment
* 🐛 Open an issue if you find a problem
* 💡 Suggest new Generative AI project ideas
* 🤝 Submit a pull request

---

## 📜 License

This project is licensed under the **MIT License**.

See the [LICENSE](./LICENSE) file for details.

---

## 👨‍💻 Author

**Ravi Soni**

Building and experimenting with Generative AI, LLMs, Python, and AI-powered applications.
