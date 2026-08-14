# 010: Cross-frame reCAPTCHA click misses target using page.mouse + bounding_box

## Symptom
Deterministic fill+submit of the TestedRecruits form (Coalition Technologies) fills every
field and uploads files, but the reCAPTCHA v2 checkbox never toggles. Polling shows
`token_len=0, checked=False` for the full window even though `anchor.count()==1` and
`scroll_into_view_if_needed()` succeed. `checked` stays False forever (no image
challenge served, widget appears "muted").

## Root Cause
`locator.bounding_box()` on a **cross-frame** element (the `#recaptcha-anchor` inside the
`google.com/recaptcha/api2/anchor` iframe) returns coordinates **relative to that iframe**,
not the page. Feeding those into `page.mouse.move/click` dispatches the click at the wrong
page position, so the real checkbox never receives it. reCAPTCHA silently ignores the miss
(it does not error), making the widget look non-interactive.

A second bug: `page.frame_locator(...).count()` does not exist (`FrameLocator` has no
`count`); iterating `page.frames` is required to detect a bframe.

## Repro
1. Run the deterministic fill script against any reCAPTCHA v2 form.
2. Click via `page.mouse` using `bounding_box()` coords from a frame_locator locator.
3. Observe `checked=False` indefinitely despite a successful-looking click.

## Fix
Use `locator.click(timeout=15000)` on the frame locator — Playwright computes the correct
page coordinates for cross-frame elements internally. Keep `bounding_box()` only as a
fallback, never for `page.mouse` targeting of framed elements. Detect frames via
`page.frames` iteration, not `frame_locator().count()`.

## Verification
With the fix, a single `anchor.click()` produced a 1294-char reCAPTCHA token at the first
poll, the submit went through, and the confirmation page loaded:
`https://app.testedrecruits.com/application/complete/1828281` — "Thank you for applying to
join us, syed! ... VERDICT: SUBMITTED OK".

## Affected Files
- C:\Users\win10\AppData\Local\Temp\opencode\fill_submit.py (scratch deterministic
  script; the same pattern must be avoided in any future native-form submit tool)
