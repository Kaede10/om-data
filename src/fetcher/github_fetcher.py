import os
from typing import List, Optional, Dict, Any
import requests

from .base import BaseFetcher
from models.repository import Repository


class GitHubFetcher(BaseFetcher):
    PLATFORM = "github"
    API_URL = "https://api.github.com"
    
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.session = requests.Session()
        if self.token:
            self.session.headers["Authorization"] = f"Bearer {self.token}"
        self.session.headers["Accept"] = "application/vnd.github.v3+json"
    
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
            params = {"per_page": per_page, "page": page, "type": "all"}
            
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            data: List[Dict[str, Any]] = response.json()
            if not data:
                break
            
            for item in data:
                repo = Repository(
                    platform=self.PLATFORM,
                    org=org,
                    repo=item["name"],
                    url=f"github.com/{org}/{item['name']}",
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
        url = f"{self.API_URL}/rate_limit"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()