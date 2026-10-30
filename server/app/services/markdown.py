"""Render myScheme's Slate trees without losing Indic text or table structure."""
from html import unescape


def to_markdown(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return unescape(value)
    if isinstance(value, list):
        return "".join(to_markdown(node) for node in value)
    if not isinstance(value, dict):
        return ""
    if "text" in value:
        text = unescape(value["text"])
        for key, mark in (("code", "`"), ("bold", "**"), ("italic", "*"), ("strikethrough", "~~")):
            if value.get(key) and text.strip():
                text = f"{mark}{text}{mark}"
        return text
    kind = value.get("type", "")
    children = value.get("children", [])
    text = to_markdown(children)
    headings = {"heading_one": 1, "heading_two": 2, "heading_three": 3,
                "heading_four": 4, "heading_five": 5, "heading_six": 6}
    if kind in headings:
        return f"{'#' * headings[kind]} {text.strip()}\n\n"
    if kind in ("link", "a"):
        url = value.get("url") or value.get("href") or ""
        return f"[{text}]({url})" if url.startswith(("https://", "http://")) else text
    if kind in ("ul_list", "ol_list", "bulleted-list", "numbered-list"):
        ordered = kind in ("ol_list", "numbered-list")
        lines = []
        for i, child in enumerate(children, 1):
            body = to_markdown(child).strip()
            if body:
                prefix = f"{i}. " if ordered else "- "
                lines.append(prefix + body.replace("\n", "\n" + " " * len(prefix)))
        return "\n".join(lines) + "\n\n"
    if kind in ("table",):
        rows = []
        for row in children:
            cells = [to_markdown(cell).strip().replace("\n", "<br>").replace("|", "\\|")
                     for cell in row.get("children", [])]
            rows.append(cells)
        if not rows:
            return ""
        width = max(map(len, rows))
        rows = [row + [""] * (width - len(row)) for row in rows]
        rows.insert(1, ["---"] * width)
        return "\n".join("| " + " | ".join(row) + " |" for row in rows) + "\n\n"
    if kind in ("blockquote", "block-quote"):
        return "> " + text.strip().replace("\n", "\n> ") + "\n\n"
    if kind in ("paragraph", "list_item", "list-item"):
        return text + "\n\n"
    if kind in ("break", "br"):
        return "\n"
    return text


def field_markdown(data: dict, key: str) -> str:
    """Prefer the publisher's Markdown twin when it is nonempty."""
    return to_markdown(data.get(key + "_md") or data.get(key)).strip()
