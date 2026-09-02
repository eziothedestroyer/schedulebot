import unittest

from twitch_client import TwitchClient


class FakeTwitchClient(TwitchClient):
    def _form(self, url, values):
        self.last_form = (url, values)
        return {"access_token": "new-access", "refresh_token": "new-refresh"}


class TwitchClientTests(unittest.TestCase):
    def test_public_client_refresh_rotates_and_reports_tokens(self):
        saved = []
        client = FakeTwitchClient("client-id", refresh_token="old-refresh",
                                  token_callback=lambda access, refresh: saved.append((access, refresh)))

        client.refresh_access_token()

        self.assertEqual(client.access_token, "new-access")
        self.assertEqual(client.refresh_token, "new-refresh")
        self.assertEqual(saved, [("new-access", "new-refresh")])
        self.assertNotIn("client_secret", client.last_form[1])
        self.assertEqual(client.last_form[1]["grant_type"], "refresh_token")


if __name__ == "__main__":
    unittest.main()
