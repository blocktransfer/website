from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import yaml


ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = ROOT / "_posts"
BLOG_DIR = ROOT / "blog"
POST_OUTPUT_DIR = BLOG_DIR / "post"
CSS_PATH = ROOT / "assets" / "blog.css"


@dataclass
class Post:
    source_path: Path
    title: str
    date: datetime
    permalink: str
    author: str
    original_url: str
    categories: list[str]
    tags: list[str]
    body: str
    excerpt: str

    @property
    def slug(self) -> str:
        return self.permalink.strip("/").split("/")[-1]

    @property
    def canonical_url(self) -> str:
        return f"https://www.blocktransfer.com{self.permalink}"


def maybe_fix_mojibake(value: str) -> str:
    if not value:
        return value

    replacements = {
        "â€”": "—",
        "â€“": "–",
        "â€˜": "'",
        "â€™": "'",
        "â€œ": '"',
        "â€": '"',
        "â€¦": "...",
        "â€¢": "•",
        "â„¢": "™",
        "Â¢": "¢",
        "Â ": " ",
    }

    cleaned = value
    for source, target in replacements.items():
        cleaned = cleaned.replace(source, target)

    cleaned = re.sub(r"ðŸ[\x80-\xBF]{2,}", "", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip()


def read_post(path: Path) -> Post:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise ValueError(f"Missing front matter in {path}")

    _, front_matter, body = raw.split("---", 2)
    data = yaml.safe_load(front_matter) or {}
    cleaned_body = maybe_fix_mojibake(body.lstrip())
    excerpt = build_excerpt(cleaned_body)
    return Post(
        source_path=path,
        title=maybe_fix_mojibake(str(data.get("title", "Untitled"))),
        date=datetime.strptime(str(data["date"]), "%Y-%m-%d %H:%M:%S"),
        permalink=str(data["permalink"]),
        author=maybe_fix_mojibake(str(data.get("author", ""))),
        original_url=str(data.get("original_url", "")),
        categories=[maybe_fix_mojibake(str(item)) for item in data.get("categories", [])],
        tags=[maybe_fix_mojibake(str(item)) for item in data.get("tags", [])],
        body=cleaned_body,
        excerpt=excerpt,
    )


def build_excerpt(markdown_text: str, limit: int = 180) -> str:
    for block in re.split(r"\n\s*\n", markdown_text.strip()):
        if block.strip().startswith("!"):
            continue
        plain = strip_markdown(block)
        if re.fullmatch(r"#+\s+.*", block.strip()):
            continue
        if plain:
            if len(plain) <= limit:
                return plain
            return plain[: limit - 1].rsplit(" ", 1)[0] + "…"
    return "Block Transfer blog post."


def strip_markdown(text: str) -> str:
    text = re.sub(r"^---.*?---\s*", "", text, flags=re.S)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"[*_#>]", "", text)
    text = re.sub(r"\s+", " ", text)
    return maybe_fix_mojibake(text.strip())


def render_inline(text: str) -> str:
    text = maybe_fix_mojibake(text)
    parts: list[str] = []
    i = 0
    while i < len(text):
        if text.startswith("![", i):
            match = re.match(r"!\[(.*?)\]\((.*?)\)", text[i:])
            if match:
                alt, src = match.groups()
                parts.append(
                    f'<img class="post-inline-image" src="{html.escape(src, quote=True)}" alt="{html.escape(alt, quote=True)}">'
                )
                i += match.end()
                continue
        if text.startswith("[", i):
            match = re.match(r"\[(.*?)\]\((.*?)\)", text[i:])
            if match:
                label, href = match.groups()
                parts.append(
                    f'<a href="{html.escape(href, quote=True)}">{render_inline(label)}</a>'
                )
                i += match.end()
                continue
        if text.startswith("**", i):
            end = text.find("**", i + 2)
            if end != -1:
                parts.append(f"<strong>{render_inline(text[i + 2:end])}</strong>")
                i = end + 2
                continue
        if text.startswith("*", i):
            end = text.find("*", i + 1)
            if end != -1:
                parts.append(f"<em>{render_inline(text[i + 1:end])}</em>")
                i = end + 1
                continue
        if text.startswith("`", i):
            end = text.find("`", i + 1)
            if end != -1:
                parts.append(f"<code>{html.escape(text[i + 1:end])}</code>")
                i = end + 1
                continue

        parts.append(html.escape(text[i]))
        i += 1

    return "".join(parts)


