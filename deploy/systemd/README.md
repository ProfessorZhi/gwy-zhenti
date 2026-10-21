# systemd user-unit templates

These are templates, never installed by this repository.

1. Copy `fenbi-pipeline.service.example` and/or `fenbi-publisher.service.example`
   to `~/.config/systemd/user/`.
2. Replace every `REPO_PLACEHOLDER` with the absolute checkout path. systemd does
   not expand shell variables in `ExecStart`, so no `${VAR}` form is used.
3. Keep `EnvironmentFile=` entries host-local (they are outside the repo and
   gitignored). Do not add `rights.json`, cookies, tokens or profile paths here.
4. `systemctl --user daemon-reload`, then enable/start manually.

The publisher template lists only environment variable names and non-sensitive
enums (`CAPTURE=0`, `ALLOW_REPLACE=1`, `PUSH=1`, `AUTO_MAIN_CONTENT=1`,
`AUTO_MAIN_APPLY=0`). They are not permissions and do not grant publication
rights. The live publisher worktree runs at a different commit than `main`.
