#!/usr/bin/env python3
import os
import subprocess
import sys
from datetime import datetime


def run_cmd(cmd, cwd=None):
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def check_git_initialized():
    return os.path.exists(".git")


def get_git_config():
    code, username, _ = run_cmd("git config user.name")
    if code != 0:
        username = ""
    code, email, _ = run_cmd("git config user.email")
    if code != 0:
        email = ""
    return username.strip(), email.strip()


def check_remote_configured():
    code, remote_out, _ = run_cmd("git remote -v")
    return code == 0 and remote_out.strip() != ""


def main():
    if not check_git_initialized():
        print("Git is not initialized in this project.")

        # Ask for remote URL
        remote_url = input(
            "Enter GitHub remote URL (e.g., git@github.com:user/repo.git): "
        ).strip()
        if not remote_url:
            print("Remote URL is required. Exiting.")
            sys.exit(1)

        # Initialize git
        print("\nInitializing git...")
        run_cmd("git init")

        # Add remote
        print(f"Adding remote: {remote_url}")
        run_cmd(f"git remote add origin {remote_url}")

        # Ask about git config
        print("\nGit user configuration:")
        change_config = (
            input(
                "Do you want to change GitHub username and email? (y/n, default: n): "
            )
            .strip()
            .lower()
        )

        if change_config == "y":
            username = input("Enter GitHub username: ").strip()
            email = input("Enter GitHub email: ").strip()
            if username:
                run_cmd(f'git config user.name "{username}"')
            if email:
                run_cmd(f'git config user.email "{email}"')
        else:
            print("Using default git config.")

        print("\nGit initialized successfully!")
        sys.exit(0)

    # Check if remote is configured
    if not check_remote_configured():
        print("Git is initialized but remote is not configured.")
        remote_url = input(
            "Enter GitHub remote URL (e.g., git@github.com:user/repo.git): "
        ).strip()
        if remote_url:
            run_cmd(f"git remote add origin {remote_url}")
            print("Remote added.")

    # Check git config
    username, email = get_git_config()
    if not username or not email:
        print("Git user.name or user.email not configured.")
        print("Please configure git config first:")
        print("  git config user.name 'Your Name'")
        print("  git config user.email 'your@email.com'")
        sys.exit(1)

    print(f"Git user: {username} <{email}>")

    # Add all changes
    print("\nStep 2: Committing changes...")
    print("Running: git add .")
    run_cmd("git add .")

    # Check if there are changes to commit
    code, status, _ = run_cmd("git status --porcelain")
    if not status.strip():
        print("No changes to commit.")
        sys.exit(0)

    # Determine commit message
    code, log_out, _ = run_cmd("git log --oneline")
    is_initial = not log_out.strip()

    if is_initial:
        commit_msg = "Initial commit"
    else:
        now = datetime.now()
        commit_msg = f"Update: {now.strftime('%m%d%H%M')}"

    print(f"Running: git commit -m '{commit_msg}'")
    run_cmd(f'git commit -m "{commit_msg}"')

    # Push
    print("\nStep 3: Pushing to remote...")
    print("Running: git push -u origin main")
    code, out, err = run_cmd("git push -u origin main")
    if code != 0:
        print("Trying master branch...")
        code, out, err = run_cmd("git push -u origin master")

    if code == 0:
        print("Pushed successfully!")
    else:
        print(f"Push failed: {err}")


if __name__ == "__main__":
    main()
