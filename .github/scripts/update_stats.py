import datetime as dt
import html
import json
import os
from pathlib import Path
import re
import urllib.request
from zoneinfo import ZoneInfo

OWNER = "Hamza-Nasar"

def graphql(query, variables):
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": "Bearer " + os.environ["STATS_TOKEN"],
                 "Content-Type": "application/json", "User-Agent": "profile-stats"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
        scopes = response.headers.get("X-OAuth-Scopes", "")
    if "read:user" not in [s.strip() for s in scopes.split(",")]:
        raise RuntimeError("STATS_TOKEN needs the read:user scope for private contribution totals.")
    if payload.get("errors"):
        raise RuntimeError("GitHub could not return complete contribution data; existing cards retained.")
    return payload["data"]

def streaks(days, today):
    active = sorted(dt.date.fromisoformat(d) for d, n in days.items() if n > 0 and dt.date.fromisoformat(d) <= today)
    longest = run = 0
    previous = None
    for day in active:
        run = run + 1 if previous and day == previous + dt.timedelta(days=1) else 1
        longest = max(longest, run)
        previous = day
    current = 0
    cursor = today if days.get(today.isoformat(), 0) else today - dt.timedelta(days=1)
    while days.get(cursor.isoformat(), 0) > 0:
        current += 1
        cursor -= dt.timedelta(days=1)
    return current, longest

def card(title, rows, subtitle, updated):
    height = 95 + len(rows) * 27
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="500" height="{height}" viewBox="0 0 500 {height}" role="img">',
             '<rect width="500" height="100%" rx="14" fill="#1a1b27"/>',
             '<g font-family="Arial,sans-serif">',
             f'<text x="24" y="32" fill="#70a5fd" font-size="18" font-weight="700">{html.escape(title)}</text>',
             f'<text x="24" y="53" fill="#a9b1d6" font-size="11">{html.escape(subtitle)}</text>']
    for index, (label, value) in enumerate(rows):
        y = 82 + index * 27
        parts += [f'<text x="24" y="{y}" fill="#38bdae" font-size="13">{html.escape(label)}</text>',
                  f'<text x="465" y="{y}" text-anchor="end" fill="#70a5fd" font-size="16" font-weight="700">{value:,}</text>']
    parts += [f'<text x="24" y="{height-14}" fill="#a9b1d6" font-size="10">Updated {html.escape(updated)} | GitHub API</text>', '</g></svg>']
    return "\n".join(parts)

def main():
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    identity = graphql('query { viewer { login createdAt } }', {})["viewer"]
    if identity["login"].lower() != OWNER.lower():
        raise RuntimeError("STATS_TOKEN must belong to the profile owner.")
    first_year = int(identity["createdAt"][:4])
    query = '''query($login:String!, $from:DateTime!, $to:DateTime!) {
      user(login:$login) { contributionsCollection(from:$from,to:$to) {
        totalCommitContributions totalPullRequestContributions totalIssueContributions
        contributionCalendar { weeks { contributionDays { date contributionCount } } }
      } }
    }'''
    totals = {key: 0 for key in ("totalCommitContributions", "totalPullRequestContributions", "totalIssueContributions")}
    days = {}
    for year in range(first_year, now.year + 1):
        start = dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc)
        end = min(dt.datetime(year, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc), now)
        data = graphql(query, {"login": OWNER, "from": start.isoformat(), "to": end.isoformat()})["user"]["contributionsCollection"]
        for key in totals:
            totals[key] += data[key]
        for week in data["contributionCalendar"]["weeks"]:
            for day in week["contributionDays"]:
                days[day["date"]] = day["contributionCount"]
    current, longest = streaks(days, now.astimezone(ZoneInfo("Asia/Karachi")).date())
    updated = now.strftime("%Y-%m-%d %H:%M UTC")
    stats = card("Hamza Nasar's GitHub Stats", [
        ("Commits (all time)", totals["totalCommitContributions"]),
        ("Pull requests (all time)", totals["totalPullRequestContributions"]),
        ("Issues opened (all time)", totals["totalIssueContributions"]),
    ], "Public + private contributions | Since account creation", updated)
    streak = card("GitHub Contribution Streak", [
        ("Total contributions (all time)", sum(days.values())),
        ("Current streak (days)", current),
        ("Longest streak (days)", longest),
    ], "Public + private contributions | Asia/Karachi", updated)
    readme_path = Path("README.md")
    text = readme_path.read_text(encoding="utf-8")
    start = text.index("## 📊 GitHub Analytics")
    end = text.index("## 📈 Contribution Graph", start)
    section = text[start:end]
    section, stats_count = re.subn(r'src="(?:https://github-readme-stats\.vercel\.app/api\?[^\"]*|\./profile/stats\.svg)"', 'src="./profile/stats.svg"', section)
    section, streak_count = re.subn(r'src="(?:https://streak-stats\.demolab\.com/\?[^\"]*|\./profile/streak\.svg)"', 'src="./profile/streak.svg"', section)
    if stats_count != 1 or streak_count != 1:
        raise RuntimeError("Analytics markup changed; refusing to modify other README sections.")
    section = section.replace("Automatically generated from GitHub activity; cached cards may take time to refresh.",
        "Public + private contribution totals from the GitHub API, updated hourly. Counts follow GitHub contribution rules; language statistics cover public repositories.")
    Path("profile").mkdir(exist_ok=True)
    Path("profile/stats.svg").write_text(stats, encoding="utf-8")
    Path("profile/streak.svg").write_text(streak, encoding="utf-8")
    readme_path.write_text(text[:start] + section + text[end:], encoding="utf-8")

if __name__ == "__main__":
    main()
