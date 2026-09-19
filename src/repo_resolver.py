from typing import Dict, List, Set
from models.repository import Repository
from config.config_loader import ConfigLoader, OrganizationConfig


class RepoResolver:
    def __init__(self, config_path: str = "src/projects.yaml"):
        self.config_loader = ConfigLoader(config_path)
        self.config_loader.load()
    
    def resolve_all(self) -> Dict[str, List[Repository]]:
        result: Dict[str, List[Repository]] = {}
        
        for org_config in self.config_loader.organizations:
            fetcher = self.config_loader.get_fetcher_for_org(org_config)
            if not fetcher:
                print(f"Warning: Unknown platform '{org_config.platform}'")
                continue
            
            platform_repos: List[Repository] = []
            for org in org_config.orgs:
                try:
                    repos = fetcher.get_org_repos(
                        org=org,
                        exclude_archived=org_config.exclude_archived,
                        exclude_forked=org_config.exclude_forked,
                        exclude_pattern=org_config.exclude_pattern
                    )
                    platform_repos.extend(repos)
                except Exception as e:
                    print(f"Error fetching repos for {org}: {e}")
            
            platform = org_config.platform
            if platform not in result:
                result[platform] = []
            result[platform].extend(platform_repos)
        
        return result
    
    def resolve_to_urls(self) -> Dict[str, List[str]]:
        repos = self.resolve_all()
        return {
            platform: [repo.url for repo in repo_list]
            for platform, repo_list in repos.items()
        }
    
    def get_all_repos(self) -> List[Repository]:
        all_repos: List[Repository] = []
        for repo_list in self.resolve_all().values():
            all_repos.extend(repo_list)
        return all_repos
    
    def get_all_urls(self) -> List[str]:
        urls: Set[str] = set()
        for url_list in self.resolve_to_urls().values():
            urls.update(url_list)
        
        for project in self.config_loader.projects:
            for item in project.items:
                urls.add(item)
        
        return sorted(list(urls))
    
    def get_repos_by_platform(self, platform: str) -> List[Repository]:
        repos = self.resolve_all()
        return repos.get(platform.lower(), [])


def main():
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="Resolve organization repositories")
    parser.add_argument("--config", default="src/projects.yaml", help="Path to config file")
    parser.add_argument("--format", choices=["json", "yaml", "urls"], default="urls", help="Output format")
    parser.add_argument("--platform", help="Filter by platform (github/gitee/gitcode)")
    args = parser.parse_args()
    
    resolver = RepoResolver(config_path=args.config)
    
    if args.format == "urls":
        urls = resolver.get_all_urls()
        for url in urls:
            print(url)
    elif args.format == "json":
        if args.platform:
            repos = resolver.get_repos_by_platform(args.platform)
            output = [r.__dict__ for r in repos]
        else:
            output = resolver.resolve_to_urls()
        print(json.dumps(output, indent=2))
    elif args.format == "yaml":
        import yaml
        if args.platform:
            repos = resolver.get_repos_by_platform(args.platform)
            output = [r.__dict__ for r in repos]
        else:
            output = resolver.resolve_to_urls()
        print(yaml.dump(output, default_flow_style=False))


if __name__ == "__main__":
    main()