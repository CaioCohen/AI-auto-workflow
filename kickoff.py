import os
import subprocess
import time
import pyautogui
import pyperclip

TICKET_FILE = "ticket-1.md"

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

# When the agent finishes a prompt, it should run: touch .agent-ready (in frontend repo root).
# We poll for this file and then send the next prompt.
# Agent runs in WSL, so we must check the file via WSL (otherwise Windows path != WSL path).
FRONTEND_DIR = os.path.expanduser("~/puzzle/frontend")
COMMANDS_DIR = os.path.join(FRONTEND_DIR, ".cursor", "commands")
AGENT_READY_FILE_WSL = "~/puzzle/frontend/.agent-ready"
POLL_INTERVAL_SECONDS = 15
AGENT_START_WAIT_SECONDS = 10
READY_TO_PROMPT_WAIT_SECONDS = 10  # Wait this long after .agent-ready before pasting next prompt
POLL_MOVE_PIXELS = 5  # Move mouse this many pixels right then back after each poll (keeps screen awake)
READY_INSTRUCTION = " Do not ask questions about design choice to the user, make them yourself. If you were to give options to the user, just follow the one you would recommend. After you've finished everything, and I mean literally everything, even the audit and other commands that you should run, run: touch .agent-ready in the repo root and wait for the next prompt."


# Command files live in frontend repo; when script runs on Windows, that repo may be in WSL only.
COMMANDS_DIR_WSL = "~/puzzle/frontend/.cursor/commands"
TICKET_PATH = os.path.expanduser("~/puzzle/tickets/ticket.md")


def load_command(name: str) -> str | None:
    """Load a Cursor command from frontend .cursor/commands/<name>.md. Tries local path then WSL."""
    path = os.path.join(COMMANDS_DIR, f"{name}.md")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        pass
    # Script may run on Windows while frontend is in WSL; load via WSL.
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
    if prompt == "/plan":
        return load_command("plan") or prompt
    if prompt == "/codereview":
        return load_command("codereview") or prompt
    return prompt


def _agent_ready_exists_in_wsl() -> bool:
    """Check if .agent-ready exists in WSL frontend dir (agent runs in WSL)."""
    r = subprocess.run(
        ["wsl", "-e", "bash", "-c", f"test -f {AGENT_READY_FILE_WSL}"],
        capture_output=True,
    )
    return r.returncode == 0


def _remove_agent_ready_in_wsl() -> None:
    """Remove .agent-ready in WSL frontend dir."""
    subprocess.run(
        ["wsl", "-e", "bash", "-c", f"rm -f {AGENT_READY_FILE_WSL}"],
        capture_output=True,
    )


def wait_for_agent_ready(center_x: int, center_y: int):
    """Poll until .agent-ready exists in frontend repo (in WSL), then remove it.
    After each poll, move mouse slightly right then back and click to avoid screen lock."""
    print("Waiting for agent to finish (polling for .agent-ready)...")
    poll_count = 0
    while True:
        poll_count += 1
        print(f"  Poll {poll_count}...", flush=True)
        if _agent_ready_exists_in_wsl():
            _remove_agent_ready_in_wsl()
            print("  Ready.")
            return
        # Small mouse move + click to keep screen from locking
        pyautogui.moveTo(center_x + POLL_MOVE_PIXELS, center_y)
        pyautogui.moveTo(center_x, center_y)
        pyautogui.click()
        time.sleep(POLL_INTERVAL_SECONDS)


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
    # 1. Open Windows Terminal with interactive agent in frontend repo.
    # --force (yolo): auto-allow terminal commands and file writes without prompting.
    subprocess.Popen(
        ["wt.exe", "wsl", "-e", "bash", "-i", "-c", "cd ~/puzzle/frontend && agent --force"],
        shell=False,
    )
    print(f"Waiting {AGENT_START_WAIT_SECONDS}s for agent to start...")
    time.sleep(AGENT_START_WAIT_SECONDS)

    screen_w, screen_h = pyautogui.size()
    center_x, center_y = screen_w // 2, screen_h // 2

    for i, prompt in enumerate(PROMPTS, 1):
        prompt_filled = prompt.format(TICKET_FILE=TICKET_FILE)
        resolved = resolve_prompt(prompt_filled)
        full_prompt = resolved + READY_INSTRUCTION
        preview = full_prompt[:55] + "..." if len(full_prompt) > 55 else full_prompt
        if resolved != prompt:
            print(f"Prompt {i}/{len(PROMPTS)}: [command {prompt}]")
        else:
            print(f"Prompt {i}/{len(PROMPTS)}: {preview}")

        if i > 1:
            wait_for_agent_ready(center_x, center_y)
            print(f"Waiting {READY_TO_PROMPT_WAIT_SECONDS}s before pasting next prompt...")
            time.sleep(READY_TO_PROMPT_WAIT_SECONDS)

        pyautogui.moveTo(center_x, center_y)
        pyautogui.click()
        time.sleep(0.5)
        pyperclip.copy(full_prompt)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.3)
        pyautogui.press("enter")
        update_ticket_progress(prompt)

    wait_for_agent_ready(center_x, center_y)
    print("All prompts sent and completed. Done.")


if __name__ == "__main__":
    main()
