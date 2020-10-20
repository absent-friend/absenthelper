from pathlib import Path

class AbsentHelperConfig:
    def __init__(self, twitch_username, twitch_oauth, twitch_channel, 
            livesplit_config, pastebin_dev_key, pastebin_username, 
            pastebin_password):
        self.twitch_username = twitch_username
        self.twitch_oauth = twitch_oauth
        self.twitch_channel = f'#{twitch_channel}'
        self.livesplit_config = Path(livesplit_config)
        self.pastebin_dev_key = pastebin_dev_key
        self.pastebin_username = pastebin_username
        self.pastebin_password = pastebin_password

    def is_valid(self):
        self.errors = []
        if not self.livesplit_config.is_file():
            self.errors.append(f'{self.livesplit_config} does not exist or is not a file.')

        return not self.errors
