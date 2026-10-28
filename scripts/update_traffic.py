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
    total_clones = 0
    total_unique_cloners = 0
    unavailable = 0

    for repo in sorted(repos, key=lambda r: r["name"].lower()):
        name = repo["name"]
        clone_data = traffic(repo["full_name"], "clones")

        if clone_data.get("unavailable"):
            unavailable += 1

        clones = clone_data.get("count", 0)
        unique_cloners = clone_data.get("uniques", 0)

        total_clones += clones
        total_unique_cloners += unique_cloners

        rows.append((
            name, repo["html_url"], clones, unique_cloners
        ))

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d UTC")

    lines = [
        f"**Last updated:** {today}  ",
        "**Window:** rolling 14 days  ",
        "",
        "| Public repository | Clone events | Unique cloners |",
        "|---|---:|---:|",
    ]

    for name, url, clones, unique_cloners in rows:
        lines.append(
            f"| [{name}]({url}) | {clones:,} | {unique_cloners:,} |"
        )

    lines.extend([
        "",
        f"**Totals:** {total_clones:,} clone events · "
        f"{total_unique_cloners:,} summed unique cloners.",
        "",
        "_Unique-cloner counts are summed across repositories. "
        "The same person may appear in multiple repositories' counts._",
    ])

    if unavailable:
        lines.extend([
            "",
            f"_Traffic data was unavailable for {unavailable} "
            "repository/repositories. Treat their zero values as unknown._",
        ])

    section = "\n".join(lines)

    with open("README.md", "r", encoding="utf-8") as f:
        readme = f.read()

    if START not in readme or END not in readme:
        raise SystemExit("README.md is missing the dashboard markers.")

    before, remainder = readme.split(START, 1)
    _, after = remainder.split(END, 1)

    updated = before + START + "\n" + section + "\n" + END + after

    with open("README.md", "w", encoding="utf-8") as f:
        f.write(updated)

    print(f"Updated dashboard for {len(rows)} public repositories.")


if __name__ == "__main__":
    main()
