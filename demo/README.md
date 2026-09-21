# Jevy Graph demo

Start the local compiler server from the repository root:

```bash
PYTHONPATH=src python3 -m jevy_graph.demo_server
```

Then open <http://localhost:8080/demo/>.

Uploads run through the real extraction and Jev verification pipeline. PDF,
DOCX, and UTF-8 text-like files are supported. The API key stays in the
server-side `.env` file and is never sent to the browser.