def render_figure(line: str) -> str | None:
    linked_image = re.match(r'^\[!\[(.*?)\]\((.*?)\)\]\((.*?)\)\s*$', line)
    if linked_image:
        alt, src, href = linked_image.groups()
        img = (
            f'<img src="{html.escape(src, quote=True)}" alt="{html.escape(alt, quote=True)}">'
        )
        return (
            '<figure class="post-figure">'
            f'<a href="{html.escape(href, quote=True)}">{img}</a>'
            "</figure>"
        )

    image = re.match(r'^!\[(.*?)\]\((.*?)\)\s*$', line)
    if image:
        alt, src = image.groups()
        return (
            '<figure class="post-figure">'
            f'<img src="{html.escape(src, quote=True)}" alt="{html.escape(alt, quote=True)}">'
            "</figure>"
        )

    return None


def render_markdown(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    blocks: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped:
            i += 1
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{render_inline(heading.group(2).strip())}</h{level}>")
            i += 1
            continue

        figure = render_figure(stripped)
        if figure:
            blocks.append(figure)
            i += 1
            continue

        if stripped.startswith(">"):
            quote_lines: list[str] = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_lines.append(lines[i].strip()[1:].strip())
                i += 1
            quote_html = "<br>".join(render_inline(part) for part in quote_lines if part)
            blocks.append(f"<blockquote>{quote_html}</blockquote>")
            continue

        unordered_match = re.match(r"^- (.*)$", stripped)
        ordered_match = re.match(r"^\d+\. (.*)$", stripped)
        if unordered_match or ordered_match:
            items: list[str] = []
            tag = "ul" if unordered_match else "ol"
            pattern = r"^- (.*)$" if tag == "ul" else r"^\d+\. (.*)$"
            while i < len(lines):
                current = lines[i].strip()
                match = re.match(pattern, current)
                if not match:
                    break
                items.append(f"<li>{render_inline(match.group(1).strip())}</li>")
                i += 1
            blocks.append(f"<{tag}>" + "".join(items) + f"</{tag}>")
            continue

        paragraph_lines = [stripped]
        i += 1
        while i < len(lines):
            candidate = lines[i].strip()
            if not candidate:
                break
            if re.match(r"^(#{1,6})\s+", candidate):
                break
            if candidate.startswith(">"):
                break
            if re.match(r"^(- |\d+\. )", candidate):
                break
            if render_figure(candidate):
                break
            paragraph_lines.append(candidate)
            i += 1
        paragraph = " ".join(paragraph_lines)
        blocks.append(f"<p>{render_inline(paragraph)}</p>")

    return "\n".join(blocks)


def render_tag_list(values: Iterable[str], label: str) -> str:
    items = [value for value in values if value]
    if not items:
        return ""
    chips = "".join(f"<li>{html.escape(value)}</li>" for value in items)
    return (
        '<section class="post-meta-group">'
        f"<h2>{html.escape(label)}</h2>"
        f"<ul class=\"chip-list\">{chips}</ul>"
        "</section>"
    )


def page_shell(*, title: str, description: str, canonical_url: str, body_html: str) -> str:
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{html.escape(title)} | Block Transfer</title>
    <meta name="description" content="{html.escape(description, quote=True)}">
    <link rel="canonical" href="{html.escape(canonical_url, quote=True)}">
    <link rel="stylesheet" href="/assets/blog.css">
  </head>
  <body>
    {body_html}
  </body>
</html>
"""


def render_post_page(post: Post) -> str:
    date_text = post.date.strftime("%B %d, %Y")
    article_html = render_markdown(post.body)
    meta_html = (
        '<main class="page-shell">'
        '<header class="site-header">'
        '<a class="brand" href="/">Block Transfer</a>'
        '<nav class="site-nav">'
        '<a href="/blog/">All Posts</a>'
        '<a href="/compliance/user/privacy-policy.html">Privacy</a>'
        "</nav>"
        "</header>"
        '<article class="post-card">'
        '<p class="eyebrow">Published Post</p>'
        f"<h1>{html.escape(post.title)}</h1>"
        '<div class="post-meta">'
        f"<span>{html.escape(date_text)}</span>"
        f"<span>{html.escape(post.author)}</span>"
        "</div>"
        f'<p class="post-excerpt">{html.escape(post.excerpt)}</p>'
        f"{article_html}"
        '<section class="post-meta-grid">'
        f'{render_tag_list(post.categories, "Categories")}'
        f'{render_tag_list(post.tags, "Tags")}'
        "</section>"
        "</article>"
        '<footer class="site-footer">'
        '<a href="/blog/">Back to blog</a>'
        '<span>Direct, investor-first securities infrastructure.</span>'
        "</footer>"
        "</main>"
    )
    return page_shell(
        title=post.title,
        description=post.excerpt,
        canonical_url=post.canonical_url,
        body_html=meta_html,
    )


def render_blog_index(posts: list[Post]) -> str:
    cards = []
    for post in posts:
        cards.append(
            '<article class="post-listing">'
            f'<p class="listing-date">{html.escape(post.date.strftime("%B %d, %Y"))}</p>'
            f'<h2><a href="{html.escape(post.permalink, quote=True)}">{html.escape(post.title)}</a></h2>'
            f'<p>{html.escape(post.excerpt)}</p>'
            f'<a class="read-more" href="{html.escape(post.permalink, quote=True)}">Read post</a>'
            "</article>"
        )

    body_html = (
        '<main class="page-shell">'
        '<header class="site-header">'
        '<a class="brand" href="/">Block Transfer</a>'
        '<nav class="site-nav">'
        '<a href="/">Home</a>'
        '<a href="/compliance/user/privacy-policy.html">Privacy</a>'
        "</nav>"
        "</header>"
        '<section class="blog-hero">'
        "<p class=\"eyebrow\">Blog</p>"
        "<h1>Published perspectives from Block Transfer</h1>"
        "<p>Static pages generated from the published posts in this repository.</p>"
        "</section>"
        '<section class="post-list">'
        f'{"".join(cards)}'
        "</section>"
        "</main>"
    )
    return page_shell(
        title="Blog",
        description="Published perspectives from Block Transfer.",
        canonical_url="https://www.blocktransfer.com/blog/",
        body_html=body_html,
    )


def render_redirect_page(target_path: str) -> str:
    escaped_target = html.escape(target_path, quote=True)
    canonical_target = html.escape(f"https://www.blocktransfer.com{target_path}", quote=True)
    body_html = (
        '<main class="redirect-shell">'
        "<h1>Redirecting...</h1>"
        f'<p>This post moved to <a href="{escaped_target}">{escaped_target}</a>.</p>'
        "</main>"
        f'<script>location.replace("{escaped_target}");</script>'
    )
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="0; url={escaped_target}">
    <link rel="canonical" href="{canonical_target}">
    <title>Redirecting...</title>
    <link rel="stylesheet" href="/assets/blog.css">
  </head>
  <body>
    {body_html}
  </body>
</html>
"""


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, content: str) -> None:
    ensure_parent(path)
    path.write_text(content, encoding="utf-8", newline="\n")


def generate() -> None:
    posts = sorted((read_post(path) for path in POSTS_DIR.glob("*.md")), key=lambda post: post.date, reverse=True)

    for post in posts:
        post_path = ROOT / post.permalink.strip("/") / "index.html"
        write_text(post_path, render_post_page(post))

        if post.original_url:
            original_path = re.sub(r"^https?://[^/]+", "", post.original_url).rstrip("/")
            if original_path and original_path != post.permalink.rstrip("/"):
                redirect_path = ROOT / original_path.strip("/") / "index.html"
                write_text(redirect_path, render_redirect_page(post.permalink))

    write_text(BLOG_DIR / "index.html", render_blog_index(posts))

    print(f"generated_posts={len(posts)}")


if __name__ == "__main__":
    generate()
