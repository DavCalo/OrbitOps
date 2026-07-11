# Security policy

## Supported versions

OrbitOps is currently an early technical preview. Security fixes are applied to the latest commit on the `main` branch and to the latest published release, when releases are available.

| Version | Supported |
|---|---|
| Latest `main` / latest release | Yes |
| Older snapshots | No |

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability.

Use GitHub's private vulnerability reporting flow from the repository **Security** tab. If that flow is unavailable, contact `calo.davide02@gmail.com` with the subject `OrbitOps security report`.

Include, when possible:

- affected commit or version;
- impact and attack scenario;
- reproduction steps or a minimal proof of concept;
- suggested remediation;
- whether public disclosure is already planned.

You should receive an acknowledgement within seven days. Confirmed reports will be tracked privately until a fix and disclosure plan are ready.

## Security scope

OrbitOps is a simulator and portfolio project, not flight software. The current UDP transport is intentionally unauthenticated and unencrypted and defaults to localhost. Do not expose it to an untrusted network or use it for confidential or safety-critical data. See [`docs/threat-model.md`](docs/threat-model.md).
