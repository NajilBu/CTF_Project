import unittest
from unittest.mock import patch

from gui.app import GridGameApp
from network.server import GridServer


class MultiplayerRulesTest(unittest.TestCase):
    def make_server(self):
        server = GridServer(max_players=2)
        server.game_started = True
        server.players = {
            1: {"r": 0, "c": 0, "color": "#00d2ff", "ip": "one", "moves": 0},
            2: {"r": 0, "c": 1, "color": "#ff4d4d", "ip": "two", "moves": 0},
        }
        server.player_visited = {1: {(0, 0)}, 2: {(0, 1)}}
        server.player_items = {1: set(), 2: set()}
        server.player_collected = {1: {}, 2: {}}
        server.player_item_keys = {1: {}, 2: {}}
        server.player_powerups = {1: [None, None, None], 2: [None, None, None]}
        server.broadcast_state = lambda: None
        return server

    @patch("network.server.play_sound", lambda *_: None)
    def test_players_can_cross_other_trails_and_positions(self):
        server = self.make_server()
        server.player_collected[2][(0, 1)] = server.players[2]["color"]
        server.process_client_move(1, 0, 1)
        self.assertEqual((server.players[1]["r"], server.players[1]["c"]), (0, 1))
        self.assertIn((0, 1), server.player_visited[1])

    @patch("gui.app.play_sound", lambda *_: None)
    @patch("gui.app.time.time", return_value=10.0)
    def test_client_qte_uses_only_its_own_unlocked_grids(self, _time):
        app = GridGameApp.__new__(GridGameApp)
        app.in_game = True
        app.in_active_game = True
        app.is_client = True
        app.my_player_id = 1
        app.players = {
            1: {"r": 0, "c": 0},
            2: {"r": 0, "c": 1},
        }
        app.client = type("Client", (), {
            "finished_players": [],
            "get_my_visited": lambda self: {(0, 0)},
        })()
        app.qte_active = False
        app.last_move_time = 0.0
        app.last_qte_key_time = 0.0
        app.qte_sequence = []
        app.qte_progress = 0
        app.draw_elements = lambda: None

        app.move_player(0, 1)

        self.assertTrue(app.qte_active)
        self.assertEqual(app.qte_target_move, (0, 1))

    def test_state_shares_items_but_only_own_vault_keys(self):
        server = self.make_server()
        server.player_items = {1: {(2, 2)}, 2: {(3, 3)}}
        server.player_item_keys = {1: {(2, 2): "ONE|PGF|1"}, 2: {(3, 3): "TWO|UXP|1"}}

        state = server._build_state(1)["per_player"]

        self.assertEqual(state["1"]["item_keys"], {"2,2": "ONE|PGF|1"})
        self.assertEqual(state["2"]["item_keys"], {})
        self.assertEqual(state["2"]["visited"], [])
        self.assertEqual(state["2"]["collected"], {})
        self.assertEqual(state["2"]["items"], [(3, 3)])

    def test_finish_thresholds(self):
        expected = {1: 1, 2: 1, 3: 2, 4: 3, 5: 3, 6: 3}
        for players, target in expected.items():
            with self.subTest(players=players):
                self.assertEqual(GridServer.finish_target_for(players), target)

    @patch("network.server.play_sound", lambda *_: None)
    def test_match_finishes_when_captured_threshold_is_reached(self):
        server = self.make_server()
        server.items_per_player = 1
        server.finish_target = 1
        server.player_items[1] = {(0, 0)}
        server.player_item_keys[1] = {(0, 0): "SECRET|TFDSFU|1"}

        server.process_client_unlock(1, 0, 0, "SECRET")

        self.assertEqual(server.finished_players, [1])
        self.assertTrue(server.match_finished)

    def test_finished_players_are_hidden_from_player_map(self):
        app = GridGameApp.__new__(GridGameApp)
        app.players = {1: {"r": 0, "c": 0}, 2: {"r": 1, "c": 1}}
        app.client = type("Client", (), {"finished_players": [2]})()
        self.assertEqual(set(app.visible_map_players()), {1})

    @patch("network.server.play_sound", lambda *_: None)
    def test_powerups_are_collected_into_fixed_slots(self):
        server = self.make_server()
        cases = (("reveal", 0), ("shield", 1), ("speed", 2))
        for powerup, slot in cases:
            server.players[1]["r"], server.players[1]["c"] = 0, 0
            server.powerups = {(1, 0): powerup}
            server.process_client_move(1, 1, 0)
            self.assertEqual(server.player_powerups[1][slot], powerup)
            server.player_powerups[1] = [None, None, None]

    @patch("network.server.play_sound", lambda *_: None)
    @patch("network.server.random.randint", side_effect=[9, 19])
    def test_powerup_two_moves_opponent_item_under_player(self, _randint):
        server = self.make_server()
        source = (0, 0)
        destination = (9, 19)
        server.player_items[2] = {source}
        server.player_item_keys[2] = {source: "VAULT|XBVMU|2"}
        server.player_visited[2] = {
            (r, c) for r in range(10) for c in range(20)
            if (r, c) != destination
        }
        server.player_powerups[1][1] = "shield"

        server.process_client_powerup(1, 1)

        self.assertEqual(server.player_items[2], {destination})
        self.assertEqual(server.player_item_keys[2][destination], "VAULT|XBVMU|2")
        self.assertIsNone(server.player_powerups[1][1])

    @patch("network.server.play_sound", lambda *_: None)
    def test_powerup_two_is_not_consumed_without_opponent_item(self):
        server = self.make_server()
        server.player_powerups[1][1] = "shield"
        server.process_client_powerup(1, 1)
        self.assertEqual(server.player_powerups[1][1], "shield")


