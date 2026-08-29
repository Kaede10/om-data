import os
from typing import List, Optional, Dict, Any
import requests

from .base import BaseFetcher
from models.repository import Repository


class GitCodeFetcher(BaseFetcher):
    PLATFORM = "gitcode"
    API_URL = "https://gitcode.com/api/v5"
    
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("GITCODE_TOKEN")
        self.session = requests.Session()
    
    def get_org_repos(
        self,
        org: str,
        exclude_archived: bool = False,
        exclude_forked: bool = False,
        exclude_pattern: Optional[List[str]] = None
    ) -> List[Repository]:
        repos: List[Repository] = []
        page = 1
        per_page = 100
        
        while True:
            url = f"{self.API_URL}/orgs/{org}/repos"
            params = {"page": page, "per_page": per_page, "type": "all"}
            if self.token:
                params["private_token"] = self.token
            
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            data: List[Dict[str, Any]] = response.json()
            if not data:
                break
            
            for item in data:
                repo = Repository(
                    platform=self.PLATFORM,
                    org=org,
                    repo=item.get("name", item.get("path", "")),
                    url=f"gitcode.com/{org}/{item.get('name', item.get('path', ''))}",
                    is_archived=item.get("archived", False),
                    is_fork=item.get("fork", False),
                    description=item.get("description"),
                    stars=item.get("stargazers_count", 0)
                )
                
                if not self._should_exclude(repo, exclude_archived, exclude_forked, exclude_pattern):
                    repos.append(repo)
            
            if len(data) < per_page:
                break
            page += 1
        
        return repos
    
    def get_rate_limit(self) -> dict:
        return {"note": "GitCode does not provide a rate limit API"}