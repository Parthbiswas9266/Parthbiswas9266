import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API = "https://api.github.com"
TOKEN = os.environ["TRAFFIC_TOKEN"]
PROFILE_REPO = os.environ["GITHUB_REPOSITORY"]
OWNER = PROFILE_REPO.split("/", 1)[0]
START = "<!-- TRAFFIC-DASHBOARD:START -->"
END = "<!-- TRAFFIC-DASHBOARD:END -->"



def api_get(path):
    request = urllib.request.Request(
        API + path,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {TOKEN}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "github-profile-traffic-dashboard",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def get_owned_public_repos():
    repos = []
    page = 1

    while True:
        path = (
            f"/users/{OWNER}/repos?type=owner"
            f"&per_page=100&page={page}&sort=updated"
        )

        batch = api_get(path)

        repos.extend(
            repo for repo in batch
            if repo.get("owner", {}).get("login", "").lower()
            == OWNER.lower()
            and repo.get("visibility") == "public"
            and not repo.get("fork", False)
        )

        if len(batch) < 100:
            break

        page += 1

    return repos


def traffic(repo, kind):
    full_name = urllib.parse.quote(repo, safe="/")
    try:
        return api_get(f"/repos/{full_name}/traffic/{kind}")
    except urllib.error.HTTPError as exc:
        # A repository may have traffic unavailable or the token may lack access.
        if exc.code in (403, 404):
            print(f"Skipping {repo} traffic/{kind}: HTTP {exc.code}")
            return {"count": 0, "uniques": 0, "unavailable": True}
        raise


def fmt(n):
    return f"{n:,}"


def main():
    repos = get_owned_public_repos()
    rows = []
    totals = {"clones": 0, "clone_uniques": 0, "views": 0, "view_uniques": 0}
    unavailable = 0

    for repo in sorted(repos, key=lambda r: r["name"].lower()):
        name = repo["name"]
        clone_data = traffic(repo["full_name"], "clones")
        view_data = traffic(repo["full_name"], "views")
        if clone_data.get("unavailable") or view_data.get("unavailable"):
            unavailable += 1
        clones = clone_data.get("count", 0)
        clone_uniques = clone_data.get("uniques", 0)
        views = view_data.get("count", 0)
        view_uniques = view_data.get("uniques", 0)
        totals["clones"] += clones
        totals["clone_uniques"] += clone_uniques
        totals["views"] += views
        totals["view_uniques"] += view_uniques
        rows.append((name, repo["html_url"], clones, clone_uniques, views, view_uniques))

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d UTC")
    lines = [
        f"**Last updated:** {today}  ",
        "**Window:** rolling 14 days  ",
        "",
        "| Public repository | Clone events | Unique cloners | Views | Unique visitors |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, url, clones, clone_uniques, views, view_uniques in rows:
        lines.append(
            f"| [{name}]({url}) | {fmt(clones)} | {fmt(clone_uniques)} | "
            f"{fmt(views)} | {fmt(view_uniques)} |"
        )
    lines.extend([
        "",
        f"**Totals:** {fmt(totals['clones'])} clone events · "
        f"{fmt(totals['clone_uniques'])} summed unique cloners · "
        f"{fmt(totals['views'])} views · "
        f"{fmt(totals['view_uniques'])} summed unique visitors.",
        "",
        "_Unique counts are added across repositories. The same person may appear in more than one repository's count, so these totals are not profile-wide unique people._",
    ])
    if unavailable:
        lines.extend([
            "",
            f"_Note: traffic data was unavailable for {unavailable} repository/repositories; those entries may show zero and should not be interpreted as confirmed zero traffic._",
        ])
    section = "\n".join(lines)

    readme_path = "README.md"
    with open(readme_path, "r", encoding="utf-8") as f:
        readme = f.read()

    if START not in readme or END not in readme:
        raise SystemExit(
            "README.md is missing the dashboard markers. Keep both "
            f"{START} and {END} in README.md."
        )
    before, remainder = readme.split(START, 1)
    _, after = remainder.split(END, 1)
    updated = before + START + "\n" + section + "\n" + END + after
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(updated)
    print(f"Updated traffic dashboard for {len(rows)} owned public repositories.")


if __name__ == "__main__":
    main()
