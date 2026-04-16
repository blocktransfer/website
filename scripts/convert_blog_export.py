from __future__ import annotations

import html
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "syndicate-blog-posts.xml"
POSTS_DIR = ROOT / "_posts"
DRAFTS_DIR = ROOT / "_drafts"

NS = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "wp": "http://wordpress.org/export/1.2/",
}


def normalize_text(value: str) -> str:
    value = html.unescape(value or "")
    value = value.replace("\xa0", " ")
    value = value.replace("\u200b", "")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def maybe_fix_mojibake(value: str) -> str:
    if not value:
        return value
    replacements = {
        "Â": "",
        "â€”": "—",
        "â€“": "–",
        "â€˜": "‘",
        "â€™": "’",
        "â€œ": '"',
        "â€": '"',
        "â€¦": "…",
        "â€¢": "•",
        "â„¢": "™",
        "âœ¨": "",
        "âŒ›": "",
        "â›”": "",
        "â™¿": "",
        "â³": "",
        "âŒ": "",
        "â¤ï¸": "",
        "â€": "",
        "ðŸ£": "",
        "ðŸ”": "",
        "ðŸ¤”": "",
        "ðŸ‘¥": "",
        "ðŸ‘©": "",
        "ðŸ’¼": "",
        "ðŸ¢": "",
        "ðŸ“†": "",
        "ðŸ“‘": "",
        "ðŸ˜©": "",
        "ðŸ’²": "",
        "ðŸš«": "",
        "ðŸš§": "",
        "ðŸŒŽ": "",
        "ðŸ’”": "",
        "ðŸ¦": "",
        "ðŸ˜•": "",
        "ðŸ•°ï¸": "",
        "ðŸ¤": "",
        "ðŸ”»": "",
        "ðŸ¤·": "",
        "ðŸ›¤ï¸": "",
        "ðŸŒŠ": "",
        "ðŸŒ…": "",
        "ðŸŒ±": "",
        "ðŸ”®": "",
        "ðŸŽ¯": "",
        "ðŸ“ˆ": "",
        "ðŸš€": "",
        "ðŸ¤": "",
        "ðŸ’¡": "",
        "ðŸŽ‰": "",
        "ðŸ˜®": "",
        "ðŸŽ¨": "",
        "ðŸ—£ï¸": "",
        "ðŸ”": "",
        "ðŸƒâ€â™‚ï¸ðŸ": "",
        "ðŸ‘€": "",
    }
    fixed = value
    for source, target in replacements.items():
        fixed = fixed.replace(source, target)
    fixed = re.sub(r"ð[\x80-\xBF][\x80-\xBF][\x80-\xBF]?", "", fixed)
    fixed = re.sub(r"[\x80-\x9F]", "", fixed)
    return fixed


def slugify(value: str) -> str:
    value = normalize_text(value).lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "post"


def yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


@dataclass
class MarkdownBlock:
    kind: str
    lines: list[str]


