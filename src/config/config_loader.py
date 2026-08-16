from pathlib import Path
from typing import List, Dict, Any, Optional
import yaml

from fetcher import BaseFetcher, GitHubFetcher, GiteeFetcher, GitCodeFetcher


class OrganizationConfig:
    def __init__(
        self,
        platform: str,
        orgs: List[str],
        token_env: Optional[str] = None,
        exclude_archived: bool = False,
        exclude_forked: bool = False,
        exclude_pattern: Optional[List[str]] = None
    ):
        self.platform = platform
        self.orgs = orgs
        self.token_env = token_env
        self.exclude_archived = exclude_archived
        self.exclude_forked = exclude_forked
        self.exclude_pattern = exclude_pattern


class ProjectConfig:
    def __init__(self, project: str, items: List[str]):
        self.project = project
        self.items = items


class ConfigLoader:
    FETCHER_MAP: Dict[str, type] = {
        "github": GitHubFetcher,
        "gitee": GiteeFetcher,
        "gitcode": GitCodeFetcher,
    }
    
    def __init__(self, config_path: str = "src/projects.yaml"):
        self.config_path = Path(config_path)
        self._config: Dict[str, Any] = {}
        self._organizations: List[OrganizationConfig] = []
        self._projects: List[ProjectConfig] = []
    
    def load(self) -> None:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        
        with open(self.config_path, "r", encoding="utf-8") as f:
            self._config = yaml.safe_load(f) or {}
        
        self._parse_organizations()
        self._parse_projects()
    
    def _parse_organizations(self) -> None:
        orgs_data = self._config.get("organizations", [])
        for org_config in orgs_data:
            self._organizations.append(OrganizationConfig(
                platform=org_config.get("platform", ""),
                orgs=org_config.get("orgs", []),
                token_env=org_config.get("token_env"),
                exclude_archived=org_config.get("exclude_archived", False),
                exclude_forked=org_config.get("exclude_forked", False),
                exclude_pattern=org_config.get("exclude_pattern")
            ))
    
    def _parse_projects(self) -> None:
        projects_data = self._config.get("projects", [])
        for proj in projects_data:
            self._projects.append(ProjectConfig(
                project=proj.get("project", ""),
                items=proj.get("items", [])
            ))
    
    @property
    def organizations(self) -> List[OrganizationConfig]:
        return self._organizations
    
    @property
    def projects(self) -> List[ProjectConfig]:
        return self._projects
    
    def get_fetcher(self, platform: str, token: Optional[str] = None) -> Optional[BaseFetcher]:
        fetcher_class = self.FETCHER_MAP.get(platform.lower())
        if not fetcher_class:
            return None
        return fetcher_class(token=token)
    
    def get_fetcher_for_org(self, org_config: OrganizationConfig) -> Optional[BaseFetcher]:
        import os
        token = None
        if org_config.token_env:
            token = os.environ.get(org_config.token_env)
        return self.get_fetcher(org_config.platform, token)