class RefreshToken(object):

    def __init__(self, config=None):
        self.config = config
        self.service_refresh_token = json.loads(config.get('service_refresh_token'))
        self.expires_in = int(config.get('expires_in'))

    def run(self, from_time):
        self.is_refresh_token()
        time.sleep(10)
        services = self.esClient.get_access_token(self.index_name_token)
        for service in services:
            print("...service = %s, created_at = %s, access_token = %s***..."
                  % (service.get("service"), service.get("created_at"), service.get("access_token")[:8]))

    def is_refresh_token(self):
        for service in self.service_refresh_token:
            valid_token = self.get_valid_token(service)
            if time.time() > (int(valid_token.get("created_time")) + self.expires_in - 60):
                print('Star to refresh access token for %s ...' % valid_token.get("service"))
                self.refresh_access_token(valid_token)