class HtmlToMarkdown(HTMLParser):
    BLOCK_TAGS = {
        "p",
        "div",
        "section",
        "article",
        "header",
        "footer",
        "aside",
        "figure",
        "figcaption",
        "blockquote",
        "ul",
        "ol",
        "li",
        "pre",
        "table",
        "thead",
        "tbody",
        "tr",
        "td",
        "th",
        "br",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.blocks: list[MarkdownBlock] = []
        self.inline: list[str] = []
        self.href_stack: list[tuple[str | None, str]] = []
        self.list_stack: list[str] = []
        self.ignore_depth = 0
        self.in_pre = False
        self.pre_lines: list[str] = []
        self.anchor_counter = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = dict(attrs)
        if tag in {"style", "script", "svg", "noscript"}:
            self.ignore_depth += 1
            return
        if self.ignore_depth:
            return
        if tag == "br":
            self.flush_inline(force_line_break=True)
            return
        if tag in {"p", "div", "section", "article", "header", "footer", "aside", "figure", "figcaption"}:
            self.flush_inline()
            return
        if tag == "blockquote":
            self.flush_inline()
            self.blocks.append(MarkdownBlock("blockquote_open", []))
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.flush_inline()
            self.blocks.append(MarkdownBlock("heading_open", [tag]))
            return
        if tag in {"ul", "ol"}:
            self.flush_inline()
            self.list_stack.append(tag)
            return
        if tag == "li":
            self.flush_inline()
            depth = max(len(self.list_stack), 1)
            list_type = self.list_stack[-1] if self.list_stack else "ul"
            marker = "-" if list_type == "ul" else "1."
            indent = "  " * (depth - 1)
            self.inline.append(f"{indent}{marker} ")
            return
        if tag == "a":
            marker = f"[[ANCHOR_{self.anchor_counter}]]"
            self.anchor_counter += 1
            self.href_stack.append((attrs_dict.get("href"), marker))
            self.inline.append(marker)
            return
        if tag in {"strong", "b"}:
            self.inline.append("**")
            return
        if tag in {"em", "i"}:
            self.inline.append("*")
            return
        if tag == "code":
            self.inline.append("`")
            return
        if tag == "pre":
            self.flush_inline()
            self.in_pre = True
            self.pre_lines = []
            return
        if tag == "img":
            src = attrs_dict.get("src")
            alt = normalize_text(attrs_dict.get("alt") or attrs_dict.get("data-alt-text") or "")
            if src:
                label = alt or "image"
                self.inline.append(f"![{label}]({src})")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"style", "script", "svg", "noscript"}:
            self.ignore_depth = max(0, self.ignore_depth - 1)
            return
        if self.ignore_depth:
            return
        if tag in {"p", "div", "section", "article", "header", "footer", "aside", "figure", "figcaption"}:
            self.flush_inline()
            return
        if tag == "blockquote":
            self.flush_inline()
            self.blocks.append(MarkdownBlock("blockquote_close", []))
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.flush_inline()
            self.blocks.append(MarkdownBlock("heading_close", []))
            return
        if tag in {"ul", "ol"}:
            self.flush_inline()
            if self.list_stack:
                self.list_stack.pop()
            return
        if tag == "li":
            self.flush_inline()
            return
        if tag == "a":
            href, marker = self.href_stack.pop() if self.href_stack else (None, "")
            if marker and marker in self.inline:
                idx = self.inline.index(marker)
                label = "".join(self.inline[idx + 1 :]).strip()
                replacement = label
                if href and not href.lower().startswith("javascript:"):
                    replacement = f"[{label}]({href})" if label else f"<{href}>"
                self.inline = self.inline[:idx] + [replacement]
            return
        if tag in {"strong", "b"}:
            self.inline.append("**")
            return
        if tag in {"em", "i"}:
            self.inline.append("*")
            return
        if tag == "code":
            self.inline.append("`")
            return
        if tag == "pre":
            content = "\n".join(line.rstrip() for line in self.pre_lines).strip("\n")
            if content:
                self.blocks.append(MarkdownBlock("code", ["```", content, "```"]))
            self.in_pre = False
            self.pre_lines = []

    def handle_data(self, data: str) -> None:
        if self.ignore_depth:
            return
        if self.in_pre:
            self.pre_lines.append(data)
            return
        text = maybe_fix_mojibake(normalize_text(data))
        if not text:
            return
        if self.inline and not self.inline[-1].endswith((" ", "\n", "(", "[", "*", "`")):
            self.inline.append(" ")
        self.inline.append(text)

    def handle_entityref(self, name: str) -> None:
        self.handle_data(html.unescape(f"&{name};"))

    def handle_charref(self, name: str) -> None:
        self.handle_data(html.unescape(f"&#{name};"))

    def flush_inline(self, force_line_break: bool = False) -> None:
        if not self.inline:
            if force_line_break and self.blocks and self.blocks[-1].kind == "text":
                self.blocks[-1].lines.append("")
            return
        text = "".join(self.inline).strip()
        self.inline = []
        if not text and not force_line_break:
            return
        if force_line_break:
            if self.blocks and self.blocks[-1].kind == "text":
                self.blocks[-1].lines.append(text)
            else:
                self.blocks.append(MarkdownBlock("text", [text]))
            return
        self.blocks.append(MarkdownBlock("text", [text]))

    def render(self) -> str:
        self.flush_inline()
        lines: list[str] = []
        blockquote_depth = 0
        heading_level: int | None = None

        for block in self.blocks:
            if block.kind == "blockquote_open":
                blockquote_depth += 1
                continue
            if block.kind == "blockquote_close":
                blockquote_depth = max(0, blockquote_depth - 1)
                lines.append("")
                continue
            if block.kind == "heading_open":
                heading_level = int(block.lines[0][1])
                continue
            if block.kind == "heading_close":
                heading_level = None
                continue

            content_lines = [line for line in block.lines if line is not None]
            if not content_lines:
                continue

            for raw_line in content_lines:
                line = raw_line.strip()
                if not line:
                    lines.append("")
                    continue
                if heading_level is not None:
                    line = f"{'#' * heading_level} {line}"
                if blockquote_depth:
                    prefix = "> " * blockquote_depth
                    line = prefix + line
                lines.append(line)
            lines.append("")

        text = "\n".join(lines)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"(?m)^[ \t]+$", "", text)
        return text.strip() + "\n"


