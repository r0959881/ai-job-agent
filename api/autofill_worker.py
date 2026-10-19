"""Run apply.py's auto-fill in its own process (Playwright's sync API cannot share the server's event loop).

    python -m api.autofill_worker <job_url> [<docx_path>]

Prints one line "AUTOFILL_RESULT {json}" as soon as the fields are filled, then
keeps the visible browser open until the user closes it.
"""
import json
import sys

RESULT_PREFIX = "AUTOFILL_RESULT "


def main(argv):
    from apply import auto_fill_job_application

    url = argv[0]
    docx = argv[1] if len(argv) > 1 and argv[1] else None

    def report(result):
        print(RESULT_PREFIX + json.dumps(result), flush=True)

    auto_fill_job_application(url, docx, headless=False, report=True, on_filled=report, wait_for_close=True)


if __name__ == "__main__":
    main(sys.argv[1:])
