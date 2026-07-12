import socket
import time
import unittest

from network.client import GridClient
from network.server import GridServer


class NetworkReconnectTest(unittest.TestCase):
    def setUp(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        self.port = probe.getsockname()[1]
        probe.close()

        self.server = GridServer(port=self.port, max_players=2)
        self.assertTrue(self.server.start())

    def tearDown(self):
        self.server.stop()

    def wait_for(self, predicate, timeout=2.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return True
            time.sleep(0.01)
        return False

    def test_reconnect_reuses_first_available_player_slot(self):
        first = GridClient("127.0.0.1", port=self.port)
        self.assertTrue(first.connect())
        self.assertTrue(self.wait_for(lambda: first.my_player_id == 1))

        first.stop()
        self.assertTrue(self.wait_for(lambda: not self.server.players))

        second = GridClient("127.0.0.1", port=self.port)
        self.addCleanup(second.stop)
        self.assertTrue(second.connect())
        self.assertTrue(self.wait_for(lambda: second.my_player_id == 1))

    def test_client_receives_started_game_state(self):
        snapshots = []
        client = GridClient(
            "127.0.0.1",
            port=self.port,
            on_state_update=lambda: snapshots.append(
                (client.game_started, client.difficulty, client.items_per_player)
            ),
        )
        self.addCleanup(client.stop)
        self.assertTrue(client.connect())
        self.assertTrue(self.wait_for(lambda: client.my_player_id == 1))

        self.server.start_game("medium")

        self.assertTrue(
            self.wait_for(lambda: (True, "medium", 3) in snapshots),
            snapshots,
        )

    def test_lobby_chat_reports_join_message_and_leave(self):
        client = GridClient("127.0.0.1", port=self.port)
        self.assertTrue(client.connect())
        self.assertTrue(self.wait_for(lambda: client.my_player_id == 1))
        self.assertTrue(self.wait_for(
            lambda: any("joined the lobby" in msg["text"] for msg in self.server.chat_history)
        ))

        client.send_chat("hello lobby")
        self.assertTrue(self.wait_for(
            lambda: any(msg["text"] == "hello lobby" for msg in self.server.chat_history)
        ))

        client.stop()
        self.assertTrue(self.wait_for(
            lambda: any("left the lobby" in msg["text"] for msg in self.server.chat_history)
        ))


if __name__ == "__main__":
    unittest.main()
