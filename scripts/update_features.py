"""Keep features.csv and the README feature table in sync with merged pull requests.

Run automatically by .github/workflows/features.yml whenever a pull request is merged into
main: the row whose branch matches the pull request is marked Done; a branch that is not
listed yet gets a new row (except `chore/` housekeeping branches). The README table between the FEATURES markers is regenerated
from the CSV every time.

Usage:
  python scripts/update_features.py --branch feature/x --pr 12 --title "Title" --author user --merged-on 2026-09-29
  python scripts/update_features.py --render-only
"""
import argparse
import csv
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "features.csv"
README = ROOT / "README.md"
COLUMNS = ["id", "feature", "area", "owner", "branch", "status", "pull_request", "merged_on"]
STATUSES = ["Done", "In progress", "Planned", "Finale"]
BADGE = {"Done": "✅ Done", "In progress": "🔄 In progress", "Planned": "⏳ Planned", "Finale": "🏁 Finale"}
START, END = "<!-- FEATURES:START -->", "<!-- FEATURES:END -->"
REPO = os.environ.get("GITHUB_REPOSITORY", "abhay-hanchate/GridTwin")


def read_rows() -> list[dict]:
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_rows(rows: list[dict]) -> None:
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def mark_done(rows: list[dict], branch: str, pr: str, title: str, author: str, merged_on: str) -> dict | None:
    """Mark every feature built on `branch` done, adding a row if the branch is new.

    `chore/` branches are housekeeping (tracker or tooling upkeep), not features: no row is touched.
    """
    if branch.startswith("chore/"):
        return None
    matched = []
    for row in rows:
        if row["branch"] == branch:
            row.update(status="Done", pull_request=pr, merged_on=merged_on)
            matched.append(row)
    if matched:
        return matched[0]
    next_id = max(int(r["id"][1:]) for r in rows) + 1
    row = {"id": f"F{next_id:02d}", "feature": title.replace(",", " "), "area": "", "owner": author,
           "branch": branch, "status": "Done", "pull_request": pr, "merged_on": merged_on}
    rows.append(row)
    return row


def render_table(rows: list[dict]) -> str:
    done = sum(r["status"] == "Done" for r in rows)
    lines = [
        f"**{done} of {len(rows)} features done.** Updated automatically when a pull request is merged; "
        "source: [features.csv](features.csv).",
        "",
        "| ID | Feature | Area | Owner | Status | Pull request |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        pr = f"[#{r['pull_request']}](https://github.com/{REPO}/pull/{r['pull_request']})" if r["pull_request"] else ""
        lines.append(f"| {r['id']} | {r['feature']} | {r['area']} | {r['owner']} | {BADGE.get(r['status'], r['status'])} | {pr} |")
    return "\n".join(lines)


def update_readme(rows: list[dict]) -> None:
    text = README.read_text(encoding="utf-8")
    block = f"{START}\n{render_table(rows)}\n{END}"
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pattern.search(text):
        raise SystemExit(f"README.md is missing the {START} / {END} markers")
    README.write_text(pattern.sub(lambda _: block, text), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--branch")
    p.add_argument("--pr", default="")
    p.add_argument("--title", default="")
    p.add_argument("--author", default="")
    p.add_argument("--merged-on", default="")
    p.add_argument("--render-only", action="store_true")
    args = p.parse_args()

    rows = read_rows()
    if not args.render_only:
        if not args.branch:
            p.error("--branch is required unless --render-only")
        row = mark_done(rows, args.branch, args.pr, args.title, args.author, args.merged_on)
        write_rows(rows)
        print(f"{row['id']} {row['feature']}: Done (#{args.pr})" if row else f"{args.branch}: housekeeping, no feature row")
    update_readme(rows)


if __name__ == "__main__":
    main()
