#!/usr/bin/env python3
"""公開リポジトリの言語構成を集計し、横棒グラフ SVG を生成する。

GitHub Linguist のバイト数を言語ごとに合算する。.gitattributes で
linguist-documentation / vendored / generated が指定されたファイルは
API 側で既に除外済みのため、ここでの追加処理は不要。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

USER = os.environ.get("METRICS_USER", "jtf10061-bit")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT = os.environ.get("METRICS_OUT", "languages.svg")

THRESHOLD = 1.0   # これ未満(%)は「Other」へ集約
MAX_ROWS = 8

# GitHub Linguist の言語カラー
COLORS = {
    "TypeScript": "#3178c6", "Python": "#3572A5", "JavaScript": "#f1e05a",
    "CSS": "#663399", "HTML": "#e34c26", "Vue": "#41b883", "Shell": "#89e051",
    "Go": "#00ADD8", "Rust": "#dea584", "Java": "#b07219", "Ruby": "#701516",
    "PHP": "#4F5D95", "C": "#555555", "C++": "#f34b7d", "C#": "#178600",
    "Kotlin": "#A97BFF", "Swift": "#F05138", "Dockerfile": "#384d54",
    "SCSS": "#c6538c", "Makefile": "#427819", "Jupyter Notebook": "#DA5B0B",
}
OTHER_COLOR = "#8b949e"


def api(url):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "language-stats-generator",
        **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
    })
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            # 403/429 はレート制限。指数バックオフで待って再試行する。
            if e.code in (403, 429) and attempt < 2:
                wait = 5 * (2 ** attempt)
                print(f"  rate limited, retry in {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            raise
        except urllib.error.URLError:
            if attempt < 2:
                time.sleep(3)
                continue
            raise


def collect():
    """全公開リポジトリの言語バイト数を合算する。fork/archive は除外。"""
    totals, page = {}, 1
    while True:
        repos = api(f"https://api.github.com/users/{USER}/repos"
                    f"?per_page=100&page={page}&type=owner")
        if not repos:
            break
        for repo in repos:
            if repo.get("fork") or repo.get("archived"):
                continue
            try:
                langs = api(repo["languages_url"])
            except urllib.error.HTTPError as e:
                print(f"  skip {repo['name']}: {e}", file=sys.stderr)
                continue
            for lang, size in langs.items():
                totals[lang] = totals.get(lang, 0) + size
        if len(repos) < 100:
            break
        page += 1
    return totals


def rank(totals):
    """しきい値未満を Other へ集約し、降順に整列する。"""
    grand = sum(totals.values())
    if not grand:
        return []
    ordered = sorted(totals.items(), key=lambda kv: -kv[1])
    rows, other = [], 0
    for lang, size in ordered:
        pct = 100 * size / grand
        if pct < THRESHOLD or len(rows) >= MAX_ROWS:
            other += size
        else:
            rows.append((lang, size, pct))
    # Other 自身がしきい値未満なら表示しない（1%未満を隠す趣旨と一貫させる）
    if other and 100 * other / grand >= THRESHOLD:
        rows.append(("Other", other, 100 * other / grand))
    return rows


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def render(rows):
    """各言語を1行で描画する。棒の幅と数値ラベルを併記し、僅差でも判別可能にする。"""
    PAD, LABEL_W, BAR_W, ROW_H, BAR_H = 20, 118, 300, 30, 10
    PCT_W, HEAD = 58, 46
    width = PAD * 2 + LABEL_W + BAR_W + PCT_W
    height = HEAD + len(rows) * ROW_H + PAD

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="Most used languages">',
        "<style>",
        # currentColor 追従でライト/ダーク両対応
        "  .bg{fill:none}",
        "  .title{font:600 15px -apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;fill:#57606a}",
        "  .lang{font:500 13px -apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;fill:#24292f}",
        "  .pct{font:500 13px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;fill:#57606a}",
        "  .track{fill:#eaeef2}",
        "  @media (prefers-color-scheme:dark){",
        "    .title{fill:#8b949e}.lang{fill:#e6edf3}.pct{fill:#8b949e}.track{fill:#21262d}",
        "  }",
        "</style>",
        f'<rect class="bg" width="{width}" height="{height}"/>',
        f'<text class="title" x="{PAD}" y="26">Most used languages</text>',
    ]

    for i, (lang, _size, pct) in enumerate(rows):
        y = HEAD + i * ROW_H
        by = y + (ROW_H - BAR_H) / 2 - 4
        color = COLORS.get(lang, OTHER_COLOR)
        fill_w = max(2.0, BAR_W * pct / 100)
        out += [
            f'<text class="lang" x="{PAD}" y="{y + 12}">{esc(lang)}</text>',
            f'<rect class="track" x="{PAD + LABEL_W}" y="{by}" '
            f'width="{BAR_W}" height="{BAR_H}" rx="5"/>',
            f'<rect x="{PAD + LABEL_W}" y="{by}" width="{fill_w:.2f}" '
            f'height="{BAR_H}" rx="5" fill="{color}"/>',
            f'<text class="pct" x="{PAD + LABEL_W + BAR_W + 10}" '
            f'y="{y + 12}">{pct:.1f}%</text>',
        ]

    out.append("</svg>")
    return "\n".join(out) + "\n"


def main():
    rows = rank(collect())
    if not rows:
        print("no language data found", file=sys.stderr)
        return 1
    # 一時ファイルに書いてから置換する。生成途中で失敗しても
    # 既存の SVG を壊さない。
    svg = render(rows)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(svg)
    os.replace(tmp, OUT)
    for lang, size, pct in rows:
        print(f"{lang:<14}{size:>10,} B  {pct:5.1f}%")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
