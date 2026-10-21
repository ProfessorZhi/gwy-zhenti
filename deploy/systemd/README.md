# systemd user-unit templates

These files are **templates only**. They are never installed or started by this
repository, and merging them does not authorize a production cutover.

1. Copy `fenbi-pipeline.service.example` to
   `~/.config/systemd/user/fenbi-pipeline.service` and/or copy
   `fenbi-publisher.service.example` to
   `~/.config/systemd/user/fenbi-publisher.service`.
2. Replace **every** `REPO_ABSOLUTE_PATH` with the verified absolute path
   to the applicable checkout. The collector path should point to its tracked
   driver code; the Publisher may still have a **separate worktree** until
   an explicitly approved production cutover. Never prefix absolute paths
   with `%h/`.
3. For the collector unit, replace `NODE_ABSOLUTE_PATH` with the absolute
   Node 22 executable path verified on the target host. Do not rely on the
   systemd user service inheriting an interactive shell's `PATH`. The
   Publisher shell script also calls `node`; configure and verify its PATH
   in the host-local service environment before enabling it.
4. Keep any `EnvironmentFile=` reference host-local and outside the checkout.
   Profile, tokens, `rights.json`, caches, documents and images are not
   part of these templates. The `FENBI_WORK_DIR` override, if used, must be
   the **same absolute directory** for all collector subprocesses.
5. After replacing the placeholders, validate the resolved units with
   `systemd-analyze verify`. Reload/start/restart only during a separately
   authorized deployment.

Publisher switch examples in the template (`CAPTURE=0`,
`ALLOW_REPLACE=1`, `PUSH=1`, `AUTO_MAIN_CONTENT=1`,
`AUTO_MAIN_APPLY=0`) are **not** permissions and do not grant publication
rights. The live Publisher uses a different worktree commit than `main`.
