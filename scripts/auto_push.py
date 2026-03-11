#!/usr/bin/env python3
import os
import subprocess
from datetime import datetime


def run(cmd, check=True):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Error: {result.stderr.strip()}")
        exit(1)
    return result


def check_git_initialized():
    if not os.path.isdir(".git"):
        print("Error: .git directory not found. Run 'git init' first.")
        exit(1)


def check_git_config():
    name_result = run("git config user.name", check=False)
    email_result = run("git config user.email", check=False)

    if not name_result.stdout.strip():
        print('Error: user.name not configured. Run: git config user.name "Your Name"')
        exit(1)
    if not email_result.stdout.strip():
        print(
            'Error: user.email not configured. Run: git config user.email "your@email.com"'
        )
        exit(1)


def get_commit_message():
    result = run("git rev-parse --is-inside-work-tree", check=False)
    is_initial = (
        result.returncode != 0
        or not run("git rev-parse HEAD", check=False).stdout.strip()
    )

    if is_initial:
        return "Initial commit"
    else:
        return f"Update: {datetime.now().strftime('%m%d%H%M')}"


def commit():
    run("git add -A")
    msg = get_commit_message()
    run(f'git commit -m "{msg}"')
    print(f"Committed: {msg}")


def push():
    for branch in ["main", "master"]:
        result = run(f"git push origin {branch}", check=False)
        if result.returncode == 0:
            print(f"Pushed to {branch}")
            return
    print("Error: Failed to push to remote")


def main():
    check_git_initialized()
    check_git_config()
    commit()
    push()


if __name__ == "__main__":
    main()
