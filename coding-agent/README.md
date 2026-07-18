# Optional local coding agent

This folder provides a small, operator-triggered coding workflow using the main
Ollama service and a local Ministral 3 8B GGUF. Nothing is downloaded or
created during RPM installation.

## Setup

The default follows the repository's current revision:

```bash
sudo bc250-setup-coding-agent
```

Set `CODING_AGENT_REVISION` to a commit, tag or branch such as `main`; the
special value `latest` follows the default revision. Set
`CODING_AGENT_SHA256` when a checksum must be enforced.

The download is about 6.1 GB and the script requires at least 8 GiB free in
`/var/llm/gguf`. It creates
`coding-ministral3-8b-unsloth-ud-q5-k-xl`.

## Generate, refactor and review

```bash
bc250-code review src/app.py review.md
bc250-code refactor src/app.py src/app.refactored.py \
  "Keep the public API stable"
printf '%s\n' "Create a Python health endpoint" |
  bc250-code generate - health.py
```

Generated code is never applied automatically. Review it, run the real test
suite and compare behavior before replacing files. Inputs are limited to about
60 KB by default so they fit the local model context; split larger reviews.

## Local commits

Stage only the intended changes, then ask for a commit message:

```bash
git add path/to/files
bc250-code-commit
```

The command shows the proposed message and asks before creating a local commit.
It never stages files, pushes, opens a pull request or merges.

## Gitea pull-request review

Create a limited Gitea token. Read access to the repository and pull request is
enough for local reviews. Posting with `--post` additionally needs permission
to create issue comments.

```bash
mkdir -p ~/.config/bc250-coding-agent
cp /usr/share/bc250-llm-server/examples/coding-agent/gitea.env.example \
  ~/.config/bc250-coding-agent/gitea.env
chmod 0600 ~/.config/bc250-coding-agent/gitea.env
$EDITOR ~/.config/bc250-coding-agent/gitea.env

bc250-gitea-review OWNER/REPOSITORY 42
bc250-gitea-review OWNER/REPOSITORY 42 --output review.md
bc250-gitea-review OWNER/REPOSITORY 42 --post
```

`--post` displays the complete comment and asks for confirmation. The script
does not approve or merge the pull request.

The local file and commit commands work in repositories hosted by Gitea,
Forgejo or GitHub. The remote review script currently targets the Gitea API;
Forgejo compatibility may work for matching endpoints but is not promised, and
the GitHub API is not implemented in this testing version.

## Security notes

- Source files, diffs and issue text are passed to the model as untrusted data.
- Keep tokens in the mode-0600 configuration file, not in command history.
- Prefer a token restricted to one test repository.
- Review every generated file and remote comment.
- Do not use `GITEA_INSECURE=1` outside an isolated reviewed test environment.
