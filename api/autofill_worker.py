"""Run apply.py's auto-fill in its own process (Playwright's sync API cannot share the server's event loop).

    python -m api.autofill_worker <job_url> [<cv_path>] [<cover_letter_path>]

Prints one line "AUTOFILL_RESULT {json}" after the first pass (Apply clicked, fields
filled), then keeps filling fields that appear later until the user closes the browser.
"""
import json
import sys

RESULT_PREFIX = "AUTOFILL_RESULT "


def main(argv):
    from apply import auto_fill_job_application

    url = argv[0]
    docx = argv[1] if len(argv) > 1 and argv[1] else None
    letter = argv[2] if len(argv) > 2 and argv[2] else None

    def report(result):
        print(RESULT_PREFIX + json.dumps(result), flush=True)

    auto_fill_job_application(url, docx, headless=False, report=True, on_filled=report, wait_for_close=True,
                              cover_letter_path=letter)


if __name__ == "__main__":
    main(sys.argv[1:])
