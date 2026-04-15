import os
import shlex
import subprocess
import sys

TICKET_FILE = "ticket-3.md"

PROMPTS = [
    (
        "read the ticket specified in cd ../tickets/{TICKET_FILE}, then, go to master, "
        "fetch, pull, create a new branch from it and write a plan inside the "
        "plan/1-high-level-plan.md file on how to solve the issue. Everytime you see (subagent), run the command in the subagent."
    ),
    "/plan",
    "proceed with the implementation then as planned",
    "/codereview",
    "Analyse the files created by the codereview, adding a solution plan to each file.",
    "proceed with the recommended solution plan for each of them attached to each of the code-review files",
    "Check if there isn't any changes unrelated to the ticket specified in cd ../tickets/{TICKET_FILE}, if there are, revert them",
    "/prdescription",
    "Commit now your changes, but do not stage any .md file. Then push to origin and create a draft pull request with the description found in plan/3-pr-description.md, remember to include the code of the ticket in both title and description",
]

FRONTEND_DIR_WSL = "~/puzzle/frontend"
COMMANDS_DIR_WSL = "~/puzzle/frontend/.cursor/commands"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TICKET_PATH = os.path.join(SCRIPT_DIR, "ticket.md")

AGENT_INSTRUCTION = (
    " Do not ask questions about design choice to the user, make them yourself."
    " If you were to give options to the user, just follow the one you would recommend."
    " After you've finished everything, and I mean literally everything,"
    " even the audit and other commands that you should run, just stop."
)


def load_command(name: str) -> str | None:
    """Load a Cursor command from frontend .cursor/commands/<name>.md via WSL."""
    r = subprocess.run(
        ["wsl", "-e", "bash", "-c", f"cat {COMMANDS_DIR_WSL}/{name}.md 2>/dev/null"],
        capture_output=True,
        text=True,
    )
    if r.returncode == 0 and r.stdout:
        return r.stdout.strip()
    return None


def resolve_prompt(prompt: str) -> str:
    """If prompt is a slash command, load its content so the agent runs the command, not the mode."""
    if prompt.startswith("/"):
        name = prompt.lstrip("/")
        return load_command(name) or prompt
    return prompt


def run_agent_prompt(prompt: str, *, continue_session: bool = False) -> int:
    """Run a single agent prompt in print mode via WSL. Returns exit code.

    Uses `agent -p` (non-interactive print mode) so prompts are injected
    programmatically as CLI arguments — no GUI window or copy-paste needed.
    Session context is preserved across prompts via --continue.
    """
    agent_cmd = f"agent -p --force --trust --workspace {FRONTEND_DIR_WSL}"
    if continue_session:
        agent_cmd += " --continue"
    agent_cmd += f" {shlex.quote(prompt)}"
    result = subprocess.run(["wsl", "-e", "bash", "-lc", agent_cmd])
    return result.returncode


def update_ticket_progress(prompt_label: str) -> None:
    """Append a sent prompt to the progress section at the bottom of the ticket file."""
    try:
        with open(TICKET_PATH, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return

    if "## Progress" not in content:
        content = content.rstrip() + "\n\n## Progress\n"

    content += f"- [x] {prompt_label}\n"

    with open(TICKET_PATH, "w", encoding="utf-8") as f:
        f.write(content)


def main():
    for i, prompt in enumerate(PROMPTS, 1):
        prompt_filled = prompt.format(TICKET_FILE=TICKET_FILE)
        resolved = resolve_prompt(prompt_filled)
        full_prompt = resolved + AGENT_INSTRUCTION

        preview = full_prompt[:55] + "..." if len(full_prompt) > 55 else full_prompt
        if resolved != prompt_filled:
            print(f"Prompt {i}/{len(PROMPTS)}: [command {prompt}]", flush=True)
        else:
            print(f"Prompt {i}/{len(PROMPTS)}: {preview}", flush=True)

        returncode = run_agent_prompt(full_prompt, continue_session=(i > 1))

        if returncode != 0:
            print(f"Agent exited with code {returncode}. Aborting.", flush=True)
            sys.exit(returncode)

        update_ticket_progress(prompt)

    print("All prompts sent and completed. Done.", flush=True)


if __name__ == "__main__":
    main()
