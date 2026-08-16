from dataclasses import dataclass
from typing import Optional


@dataclass
class Repository:
    platform: str
    org: str
    repo: str
    url: str
    is_archived: bool = False
    is_fork: bool = False
    description: Optional[str] = None
    stars: int = 0

    @classmethod
    def from_url(cls, url: str, is_archived: bool = False, is_fork: bool = False,
                 description: Optional[str] = None, stars: int = 0) -> "Repository":
        parts = url.strip("/").split("/")
        if len(parts) < 3:
            raise ValueError(f"Invalid repository URL: {url}")
        
        platform = parts[0]
        org = parts[1]
        repo = parts[2]
        
        return cls(
            platform=platform,
            org=org,
            repo=repo,
            url=url,
            is_archived=is_archived,
            is_fork=is_fork,
            description=description,
            stars=stars
        )

    def __str__(self) -> str:
        return self.url