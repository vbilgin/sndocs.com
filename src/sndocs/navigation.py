from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from urllib.parse import urlparse

NAV_RE = re.compile(r"^(\s*)- \[([^]]+)]\(([^)]+)\)")


@dataclass
class NavNode:
    title: str
    path: str
    children: list["NavNode"] = field(default_factory=list)

    def mkdocs(self):
        if self.children:
            return {self.title: [self.path, *[child.mkdocs() for child in self.children]]}
        return {self.title: self.path}


def source_path(url: str) -> str | None:
    parsed = urlparse(url)
    marker = "/markdown/"
    if marker not in parsed.path:
        return None
    return parsed.path.split(marker, 1)[1]


def parse_index(text: str) -> list[dict]:
    roots: list[NavNode] = []
    stack: list[tuple[int, NavNode]] = []
    for line in text.splitlines():
        match = NAV_RE.match(line)
        if not match:
            continue
        indent, title, url = match.groups()
        path = source_path(url)
        if path is None or path.endswith("/index.md"):
            continue
        depth = len(indent.expandtabs(2)) // 2
        node = NavNode(title.strip(), str(PurePosixPath(path)))
        while stack and stack[-1][0] >= depth:
            stack.pop()
        if stack:
            stack[-1][1].children.append(node)
        else:
            roots.append(node)
        stack.append((depth, node))
    return [node.mkdocs() for node in roots]

