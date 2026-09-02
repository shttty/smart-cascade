# Raw SSH/tmux fallback

Use this only when the high-level `hermes_claude_code` MCP surface is unavailable or the user explicitly requests raw remote control.

## Preflight

Run through the same interactive login shell used by Claude Code:

```bash
ssh <host> 'zsh -lic '\''cd /path/to/repo && git status --short --branch && command -v claude && claude --version && claude auth status --text'\'''
```

A plain `bash -lc` may miss PATH, provider URLs, auth tokens, and model aliases from `.zshrc`.

## Launch

If nested quoting becomes brittle, create a small remote launcher and execute Claude through `zsh -lic`. Use a fresh, explicitly named tmux session for a bounded task. Do not replace or kill a user-controlled session without permission.

## Submit

For a controller driving remote tmux, stream the prompt over SSH stdin; a local `/tmp` path does not exist remotely:

```bash
ssh <host> 'tmux load-buffer -b task -' < /tmp/task.txt
ssh <host> 'tmux paste-buffer -b task -t cc-task'
ssh <host> 'tmux send-keys -t cc-task Enter'
ssh <host> 'tmux capture-pane -t cc-task -p -S -100'
```

Visible text is not proof of submission. Require the pane to move into active processing/history; if text remains at the prompt, send Enter and capture again.

## Completion

A watcher or pane is only a hint. Parent Hermes inspects the remote repository and reruns tests before reporting completion or committing:

```bash
git status --short --branch
git diff --stat
git diff --check
```

Add project-specific tests, compile/static checks, and a real-behaviour smoke.

## Runtime hygiene

Before dispatch, define allowed files and non-goals. In service repositories, guard runtime artifacts, ad-hoc payloads/probes, launcher scripts, and unrelated lockfile churn. Commit only after parent verification passes.
