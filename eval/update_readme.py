"""Copies eval/results/latest.md into the README between the BENCHMARK markers.
Run after eval/run_benchmark.py:   python eval/update_readme.py"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
readme = ROOT / "README.md"
latest = (ROOT / "eval" / "results" / "latest.md").read_text().strip()

text = readme.read_text()
pattern = re.compile(r"(<!-- BENCHMARK:START -->).*?(<!-- BENCHMARK:END -->)", re.DOTALL)
assert pattern.search(text), "README is missing the BENCHMARK markers"
readme.write_text(pattern.sub(lambda m: f"{m.group(1)}\n{latest}\n{m.group(2)}", text))
print("README updated from eval/results/latest.md")
