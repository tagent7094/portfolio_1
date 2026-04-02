# Digital DNA

Build a personality knowledge graph from founder content and generate authentic social media posts using agentic voting.

## Quick Start

```bash
# Activate environment
conda activate digital-dna

# Install
pip install -e .
python -m spacy download en_core_web_sm

# Configure (default: Ollama)
# Make sure Ollama is running: ollama serve
# Pull a model: ollama pull llama3.1:8b

# Drop founder files into data/founder-data/
cp your-content.md data/founder-data/

# Build knowledge graph
digital-dna ingest

# Generate posts
digital-dna generate topic "AI agents replacing contact centers"
digital-dna generate podcast data/podcasts/episode.txt

# View graph
digital-dna graph show

# Web UI
cd webapp && python server.py
# Open http://localhost:5000
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `digital-dna ingest` | Read founder data, build knowledge graph |
| `digital-dna generate topic <topic>` | Generate post on a viral topic |
| `digital-dna generate podcast <file>` | Generate post from podcast transcript |
| `digital-dna graph show` | Print graph summary |
| `digital-dna graph export` | Export graph as JSON |
| `digital-dna config show` | Show current LLM config |
| `digital-dna config set-llm <provider>` | Switch LLM provider |

## LLM Providers

- **Ollama** (default, local) — `ollama pull llama3.1:8b`
- **LM Studio** (local) — OpenAI-compatible at localhost:1234
- **Anthropic** (API) — requires `ANTHROPIC_API_KEY`
- **OpenAI** (API) — requires `OPENAI_API_KEY`

