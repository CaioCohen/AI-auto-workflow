import shlex
import subprocess
import sys

BRANCH_NAME = "CORE-7231-update-all-ledger-account-selectors-to-use-consistent-dropdown-menu"

PROMPTS = [
    "Go to the branch: {BRANCH_NAME} and fetch and pull to get it up to date with remote",
    "/personal/getContext",
    "Now, I want you to run: pnpm dev:app:prod in the root. This command should take from 10 to 20 minutes to finish, just wait, return when the build has finished already. If it fails, fix the issue and run the command again.",
    "/personal/openBrowser",
    "Perform the manual tests specified in the Pull Request description. If you go to a page and there is no data available, try broadening the filters, starting with the daterange. Add the results of the tests in the plan/5-manual-test-report.md file.",
    "read the plan/5-manual-test-report.md file, if any test has failed, analyse the problem and add to the file a proposed solution to fix it (but do not fix it yet). If all tests have passed, just say so.",
]

FRONTEND_DIR_WSL = "~/puzzle/frontend"
COMMANDS_DIR_WSL = "~/puzzle/frontend/.cursor/commands"

AGENT_INSTRUCTION = (
    " Do not ask questions about design choice to the user, make them yourself."
    " If you were to give options to the user, just follow the one you would recommend."
    " After you've finished all the testing steps, just stop."
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

    wsl_cmd = ["wsl", "-e", "bash", "-lc", agent_cmd]
    print(f"  > {' '.join(wsl_cmd[:4])} ...", flush=True)

    proc = subprocess.Popen(
        wsl_cmd,
        stdout=sys.stdout,
        stderr=sys.stderr,
        bufsize=0,
    )
    return proc.wait()


def main():
    for i, prompt in enumerate(PROMPTS, 1):
        prompt_filled = prompt.format(BRANCH_NAME=BRANCH_NAME)
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

    print("All prompts sent and completed. Done.", flush=True)


if __name__ == "__main__":
    main()