def extract_categories(item: ET.Element) -> tuple[list[str], list[str]]:
    categories: list[str] = []
    tags: list[str] = []
    for category in item.findall("category"):
        domain = category.get("domain", "")
        value = normalize_text("".join(category.itertext()))
        if not value:
            continue
        if domain == "category":
            categories.append(value)
        elif domain == "post_tag":
            tags.append(value)
    return categories, tags


def clean_markdown(text: str) -> str:
    text = maybe_fix_mojibake(normalize_text(text))
    text = re.sub(r"(?m)^\s*Quote\s*$", "", text)
    text = re.sub(r"(?m)^#{1,6}\s+(Subheading|Sub-Sub-Heading|Heading)\b.*$", "", text)
    text = re.sub(r"(?m)^\s*Text\s*$", "", text)
    text = re.sub(r"(?m)^\s*Source #\d+ as needed\s*$", "", text)
    text = re.sub(r"(?ms)\n## Get Notified About New Blog Posts\s+.*$", "", text)
    text = normalize_markdown_spacing(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def normalize_markdown_spacing(text: str) -> str:
    text = collapse_adjacent_links(text)
    protected = protect_markdown_links(text)
    text = protected["text"]

    text = re.sub(r"([.!?])(__LINK_\d+__)", r"\1\n\n\2", text)
    text = re.sub(r"(:)(__LINK_\d+__)", r"\1 \2", text)
    text = re.sub(r"(?<=[A-Za-z0-9\"'])(__LINK_\d+__)", r" \1", text)
    text = re.sub(r"(__LINK_\d+__)(?=__LINK_\d+__)", r"\1 ", text)
    text = re.sub(r"(__LINK_\d+__)(?=[A-Za-z0-9\"'])", r"\1 ", text)
    text = re.sub(r'"(?=\w)', '"', text)
    text = re.sub(r'(?<=[A-Za-z])"(?=[A-Za-z])', ' "', text)
    text = re.sub(r'"\s+([^"\n]+?)\s+"', r'"\1"', text)
    text = re.sub(r"[ \t]+([,;!?])", r"\1", text)
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\$\s+(\d)", r"$\1", text)
    text = text.replace("w ith", "with")
    text = text.replace("u sing", "using")
    text = text.replace("T+1:(##", "T+1 :(\n\n##")
    text = restore_markdown_links(text, protected["links"])
    return text


def collapse_adjacent_links(text: str) -> str:
    pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)\s*\[([^\]]+)\]\(\2\)")
    while True:
        updated = pattern.sub(lambda m: f"[{m.group(1)} {m.group(3)}]({m.group(2)})", text)
        if updated == text:
            return text
        text = updated


