"""Guard against a Colab/Jupyter footgun in the example notebooks.

An IPython *line* magic (``%cd``, ``%pip``, …) consumes the rest of the line —
including a trailing ``# comment``. So ``%cd climate-toolkit  # note`` tries to
enter a directory literally named ``climate-toolkit  # note`` and fails. This
exact mistake broke the ERA Colab notebook: the clone succeeded but the ``%cd``
did not, leaving the working directory in ``/content`` so every later step
could not find ``lte_final.csv``.

This test keeps inline comments off line magics in every shipped notebook.
"""

import glob
import json
import os
import unittest

EXAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")


class NotebookLineMagicTests(unittest.TestCase):
    def test_line_magics_carry_no_inline_comment(self):
        offenders = []
        for nb_path in sorted(glob.glob(os.path.join(EXAMPLES, "*.ipynb"))):
            nb = json.load(open(nb_path, encoding="utf-8"))
            for i, cell in enumerate(nb.get("cells", [])):
                if cell.get("cell_type") != "code":
                    continue
                for line in cell.get("source", []):
                    s = line.strip()
                    # a single-% line magic (not a %% cell magic); a '#' here is
                    # swallowed as part of the magic's argument, not a comment.
                    if s.startswith("%") and not s.startswith("%%") and "#" in s:
                        offenders.append(f"{os.path.basename(nb_path)} · cell {i}: {s}")
        self.assertEqual(
            offenders, [],
            "line magics must not carry an inline comment (IPython treats it as the "
            "argument) — put the comment on its own line:\n  " + "\n  ".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
