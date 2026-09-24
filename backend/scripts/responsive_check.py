"""Does the page fit the screen it is on?

    python scripts/responsive_check.py --url http://127.0.0.1:8030

Walks a set of real device widths and reports, per width:

    horizontal overflow   the page scrolling sideways at all, and what causes it
    clipped controls      anything whose box extends past the viewport
    tap targets           controls under 40px, which are hard to hit with a thumb
    text                  anything under 11px, which is hard to read on a phone

Measured in a browser rather than read out of the stylesheet, because a media
query that looks right and an element that fits are different claims.
"""

from __future__ import annotations

import argparse
import sys

from playwright.sync_api import sync_playwright

# A phone in a case, the common Android, the common iPhone, a large phone, a
# tablet in both orientations, a small laptop, and a desktop.
WIDTHS = [(320, 640, "small phone"), (360, 780, "android"), (390, 844, "iphone"),
          (414, 896, "large phone"), (768, 1024, "tablet portrait"),
          (1024, 768, "tablet landscape"), (1280, 800, "laptop"),
          (1440, 900, "desktop")]

PROBE = """(() => {
  const doc = document.documentElement;
  const over = doc.scrollWidth - doc.clientWidth;
  const wide = [];
  const small = [];
  const tiny = [];
  for (const el of document.querySelectorAll('body *')) {
    if (!el.offsetParent && el.tagName !== 'BODY') continue;
    const b = el.getBoundingClientRect();
    if (b.width === 0 || b.height === 0) continue;
    // An element whose box runs past the edge but which sits inside a
    // clipping ancestor is not visible past the edge. The decorative orbits
    // behind the home illustration are exactly this, and reporting them
    // sends somebody looking for a bug that the stylesheet already handles.
    let clipped = false;
    for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
      const o = getComputedStyle(a);
      if (o.overflow !== 'visible' && o.overflowX !== 'visible') { clipped = true; break; }
    }
    if (!clipped && (b.right > doc.clientWidth + 1 || b.left < -1)) {
      wide.push((el.id ? '#' + el.id : el.tagName.toLowerCase() + '.' +
                String(el.className).split(' ')[0]) +
                ' [' + Math.round(b.left) + '..' + Math.round(b.right) + ']');
    }
    const tappable = el.matches('button, a[href], select, input, textarea');
    if (tappable && b.height < 40 && b.height > 0) {
      small.push((el.id ? '#' + el.id : el.tagName.toLowerCase()) + ' h=' + Math.round(b.height));
    }
    if (el.children.length === 0 && el.textContent.trim()) {
      const size = parseFloat(getComputedStyle(el).fontSize);
      if (size && size < 11) tiny.push((el.id ? '#' + el.id : el.tagName.toLowerCase()) + ' ' + size + 'px');
    }
  }
  return {over, wide: [...new Set(wide)].slice(0, 6),
          small: [...new Set(small)].slice(0, 6), tiny: [...new Set(tiny)].slice(0, 5)};
})()"""


def walk(page, url, label, results):
    for width, height, name in WIDTHS:
        page.set_viewport_size({"width": width, "height": height})
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(900)
        found = page.evaluate(PROBE)
        ok = found["over"] <= 1 and not found["wide"]
        results.append((label, name, width, ok, found))
        flag = "ok  " if ok else "WIDE"
        print(f"  {flag} {name:17s} {width:4d}px  overflow={found['over']:4d}px")
        for item in found["wide"]:
            print(f"         past the edge: {item}")
        if found["small"]:
            print(f"         small taps   : {', '.join(found['small'][:3])}")
        if found["tiny"]:
            print(f"         tiny text    : {', '.join(found['tiny'][:3])}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8030")
    args = parser.parse_args()

    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_context().new_page()
        print("\nHOME")
        walk(page, args.url + "/#home", "home", results)
        print("\nCREATE (the interview)")
        walk(page, args.url + "/#create", "create", results)
        browser.close()

    bad = [r for r in results if not r[3]]
    print(f"\n{len(results) - len(bad)}/{len(results)} widths fit the screen")
    if bad:
        print("\nWIDTHS THAT OVERFLOW:")
        for label, name, width, _, found in bad:
            print(f"  {label} @ {width}px ({name}): {found['over']}px — {found['wide'][:3]}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