def protect_markdown_links(text: str) -> dict[str, object]:
    links: list[str] = []

    def repl(match: re.Match[str]) -> str:
        token = f"__LINK_{len(links)}__"
        links.append(match.group(0))
        return token

    protected = re.sub(r"!?(\[[^\]]*\]\([^)]+\))", repl, text)
    return {"text": protected, "links": links}


def restore_markdown_links(text: str, links: list[str]) -> str:
    for idx, link in enumerate(links):
        text = text.replace(f"__LINK_{idx}__", link)
    return text


def build_front_matter(
    *,
    title: str,
    date: str,
    permalink: str,
    categories: Iterable[str],
    tags: Iterable[str],
    author: str,
    original_url: str,
    status: str,
) -> str:
    lines = [
        "---",
        f"title: {yaml_quote(title)}",
        f"date: {date}",
        "layout: post",
        f"permalink: {yaml_quote(permalink)}",
        f"author: {yaml_quote(author)}",
        f"original_url: {yaml_quote(original_url)}",
        f"status: {yaml_quote(status)}",
    ]
    categories = list(categories)
    tags = list(tags)
    if categories:
        lines.append("categories:")
        lines.extend(f"  - {yaml_quote(value)}" for value in categories)
    if tags:
        lines.append("tags:")
        lines.extend(f"  - {yaml_quote(value)}" for value in tags)
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def convert_item(item: ET.Element) -> tuple[Path, str]:
    title = normalize_text(item.findtext("title") or "Untitled")
    author = normalize_text(item.findtext(f"{{{NS['dc']}}}creator") or "")
    original_url = normalize_text(item.findtext("link") or item.findtext("guid") or "")
    post_date = normalize_text(item.findtext(f"{{{NS['wp']}}}post_date") or "")
    status = normalize_text(item.findtext(f"{{{NS['wp']}}}status") or "draft")
    post_name = normalize_text(item.findtext(f"{{{NS['wp']}}}post_name") or "")
    slug = slugify(post_name or title)
    dt = datetime.strptime(post_date, "%Y-%m-%d %H:%M:%S")
    categories, tags = extract_categories(item)

    parser = HtmlToMarkdown()
    parser.feed(item.findtext(f"{{{NS['content']}}}encoded") or "")
    parser.close()
    body = clean_markdown(parser.render())

    permalink = f"/blog/post/{slug}/"
    front_matter = build_front_matter(
        title=title,
        date=dt.strftime("%Y-%m-%d %H:%M:%S"),
        permalink=permalink,
        categories=categories,
        tags=tags,
        author=author,
        original_url=original_url,
        status=status,
    )

    if status == "publish":
        path = POSTS_DIR / f"{dt.strftime('%Y-%m-%d')}-{slug}.md"
    else:
        path = DRAFTS_DIR / f"{slug}.md"
    return path, front_matter + body


def main() -> None:
    POSTS_DIR.mkdir(exist_ok=True)
    DRAFTS_DIR.mkdir(exist_ok=True)

    tree = ET.parse(SOURCE)
    channel = tree.getroot().find("channel")
    if channel is None:
        raise SystemExit("Missing RSS channel")

    written: list[Path] = []
    for item in channel.findall("item"):
        path, content = convert_item(item)
        path.write_text(content, encoding="utf-8", newline="\n")
        written.append(path)

    print(f"wrote {len(written)} files")
    print(f"published={sum(1 for path in written if path.parent == POSTS_DIR)}")
    print(f"drafts={sum(1 for path in written if path.parent == DRAFTS_DIR)}")


if __name__ == "__main__":
    main()
