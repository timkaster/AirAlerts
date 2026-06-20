# AGENTS.md

## Project Context

This project is a mini Python research/engineering task: time series analysis of air raid alerts in Ukraine. The expected output should combine reproducible data work, clear reasoning, and practical defense-analytics framing.

AI assistance is allowed and expected, but it must be used as an engineering tool. Keep decisions traceable in `RESEARCH_LOG.md`.

## Working Principles

- Prefer small, reproducible Python scripts or notebooks over one-off manual analysis.
- Keep source data, transformed data, figures, and reports clearly separated.
- Document assumptions before relying on them.
- Validate time zones, alert start/end semantics, missing data, duplicated records, and regional naming before modeling.
- Use baselines before complex models.
- Favor explainable results over overly elaborate forecasting that cannot be defended.

## Suggested Structure

- `data/raw/` for downloaded or provided source data.
- `data/interim/` for cleaned but not final datasets.
- `data/processed/` for analysis-ready tables.
- `notebooks/` for exploratory work.
- `src/` for reusable loading, cleaning, feature, modeling, and plotting code.
- `reports/` for final writeups and figures.
- `tests/` for focused validation of parsing and transformations.

## Research Expectations

For each meaningful research or implementation step, update `RESEARCH_LOG.md` with:

- Date and goal.
- Sources consulted.
- Data or method chosen.
- Assumptions and risks.
- Result or next step.

## Coding Guidelines

- Use type hints for reusable functions.
- Keep IO paths configurable where practical.
- Avoid hardcoded absolute paths in committed code.
- Use deterministic seeds for experiments.
- Add quick checks or tests for data cleaning rules that could change conclusions.

## Git Hygiene

- Do not commit virtual environments, IDE folders, raw secrets, or bulky generated artifacts.
- Commit source code, small documentation files, configuration, and lightweight reproducibility metadata.
- Keep commits organized around coherent milestones: setup, data ingestion, cleaning, EDA, modeling, report.
