"""
Job scraper adapter base class.
Add new companies by subclassing this and implementing fetch().
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import os, json, time


@dataclass
class JobPost:
    """Unified job post model, company-agnostic."""
    id: str
    title: str
    department: str = ""
    city: str = ""
    type: str = ""
    description: str = ""
    requirement: str = ""
    extra: str = ""

    def to_text(self) -> str:
        return f"""职位名称: {self.title}
职位ID: {self.id}
部门: {self.department}
城市: {self.city}
招聘类型: {self.type}

职位描述:
{self.description}

职位要求:
{self.requirement}

更多要求:
{self.extra}
"""


class BaseAdapter(ABC):
    """Base class for job site adapters."""

    name: str = "base"
    display_name: str = "Base"

    def __init__(self, output_dir: str, delay: float = 0.5):
        self.output_dir = output_dir
        self.delay = delay
        os.makedirs(output_dir, exist_ok=True)

    @abstractmethod
    def fetch(self, keyword: str, **filters) -> list[JobPost]:
        """Search jobs by keyword, return list of JobPost."""
        ...

    def save(self, posts: list[JobPost]):
        """Save posts to disk, auto-deduplicate."""
        count = 0
        for p in posts:
            safe_title = p.title.replace('/', '_').replace('\\', '_').replace(':', '-')
            fname = f"{self.name}_{p.id}_{safe_title}.txt"
            fpath = os.path.join(self.output_dir, fname)
            if os.path.exists(fpath):
                continue
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(p.to_text())
            count += 1
        return count

    def _rate_limit(self):
        time.sleep(self.delay)
