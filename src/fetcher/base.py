from abc import ABC, abstractmethod
from typing import List, Optional

from models.repository import Repository


class BaseFetcher(ABC):
    PLATFORM: str = ""
    
    @abstractmethod
    def get_org_repos(
        self, 
        org: str, 
        exclude_archived: bool = False,
        exclude_forked: bool = False,
        exclude_pattern: Optional[List[str]] = None
    ) -> List[Repository]:
        pass

    @abstractmethod
    def get_rate_limit(self) -> dict:
        pass

    def _should_exclude(
        self, 
        repo: Repository, 
        exclude_archived: bool,
        exclude_forked: bool,
        exclude_pattern: Optional[List[str]]
    ) -> bool:
        if exclude_archived and repo.is_archived:
            return True
        if exclude_forked and repo.is_fork:
            return True
        if exclude_pattern:
            import re
            for pattern in exclude_pattern:
                if re.match(pattern, repo.repo):
                    return True
        return False