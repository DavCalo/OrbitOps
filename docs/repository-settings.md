# Recommended GitHub repository settings

These settings cannot be enforced by files alone and should be configured in the GitHub UI.

## General

- Add topics: `cubesat`, `telemetry`, `ground-station`, `cpp`, `python`, `simulation`.
- Keep Issues enabled.
- Enable Discussions only when you are ready to answer usage and design questions.
- Use squash merge as the default merge strategy and disable merge commits for a linear history.
- Configure squash commit titles from the pull-request title and commit bodies from the
  pull-request body.
- Automatically delete head branches after pull requests are merged.

## Main-branch ruleset

Create a ruleset targeting `main`:

- block force pushes and branch deletion;
- require pull requests before merging;
- require the CI checks from `.github/workflows/ci.yml`;
- require conversations to be resolved;
- require the branch to be up to date before merging;
- require linear history;
- restrict bypass permissions to genuine recovery scenarios;
- optionally require signed commits once your local signing setup is reliable.

For a single-maintainer portfolio repository, one approving review can be optional. The
important controls are green checks, resolved conversations, no force pushes, and a reviewed head
commit that cannot change silently before merge. Periodically audit the live GitHub settings
because this document records policy but cannot enforce UI configuration.

## Security

Enable where available:

- private vulnerability reporting;
- Dependabot alerts and security updates;
- secret scanning;
- push protection;
- CodeQL default setup for C++ and Python.

Review generated Dependabot pull requests rather than auto-merging them without CI.

## Releases

- Create releases from signed `vMAJOR.MINOR.PATCH` tags.
- Mark pre-1.0 releases as pre-releases when APIs are still intentionally unstable.
- Include changelog notes and known limitations.
- Do not attach unverified binaries; publish checksums for manually built artifacts.
