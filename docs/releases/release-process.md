# Release Process

This checklist is for maintainers preparing a platform release.

## Versioning

Current releases use a single platform tag:

```text
vX.Y.Z
```

Component-specific tags such as `node-agent/vX.Y.Z` are reserved for future independently shipped components.

## Pre-Release Checklist

1. Update `CHANGELOG.md`.
2. Confirm `README.md` and docs match the release behavior.
3. Run validation:

```bash
make validate
make validate-mtls
npm --prefix frontend ci
npm --prefix frontend run build
python3 -m compileall services scripts collector/agent/tools
```

4. Package the Node Agent:

```bash
./scripts/package-node-agent.sh <version>
./scripts/verify-node-agent-release.sh <version>
```

5. Create an annotated release tag:

```bash
git tag -a v<version> -m "Release v<version>"
git push origin v<version>
```

6. Create a GitHub Release for the tag and attach the generated Node Agent artifacts from `releases/<version>/`:

```text
otel-node-agent-<version>.tgz
SHA256SUMS
manifest.json
sbom.json
```

7. Verify the GitHub Release links from the README and Node Agent onboarding documentation.

## Artifact Policy

Generated release archives are release artifacts. Prefer attaching them to GitHub Releases instead of committing large archives to the repository. If a future release commits `releases/<version>/`, update `docs/releases/compatibility.md` and this checklist in the same PR.
