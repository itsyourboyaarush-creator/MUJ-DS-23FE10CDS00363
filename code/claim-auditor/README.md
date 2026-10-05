tests/test_pipeline.py    offline tests (fake client, no API key needed)
# Claim Auditor

Claim Auditor extracts checkable claims from a document and evaluates how well the document supports each one. It produces a Markdown report and machine-readable JSON, including a deterministic evidence score.

The audit is grounded in the supplied text. It does not verify claims against external sources.

## Features

- Extracts and deduplicates empirical, causal, comparative, numeric, and predictive claims.
- Audits claims in configurable batches to reduce API requests while retaining individual results.
- Verifies evidence quotes against the source text; unsupported quotes are discarded and can downgrade the verdict.
- Scores results in code: supported (100), partially supported (60), overstated (30), unsupported (0).
- Writes Markdown and JSON reports; caches identical LLM requests locally.
- Supports Anthropic and Google Gemini models through their APIs.

## Quick Start

Requires Python 3.10 or newer and an API key for the provider you choose.

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
Copy-Item .env.example .env
```

### macOS or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and add the key for your selected provider. The example file is configured for Gemini:

```dotenv
CLAIM_AUDITOR_PROVIDER=gemini
CLAIM_AUDITOR_MODEL=gemini-3-flash-preview
GEMINI_API_KEY=your-gemini-api-key
```

To use Anthropic instead, set the provider and model and add an Anthropic key:

```dotenv
CLAIM_AUDITOR_PROVIDER=anthropic
CLAIM_AUDITOR_MODEL=claude-sonnet-4-5
ANTHROPIC_API_KEY=your-anthropic-api-key
```

Then run an audit:

```bash
python -m claim_auditor.cli samples/coffee_blog.txt
```

The command writes `reports/coffee_blog.md` and `reports/coffee_blog.json`. The `.env`, cache, reports, and virtual environment are excluded by `.gitignore`; never commit API keys.

## Web Interface

Install the dependencies, then start the local web app:

```bash
python -m pip install -r requirements.txt
python -m uvicorn claim_auditor.web:app --reload
```

Open `http://127.0.0.1:8000`, choose a sample or paste text, and run an audit. The web app uses the same configuration, API key, cache, and audit pipeline as the CLI. Reports can be downloaded as Markdown or JSON.

## Usage

```bash
python -m claim_auditor.cli path/to/document.txt
python -m claim_auditor.cli path/to/document.txt --out results/
python -m claim_auditor.cli path/to/document.txt --no-cache -v
cat path/to/document.txt | python -m claim_auditor.cli
```

Options:

- `--config PATH`: use an alternate YAML configuration file.
- `--prompts PATH`: use an alternate prompt file.
- `--out PATH`: choose the report output directory.
- `--no-cache`: bypass the local response cache.
- `-v`, `--verbose`: show informational logs.

The CLI also accepts `CLAIM_AUDITOR_PROVIDER` and `CLAIM_AUDITOR_MODEL` environment overrides. Existing shell environment variables take precedence over values in `.env`.

## Request Count and Configuration

By default, claims are audited in batches of three. For $N$ extracted claims, a normal run uses approximately $1 + \lceil N/3 \rceil + 1$ API calls: one extraction request, one per audit batch, and one summary request. For nine claims, that is five calls instead of eleven with one request per claim. Retries, malformed-response repair, cache hits, and empty extraction results can change the actual count. `max_workers` controls how many audit batches run concurrently; it does not change the number of batches.

Settings are in `config.yaml`:

| Setting | Default | Purpose |
| --- | --- | --- |
| `llm.provider` | `anthropic` | Provider: `anthropic` or `gemini`. |
| `llm.model` | `claude-sonnet-4-5` | Provider-specific model ID. |
| `llm.max_tokens` | `2000` | Maximum generated output tokens. |
| `llm.temperature` | `0.2` | Generation temperature. |
| `llm.max_retries` | `3` | Retries for retryable API failures. |
| `pipeline.max_claims` | `12` | Maximum claims extracted per document. |
| `pipeline.max_workers` | `4` | Concurrent audit batches. |
| `pipeline.audit_batch_size` | `3` | Claims per audit request. |
| `pipeline.max_input_chars` | `20000` | Maximum source length; longer input is truncated. |
| `cache.enabled` | `true` | Enable the local response cache. |
| `cache.dir` | `.cache` | Cache directory. |
| `output.dir` | `reports` | Report output directory. |

Gemini model IDs and quotas depend on API access and project limits. Use a model ID supported by your key for `generateContent`; a model being listed in a dashboard does not guarantee a particular free-tier request limit.

## How the Audit Works

1. The model extracts up to `max_claims` distinct, checkable claims.
2. Claims are grouped into batches. Each batch is audited against the original source, returning a verdict, quote, issues, confidence, rationale, and suggested rewrite per claim.
3. The application checks each quote against the source and calculates the overall score from the verdicts.
4. The model writes a short executive summary and the CLI saves both report formats.

If an audit batch fails or omits a claim, that claim remains in the report with an error rather than being silently removed. Review error fields before relying on the score. The score reflects the supplied document's support, not whether the claims are true in the outside world.

## Development

Install dependencies, then run the offline test suite:

```bash
python -m pip install -r requirements.txt
python -m pytest -q
```

Tests use fake clients and do not require API keys or network access.

## Project Layout

```text
claim_auditor/       CLI, configuration, LLM client, pipeline, and report generation
tests/               Offline pipeline tests
samples/             Example source document
config.yaml          Runtime settings
prompts.yaml         Extraction, audit, and summary prompts
.env.example         Provider configuration template
```
