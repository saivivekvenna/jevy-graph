# Jevy Graph v0.1 launch checklist

Nothing in this directory has been posted or sent.

## Ready locally

- [x] Wheel and source distribution build from a clean temporary environment.
- [x] Installed wheel passes all 37 tests and the CLI smoke test.
- [x] Installed `jevy-graph-demo` serves its bundled frontend.
- [x] Source distribution reduced from about 7.9 MB to about 52 KB by excluding
  repository-only demo media.
- [x] 19-second launch clip and thumbnail generated.
- [x] Release notes and a PyPI Trusted Publishing workflow prepared.

## Owner-only steps before launch

1. Review and commit the local changes.
2. Push them to GitHub.
3. On PyPI, create a pending Trusted Publisher for:
   - owner: `saivivekvenna`
   - repository: `jevy-graph`
   - workflow: `release.yml`
   - environment: `pypi`
4. In GitHub, create an environment named `pypi` and require manual approval.
5. Create tag `v0.1.0`, then publish the matching GitHub release. Publishing the
   release will run `.github/workflows/release.yml` and upload to PyPI.
6. Verify from a new environment:

   ```bash
   python -m venv /tmp/jevy-verify
   /tmp/jevy-verify/bin/python -m pip install jevy-graph
   printf 'Alice founded Acme.' | /tmp/jevy-verify/bin/jevy-graph --no-verify
   ```

7. Only after that succeeds, replace the README clone-based install block with
   `python -m pip install jevy-graph`.
8. Add the repository homepage and these GitHub topics:
   `knowledge-graph`, `rdf`, `semantic-web`, `information-extraction`,
   `document-ai`, `nlp`, `python`, `provenance`, `text-to-graph`,
   `neuro-symbolic-ai`, `llm`.

## Do not combine these events

Publish to PyPI before making the GitHub release public if using a manual upload,
or use the release workflow above and wait for it to complete before sharing the
release. Do not announce the release until the public install path has been tested
from a clean machine.
