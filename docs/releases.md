# Releases

The `CI` workflow in `.github/workflows/ci.yml` runs Python Semantic Release 10.7.0 after both the
Linux package matrix and real-server integration pass for a push to `main`. Pull requests and other
branches cannot publish. A stale workflow skips release if `main` has moved; release jobs are serialized.

Use Conventional Commits in the commits that land on `main` (or the squash merge title):

| Commit | Version change |
|---|---|
| `fix: ...`, `perf: ...` | Patch |
| `feat: ...` | Minor |
| `feat!: ...` or a `BREAKING CHANGE:` footer | Major, including from 0.x to 1.0.0 |
| `docs: ...`, `chore: ...`, `ci: ...`, `test: ...` | No release on their own |

With the current untagged history, the first release is `0.1.0`. Do not create a baseline tag manually:
that would tell the release tool the version was already released. Versions are derived from Git tags;
`project.version`, `uv.lock` and `CHANGELOG.md` are updated automatically. The release commit is
`chore(release): VERSION [skip ci]` and the tag is `vVERSION`.

The build refreshes only project metadata in the lockfile using `uv lock --upgrade-package "$PACKAGE_NAME"`, builds wheel/sdist,
and checks installation. Before publishing anything, CI saves the distributions, release notes and a Git
bundle containing the prepared commit and tag as the workflow artifact `release-dist` (retained for 30 days).
A separate job pushes the commit and tag atomically, creates the GitHub Release and attaches those saved
distributions. Retrying that job reuses the exact saved files and commit. PyPI downloads those
GitHub Release files; it does not rebuild them.

## Enable PyPI publishing once

PyPI publishing is disabled unless the GitHub repository variable `PYPI_PUBLISH_ENABLED` is `true`.
Until enabled, semantic versioning and GitHub Releases still run. No PyPI API token is required.

In your PyPI account, add a pending Trusted Publisher for a new project, or a publisher on the existing
project's Publishing settings:

- Project: `go-judge-client`
- GitHub owner: `Inzhenerka`
- Repository: `go-judge-client`
- Workflow filename: `ci.yml`
- Environment: leave empty (the workflow does not use a GitHub environment)

Then set `PYPI_PUBLISH_ENABLED=true` under GitHub repository Settings → Secrets and variables →
Actions → Variables. The publish job alone receives `id-token: write`; it exchanges GitHub's OIDC
identity for short-lived PyPI authorization. GitHub release jobs use `GITHUB_TOKEN` with `contents: write`.
Repository rules must permit the release bot to push the version commit and tag.

See [PyPI's pending publisher setup](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
and [Python Semantic Release's uv integration](https://python-semantic-release.readthedocs.io/en/latest/configuration/configuration-guides/uv_integration.html).

## Retry or publish an existing version

If PyPI publication fails after the release was created, rerun the failed job. Existing distributions are
skipped, so a partial upload can finish without incrementing the version. Never move an existing release
tag or reuse a PyPI version for changed contents.

To publish a GitHub Release created while PyPI was disabled, enable the publisher and repository variable,
then run the `CI` workflow manually on `main` with `publish_tag` set to that release (for example `v0.1.0`).
This runs the checks and publishes existing release assets without creating a new version. A blank input
runs CI only. If the GitHub asset upload failed, rerun that failed job first while its workflow artifact
is still available. If preparation or artifact storage fails, no commit or tag has been published: rerun the failed jobs.
If publication fails after the atomic Git push, rerun only the failed jobs to resume from the saved
artifact. Do not rerun all jobs: preparation is intentionally skipped once main has advanced.
After artifact expiry, recover the original distributions from a backup or publish a new version;
do not rebuild and overwrite an already published version.

## Local preview

```sh
uvx --from python-semantic-release==10.7.0 semantic-release --noop version
```

This previews the version, changelog and release operations without writing or publishing them.
The actual release still requires successful CI, including native Linux sandbox acceptance.
