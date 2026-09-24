"""A timestamped record of every decision MOPU makes during a Fetch Repo / Analyze /
Confirm Update run -- not something the user has to ask for, since the whole point is
to have it ready to attach to a support request without the user needing to reproduce
anything or know what to look for. Written out automatically to a "MOPU" subfolder of the output folder, as
"mopu-error-log-<date>_<time>.txt" (the timestamp is fixed once per app launch, in
gui.py, not regenerated on every write) -- overwritten as this run progresses so it's
there even if something fails partway through, but a later run never overwrites it,
since each launch gets its own timestamped file.

This is deliberately a *separate* file from the Added/Removed/Renamed/etc. summary the
Review and Done screens show -- that one explains WHAT changed, in plain terms, for the
user to review before confirming. This one explains HOW MOPU got there and WHERE it
looked, in enough procedural detail (with timestamps) for troubleshooting when something
looks wrong or a step failed outright."""

import time


class DiagnosticLog:
    def __init__(self):
        self.lines = []
        self.had_error = False

    def _stamp(self):
        return time.strftime("%H:%M:%S")

    def info(self, message):
        self.lines.append(f"[{self._stamp()}] {message}")

    def error(self, message):
        self.had_error = True
        # blank line before an error so it's easy to spot when skimming
        self.lines.append("")
        self.lines.append(f"[{self._stamp()}] ERROR: {message}")
        self.lines.append("")

    def render(self):
        header = [
            "MOPU Error Log",
            f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "=" * 70,
            "",
        ]
        footer = ["", "=" * 70, "No errors were recorded during this run." if not self.had_error
                  else "One or more errors were recorded above -- see \"ERROR:\" lines."]
        return "\n".join(header + self.lines + footer) + "\n"
