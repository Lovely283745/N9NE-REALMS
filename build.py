#!/usr/bin/env python3
"""
build.py — Nine Realms nav-sync build script

Solves the duplication problem: the Lore Navigator (floating button +
slide-out drawer) previously had to be manually copy-pasted into all
31 HTML files every time a page was added or the drawer changed.

Now the ONE source of truth is `_nav-template.html`. This script reads
that file and re-injects it into every page in the directory, replacing
whatever nav block currently exists there (or appending one if missing).

USAGE
    python3 build.py                # apply nav template to all pages
    python3 build.py --check        # dry run — report what WOULD change, no writes
    python3 build.py --validate     # after building, run Node.js syntax check on every script

WORKFLOW GOING FORWARD
    1. Add a new character/page? Write the new .html file as usual.
    2. Add its entry to `_nav-template.html` (one file, one edit).
    3. Run `python3 build.py`.
    4. Every page — old and new — now has the updated nav automatically.
    5. Deploy.

This script is also wired into netlify.toml as the build command, so it
runs automatically on every Netlify deploy — you never have to remember
to run it manually if you push through git.
"""

import os
import re
import sys
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
NAV_TEMPLATE_PATH = os.path.join(ROOT, "_nav-template.html")
NAV_MARKER = "UNIVERSAL NINE REALMS LORE NAVIGATOR"

# Files that should NEVER receive the nav injection (utility/config files,
# and the template itself).
EXCLUDE = {"_nav-template.html", "index.html"}
# index.html is the master sitemap and currently manages its own footer nav;
# remove it from EXCLUDE if you want the drawer injected there too.


def load_template():
    if not os.path.exists(NAV_TEMPLATE_PATH):
        sys.exit(f"ERROR: {NAV_TEMPLATE_PATH} not found. Create it first — "
                  f"it should contain everything from the "
                  f"'<!-- ═══... UNIVERSAL NINE REALMS LORE NAVIGATOR' comment "
                  f"through the final </html> tag.")
    with open(NAV_TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()
    if NAV_MARKER not in template:
        sys.exit(f"ERROR: {NAV_TEMPLATE_PATH} does not contain the nav marker "
                  f"'{NAV_MARKER}'. Refusing to proceed.")
    return template.rstrip("\n") + "\n"


def find_html_pages():
    return sorted(
        f for f in os.listdir(ROOT)
        if f.endswith(".html") and f not in EXCLUDE
    )


def inject_nav(content, template):
    """Replace everything from the nav marker onward with the fresh template.
    If no marker exists yet, append the template just before </body></html>.
    """
    marker_pos = content.find(NAV_MARKER)

    if marker_pos == -1:
        # No existing nav — insert before the final </body>\n</html>
        body_close = content.rfind("</body>")
        if body_close == -1:
            return None  # malformed file, skip
        return content[:body_close] + template + content[body_close:]

    # Walk back to the start of the HTML comment that opens the nav block
    comment_start = content.rfind("<!--", 0, marker_pos)
    if comment_start == -1:
        comment_start = marker_pos  # fallback: cut exactly at marker

    return content[:comment_start] + template


def validate_scripts(path):
    """Extract every <script> block from a file and run `node --check` on it."""
    content = open(path, encoding="utf-8").read()
    scripts = re.findall(r"<script[^>]*>([\s\S]*?)</script>", content)
    for i, script in enumerate(scripts):
        tmp = f"/tmp/_validate_{os.path.basename(path)}_{i}.js"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(script)
        result = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  ✗ SYNTAX ERROR in {path} script #{i}:")
            print("    " + result.stderr.strip().replace("\n", "\n    "))
            return False
    return True


def main():
    check_only = "--check" in sys.argv
    do_validate = "--validate" in sys.argv

    template = load_template()
    pages = find_html_pages()

    if not pages:
        sys.exit("No HTML pages found to process.")

    print(f"Nav template loaded: {len(template):,} chars")
    print(f"Pages found: {len(pages)}")
    print(f"Mode: {'CHECK (dry run)' if check_only else 'APPLY'}\n")

    changed, skipped, failed = [], [], []

    for page in pages:
        path = os.path.join(ROOT, page)
        content = open(path, encoding="utf-8").read()
        new_content = inject_nav(content, template)

        if new_content is None:
            skipped.append(page)
            continue

        if new_content == content:
            continue  # already up to date

        changed.append(page)

        if not check_only:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)

    for page in changed:
        tag = "would update" if check_only else "updated"
        print(f"  ✓ {tag}: {page}")

    for page in skipped:
        print(f"  ⚠ skipped (malformed, no </body> found): {page}")

    print(f"\n{len(changed)} page(s) {'need updating' if check_only else 'updated'}, "
          f"{len(pages) - len(changed) - len(skipped)} already current, "
          f"{len(skipped)} skipped.")

    if do_validate and not check_only:
        print("\nValidating JavaScript syntax on all pages...")
        all_ok = True
        for page in pages:
            if not validate_scripts(os.path.join(ROOT, page)):
                failed.append(page)
                all_ok = False
        if all_ok:
            print(f"  ✓ All {len(pages)} pages pass Node.js syntax validation.")
        else:
            print(f"\n  ✗ {len(failed)} page(s) FAILED validation: {', '.join(failed)}")
            sys.exit(1)


if __name__ == "__main__":
    main()
