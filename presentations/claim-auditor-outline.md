# Claim Auditor Presentation Outline

## Slide 1: Title

- Claim Auditor
- Aarush Kumar, 23FE10CDS00363
- CSE Data Science and Engineering, 7th semester, Section E
- MUJ Data Science Training Program, Batch F

## Slide 2: Problem

- Articles can mix evidence with exaggerated conclusions.
- Manually checking every claim is slow.
- The project checks how well a document supports its own claims.

## Slide 3: Approach

- Extract checkable claims from the input text.
- Audit claims against the same source text in small batches.
- Verify evidence quotes in Python.
- Score verdicts and generate a summary.

## Slide 4: NLP and LLM

- NLP is needed to interpret ordinary written language and claim meaning.
- An LLM handles varied wording and contextual comparisons.
- Python calls the LLM API and validates structured JSON responses.

## Slide 5: Implementation

- Python CLI and local FastAPI web interface.
- Anthropic and Gemini API support.
- YAML prompts and configuration.
- Response caching, retries, concurrent batches, and offline tests.

## Slide 6: Demonstration Results

- Sample: intermittent-fasting blog article.
- 8 claims reviewed: 5 supported, 1 overstated, 2 unsupported.
- Evidence score: 66.2/100.
- The score measures support in the article, not real-world truth.

## Slide 7: Limitations and Future Work

- No external fact-checking or source retrieval.
- LLM judgments can still be wrong; quote matching only confirms the quote exists.
- Possible extensions: source citations, more evaluation data, and reviewer feedback.

## Slide 8: Demo

- Run `python -m claim_auditor.cli samples/blogs.txt` from `code/claim-auditor`.
- Or start the web UI with `python -m uvicorn claim_auditor.web:app --reload`.