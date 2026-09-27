# Jevy Graph release checklist

## Verified locally

- [x] 233 core tests pass with one expected skip.
- [x] Five optional scientific-parser tests pass.
- [x] The frozen offline benchmark reaches all 1,267 reviewed claims.
- [x] All 74 substantive Constitution units have exhaustive Codex review.
- [x] Wheel and source distribution build in an isolated environment.
- [x] The installed wheel passes the CLI smoke test and bundles the demo.
- [x] The source distribution excludes benchmarks, tests, scripts, media, and
  generated output.
- [x] The demo exposes `/healthz` and reads `HOST` and `PORT` from the environment.
- [x] The container definition installs Poppler and runs as a network service.
- [x] CI tests Python 3.11 and 3.13 and builds release artifacts.
- [x] The release workflow uses PyPI Trusted Publishing.

The Docker daemon was unavailable during the final local pass. CI or the target
container builder must complete the image build before deployment.

## Release steps

1. Push the prepared commit and confirm both CI matrix jobs pass.
2. Build the container and verify `/healthz` plus one real upload with a server
   `TYPESAFE_API_KEY`.
3. Create the protected GitHub environment `pypi` if it does not exist.
4. Configure PyPI Trusted Publishing for repository `saivivekvenna/jevy-graph`,
   workflow `release.yml`, and environment `pypi`.
5. Create a version tag and publish the matching GitHub release.
6. Install the published wheel in a new environment and run:

   ```bash
   printf 'Alice founded Acme.' | jevy-graph --no-verify
   ```

7. Confirm that the public README benchmark table matches the attached benchmark
   report before announcing the release.