class EnterVaultTest(unittest.TestCase):
    def test_enter_opens_multiplayer_vault_on_owned_item(self):
        app = GridGameApp.__new__(GridGameApp)
        app.in_active_game = True
        app.qte_active = False
        app.my_player_id = 1
        app.is_client = True
        app.players = {1: {"r": 4, "c": 5}}
        app.per_player_data = {1: {"items": {(4, 5)}}}
        opened = []
        app.open_lock_dialog = lambda: opened.append(True)

        app.open_vault_at_current_item()

        self.assertEqual(opened, [True])

    @patch("gui.app.play_sound", lambda *_: None)
    def test_security_lock_can_be_cancelled(self):
        app = GridGameApp.__new__(GridGameApp)
        app.qte_active = True
        app.qte_sequence = [(1, 0)]
        app.qte_progress = 0
        app.qte_target_move = (1, 0)

        app.cancel_qte()

        self.assertFalse(app.qte_active)
        self.assertEqual(app.qte_sequence, [])
        self.assertEqual(app.qte_target_move, (0, 0))


class VisibilityTest(unittest.TestCase):
    class Canvas:
        def __init__(self):
            self.rectangles = []
            self.ovals = []

        def create_rectangle(self, *args, **kwargs):
            self.rectangles.append((args, kwargs))

        def create_text(self, *args, **kwargs):
            pass

        def create_oval(self, *args, **kwargs):
            self.ovals.append((args, kwargs))

    def test_items_and_powerups_render_only_on_discovered_cells(self):
        app = GridGameApp.__new__(GridGameApp)
        app.my_player_id = 1
        app.canvas = self.Canvas()
        app.players = {1: {"color": "#00d2ff"}, 2: {"color": "#ff4d4d"}}
        app.per_player_data = {
            1: {"visited": {(2, 2)}},
            2: {"items": {(2, 2), (3, 3)}},
        }
        app.client = type("Client", (), {
            "map_powerups": {(2, 2): "reveal", (4, 4): "speed"},
            "get_my_visited": lambda self: {(2, 2)},
        })()

        app._draw_shared_items()
        app._draw_map_powerups()

        self.assertEqual(len(app.canvas.rectangles), 1)
        self.assertEqual(len(app.canvas.ovals), 1)


if __name__ == "__main__":
    unittest.main()
