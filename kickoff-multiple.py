import os
import subprocess
import time
import pyautogui
import pyperclip

PROMPTS = [
    (
        "read the ticket specified in cd ../tickets/{ticket_file}, then, clean all uncommited changes and go to master, "
        "fetch, pull, create a new branch from it and write a plan inside the "
        "plan/1-high-level-plan.md file on how to solve the issue. Everytime you see (subagent), run the command in the subagent."
    ),
    "/plan",
    "proceed with the implementation then as planned",
    "/codereview",
    "Analyse the files created by the codereview, adding a solution plan to each file.",
    "proceed with the recommended solution plan for each of them attached to each of the code-review files",
    "/prdescription",
    "Commit now your changes, but do not stage any .md file. Then push to origin and create a draft pull request with the description found in plan/3-pr-description.md, remember to include the code of the ticket in both title and description. After that add the PR link to the file ../tickets/prs.md, if there are already other urls there, just add it to the end of the file",
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
SHUTDOWN_DELAY_SECONDS = 10
POLL_MOVE_PIXELS = 5  # Move mouse this many pixels right then back after each poll (keeps screen awake)
READY_INSTRUCTION = " Do not ask questions about design choice to the user, make them yourself. If you were to give options to the user, just follow the one you would recommend. After you've finished everything, and I mean literally everything, even the audit and other commands that you should run, run: touch .agent-ready in the repo root (frontend) and wait for the next prompt."


# Command files live in frontend repo; when script runs on Windows, that repo may be in WSL only.
COMMANDS_DIR_WSL = "~/puzzle/frontend/.cursor/commands"
TICKETS_DIR_LOCAL = os.path.expanduser("~/puzzle/tickets")
TICKETS_DIR_WSL = "~/puzzle/tickets"


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
    if prompt.startswith("/"):
        name = prompt.lstrip("/")
        return load_command(name) or prompt
    return prompt


def ticket_exists(ticket_file: str) -> bool:
    """Check if a ticket file exists locally or in WSL."""
    local_path = os.path.join(TICKETS_DIR_LOCAL, ticket_file)
    if os.path.isfile(local_path):
        return True
    r = subprocess.run(
        ["wsl", "-e", "bash", "-c", f"test -f {TICKETS_DIR_WSL}/{ticket_file}"],
        capture_output=True,
    )
    return r.returncode == 0


def get_ticket_sequence() -> list[str]:
    """Return ticket.md, then ticket-1.md, ticket-2.md... until first missing numbered file."""
    ticket_files: list[str] = []
    if ticket_exists("ticket.md"):
        ticket_files.append("ticket.md")

    index = 1
    while True:
        numbered = f"ticket-{index}.md"
        if not ticket_exists(numbered):
            break
        ticket_files.append(numbered)
        index += 1
    return ticket_files


def should_shutdown_after_completion() -> bool:
    """Ask user whether the computer should shut down after all tickets finish."""
    answer = input("Shut down computer after all tickets complete? [Y/N]: ")
    return answer.strip().upper() == "Y"


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


_current_agent_proc: subprocess.Popen | None = None


def stop_agent() -> None:
    """Terminate any previously started agent terminal and kill WSL-side agent processes."""
    global _current_agent_proc
    if _current_agent_proc is not None:
        _current_agent_proc.terminate()
        _current_agent_proc = None
    subprocess.run(
        ["wsl", "-e", "bash", "-c", "pkill -f 'agent --force' 2>/dev/null; true"],
        capture_output=True,
    )


def start_agent() -> None:
    """Open Windows Terminal with interactive agent in frontend repo."""
    global _current_agent_proc
    stop_agent()
    time.sleep(5)
    _current_agent_proc = subprocess.Popen(
        ["wt.exe", "wsl", "-e", "bash", "-i", "-c", "cd ~/puzzle/frontend && agent --force"],
        shell=False,
    )
    print(f"Waiting {AGENT_START_WAIT_SECONDS}s for agent to start...")
    time.sleep(AGENT_START_WAIT_SECONDS)


def update_ticket_progress(ticket_file: str, prompt_label: str) -> None:
    """Append a sent prompt to the progress section at the bottom of the ticket file."""
    ticket_path = os.path.join(TICKETS_DIR_LOCAL, ticket_file)
    try:
        with open(ticket_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return

    if "## Progress" not in content:
        content = content.rstrip() + "\n\n## Progress\n"

    content += f"- [x] {prompt_label}\n"

    with open(ticket_path, "w", encoding="utf-8") as f:
        f.write(content)


def run_prompts_for_ticket(ticket_file: str, center_x: int, center_y: int) -> None:
    """Run the full prompt flow for one ticket file."""
    print(f"\n=== Processing {ticket_file} ===")
    _remove_agent_ready_in_wsl()
    start_agent()

    for i, prompt in enumerate(PROMPTS, 1):
        prompt_with_ticket = prompt.format(ticket_file=ticket_file)
        resolved = resolve_prompt(prompt_with_ticket)
        full_prompt = resolved + READY_INSTRUCTION
        preview = full_prompt[:55] + "..." if len(full_prompt) > 55 else full_prompt
        if prompt_with_ticket.startswith("/"):
            print(f"Prompt {i}/{len(PROMPTS)}: [command {prompt_with_ticket}]")
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
        update_ticket_progress(ticket_file, prompt_with_ticket)

    wait_for_agent_ready(center_x, center_y)
    print(f"Completed {ticket_file}.")


def main():
    shutdown_after_completion = should_shutdown_after_completion()
    ticket_files = get_ticket_sequence()
    if not ticket_files:
        print("No ticket files found (expected ticket.md or ticket-1.md, ticket-2.md...).")
        return

    print("Ticket run order:", ", ".join(ticket_files))
    screen_w, screen_h = pyautogui.size()
    center_x, center_y = screen_w // 2, screen_h // 2

    for ticket_file in ticket_files:
        run_prompts_for_ticket(ticket_file, center_x, center_y)

    print("\nAll ticket flows completed. Done.")
    if shutdown_after_completion:
        print(f"Shutting down in {SHUTDOWN_DELAY_SECONDS} seconds...")
        time.sleep(SHUTDOWN_DELAY_SECONDS)
        if os.name == "nt":
            subprocess.run(["shutdown", "/s", "/t", "0"], check=False)
        else:
            subprocess.run(["shutdown", "-h", "now"], check=False)


if __name__ == "__main__":
    main()
