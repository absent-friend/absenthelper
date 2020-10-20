from datetime import datetime
import socket

from bs4 import BeautifulSoup
import irc.bot
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from pbwrap import Pastebin

class AbsentHelper(irc.bot.SingleServerIRCBot):
    KNOWN_COMPARISONS = {
            'pb': 'Personal Best',
            'best': 'Best Segments',
            'bestsplits': 'Best Split Times',
            'average': 'Average Segments',
            'median': 'Median Segments',
            'worst': 'Worst Segments',
            'balanced': 'Balanced PB',
            'latest': 'Latest Run',
            'none': 'None'
    }
    MAX_RECV = 4096

    def __init__(self, config):
        self.config = config

        # Create IRC bot connection
        server = 'irc.chat.twitch.tv'
        port = 6667
        print('Connecting to ' + server + ' on port ' + str(port) + '...')
        irc.bot.SingleServerIRCBot.__init__(self, [(server, port, 'oauth:'+config.twitch_oauth)], config.twitch_username, config.twitch_username)
        
        # try to connect to livesplit server
        self._init_livesplit_server()

        # read livesplit config to get active comparisons
        self.active = {'Personal Best': True}
        with config.livesplit_config.open() as livesplit_config_file:
            livesplit_config_root = BeautifulSoup(livesplit_config_file, 'html.parser')
            comparison_settings = livesplit_config_root.find('comparisongeneratorstates')
            for comparison in comparison_settings.find_all(True):
                is_active = eval(comparison.string) if comparison.string in ['True', 'False'] else False
                self.active[comparison['name']] = is_active

        # init spotify client
        scope = " ".join([
            'user-read-currently-playing',
            'user-read-recently-played',
        ])
        self.spotify = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=scope, open_browser=False))
        # this will output an authorization URI to stdout and prompt for the redirect URI,
        # if not already authorized
        self.spotify.current_user_playing_track()

        # init pastebin client
        self.pastebin = Pastebin(config.pastebin_dev_key)
        self.pastebin.authenticate(config.pastebin_username, config.pastebin_password)

    def _init_livesplit_server(self):
        self.livesplit_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.livesplit_server.connect(("localhost", 16834))
        except ConnectionRefusedError:
            self.livesplit_server = None

    def on_welcome(self, c, e):
        print('Joining ' + self.config.twitch_channel.strip('#'))
        c.join(self.config.twitch_channel)

    def on_pubmsg(self, c, e):
        parts = e.arguments[0].strip().split(' ', 1)
        if parts[0][:1] == '!':
            print(f'got command: {e.arguments[0]}')
            cmd = parts[0][1:]
            args = parts[1:]
            self.command_dispatch(cmd, args)

    def command_dispatch(self, cmd, args):
        c = self.connection

        if cmd == 'splits':
            if len(args) != 1:
                c.privmsg(self.config.twitch_channel, 'usage: !splits <comparison>')
                return
            self.splits_info(args[0])
        elif cmd == 'spotify':
            if len(args) != 1:
                c.privmsg(self.config.twitch_channel, 'usage: !spotify <command>')
                return
            self.spotify_info(args[0])
        elif cmd == 'thoughts':
            self.latest_pastebin()
        else:
            print(f'unrecognized command: {cmd}')

    def splits_info(self, shorthand):
        """Queries a local livesplit server for the final time
        for the given comparison and posts the time in chat.
        """
        c = self.connection
        comparison = TwitchBot.KNOWN_COMPARISONS.get(shorthand)
        if not comparison:
            c.privmsg(self.config.twitch_channel, f'"{shorthand}" is not a shorthand for any known comparison.')
        elif comparison == 'None':
            c.privmsg(self.config.twitch_channel, 'why')
        elif not self.active[comparison]:
            c.privmsg(self.config.twitch_channel, f'The "{comparison}" comparison is not currently active.')
        elif not self.livesplit_server:
            self._init_livesplit_server()
            if not self.livesplit_server:
                c.privmsg(self.config.twitch_channel, 'LiveSplit Server isn\'t running at the moment.')
            else:
                self._try_get_time(comparison)
        else:
            self._try_get_time(comparison)

    def _try_get_time(self, comparison):
        c = self.connection
        time = self._get_final_time(comparison)
        if not time:
            self._init_livesplit_server()
            if not self.livesplit_server:
                c.privmsg(self.config.twitch_channel, 'LiveSplit Server isn\'t running at the moment.')
                return
            time = self._get_final_time(comparison)
        c.privmsg(self.config.twitch_channel, f'Final time for comparison "{comparison}" is {time}.')

    def _get_final_time(self, comparison):
        command = bytes(f'getfinaltime {comparison}\r\n', 'ascii')
        self.livesplit_server.send(command)
        return self.livesplit_server.recv(AbsentHelper.MAX_RECV).decode().strip()

    def spotify_info(self, command):
        c = self.connection

        if command == 'current':
            track_data = self.spotify.current_user_playing_track()
            if not track_data:
                c.privmsg(self.config.twitch_channel, 'No currently playing track.')
            else:
                track = track_data['item']
                c.privmsg(self.config.twitch_channel, self._track_info_message(track))
        elif command == 'previous':
            track_data = self.spotify.current_user_recently_played(limit=1)
            if 'items' not in track_data or not track_data['items']:
                c.privmsg(self.config.twitch_channel, 'No recently played tracks.')
            else:
                track = track_data['items'][0]['track']
                c.privmsg(self.config.twitch_channel, self._track_info_message(track))

    def _track_info_message(self, track):
        track_artists = ', '.join([artist['name'] for artist in track['artists']])
        track_name = track['name']
        return f'{track_artists} - {track_name}'

    def latest_pastebin(self):
        c = self.connection
       
        pastes = self.pastebin.get_user_pastes(api_results_limit=1)
        if not pastes:
            c.privmsg(self.config.twitch_channel, 'No thoughts.')
            return

        paste_title = pastes[0].title
        paste_date = datetime.fromtimestamp(int(pastes[0].date))
        paste_url = pastes[0].url
        message = f'{paste_title} ({paste_date:%Y-%m-%d}) --- {paste_url}'
        c.privmsg(self.config.twitch_channel, message)
