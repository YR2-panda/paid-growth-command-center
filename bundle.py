"""Build every output file for a plan into a folder and return them as a zip (bytes)."""
import io
import os
import tempfile
import zipfile

from builder.generate import build_google, build_meta
from builder.report import write_summary
from builder.validate import validate


def build_zip(plan, extra_files=None):
    errors, warnings, summary = validate(plan)
    if errors:
        raise ValueError("Plan has validation errors; nothing generated.")
    with tempfile.TemporaryDirectory() as d:
        paths = [build_meta(plan, d)[0]]
        g, _, pmax = build_google(plan, d)
        paths += [g, pmax, write_summary(plan, errors, warnings, summary, d)]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in paths:
                if os.path.exists(p):
                    z.write(p, os.path.basename(p))
            for name, text in (extra_files or {}).items():
                z.writestr(name, text)
        files = {os.path.basename(p): open(p, "rb").read() for p in paths if os.path.exists(p)}
    return buf.getvalue(), files
