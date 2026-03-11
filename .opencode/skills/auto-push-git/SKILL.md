---
name: auto-push-git
description: Automatically initialize git repository, commit changes with timestamp-based messages, and push to remote. Use when: (1) User wants to quickly commit and push code to GitHub, (2) Project needs git initialization with remote configuration, (3) Automated commit workflow is needed
---

# Auto Push Git

## Usage

Run the script to commit and push:

```bash
python3 scripts/auto_push.py
```

## Workflow

### Step 1: Check Git Initialization

- If `.git` directory exists → proceed to Step 2
- If not initialized → user needs to run `git init` first

### Step 2: Check Git Config

Verify `user.name` and `user.email` are configured:

```bash
git config user.name "Your Name"
git config user.email "your@email.com"
```

### Step 3: Commit

- First commit message: `Initial commit`
- Subsequent commits: `Update: MMDDHHMM` (e.g., `Update: 03112315`)

### Step 4: Push

Push to remote origin (tries `main` first, then `master`).

## Script Location

`scripts/auto_push.py` - Execute directly with Python 3.
