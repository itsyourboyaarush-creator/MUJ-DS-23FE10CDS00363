# MUJ Data Science Training Portfolio

## Student Profile

- **Name:** Aarush Kumar
- **Registration Number:** 23FE10CDS00363
- **Branch:** CSE Data Science and Engineering
- **Semester:** 7th
- **Section:** E
- **Training Batch:** F
- **Project Title:** Claim Auditor
- **GitHub Username:** [itsyourboyaarush-creator](https://github.com/itsyourboyaarush-creator)
- **Training Program:** MUJ Data Science Training Program

## Project: Claim Auditor

Claim Auditor analyzes claims in a supplied document and checks how well the document itself supports them. It uses an LLM to extract and assess claims, verifies that quoted evidence occurs in the source, calculates a deterministic evidence score, and generates Markdown and JSON reports.

The project evaluates support within the submitted text; it does not independently verify facts against external sources.

## Capstone Repository

The capstone is a separate project whose topic is awaiting instructor approval: [MUJ-DS-23FE10CDS00363-Capstone](https://github.com/itsyourboyaarush-creator/MUJ-DS-23FE10CDS00363-Capstone).

### Run the project

```powershell
cd code/claim-auditor
python -m pip install -r requirements.txt
python -m claim_auditor.cli samples/blogs.txt
```

To start the local web interface:

```powershell
python -m uvicorn claim_auditor.web:app --reload
```

Set the provider API key in a local `.env` file before running an uncached audit. Never commit `.env` or API keys.

## Repository Structure

```text
assignments/                 Training assignments
notebooks/                   Exploratory and analysis notebooks
code/claim-auditor/          Claim Auditor source, tests, and setup guide
resources/results/           Example Markdown and JSON audit results
resources/screenshots/       Application screenshots
presentations/               Presentation outline and slides
capstone/                    Individual capstone project information
```

## Training and Contributions

This repository is the individual training portfolio for Batch F. Meaningful work should be committed regularly. Use issues to track tasks and branches and pull requests to review substantial changes.

The current project contribution includes the Python audit pipeline, LLM integration, prompts, tests, command-line interface, and local web interface. Additional assignments, notebooks, screenshots, and presentation slides should be added as they are completed.