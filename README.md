# AI_Devs Course Playground

Welcome, Artur. This is our dedicated space for the [AI_Devs](https://www.aidevs.pl/) course, starting 2026-03-09.

## Structure Overview

We are using a **feature-based modular approach**:

- `lessons/`: Contains a folder for each lesson.
  - Inside each lesson folder, you will find notes (`lesson.md`), and any code, scripts, or configurations specifically required for that lesson (e.g., `pyproject.toml`, `main.py`).
- `terraform/`: Contains our GCP infrastructure definitions following standard Google Cloud Terraform module structures.

## Setup
We use `uv` for Python dependency management.
Infrastructure is deployed via Terraform to GCP.
