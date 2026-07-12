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


if __name__ == "__main__":
    unittest.main()
