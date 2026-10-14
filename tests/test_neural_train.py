"""Own terminal returns, exact resume and frozen paired evaluation contracts."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from env.episode_api import TwoPlayerEpisode
from env.match_eval import SIDES, write_synthetic_snapshot
from env.neural_train import NeuralTrainer, canonical, main


class NeuralTrainingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.snapshot = write_synthetic_snapshot(self.root / "snapshot")

    def trainer(self, **kwargs):
        return NeuralTrainer(self.snapshot, policy_config={"buckets": 32, "hidden_dim": 4},
                             episode_config={"max_seconds": 20, "max_steps": 100}, **kwargs)

    def test_actual_synthetic_fixture_updates_parameters(self):
        trainer = self.trainer(seed=3, batch_episodes=2)
        before = copy.deepcopy(trainer.policy.checkpoint()["params"])
        records = trainer.train(2)
        self.assertTrue(all(r["status"]["terminated"] for r in records))
        self.assertEqual([r["learner_side"] for r in records], list(SIDES))
        self.assertEqual(trainer.updates, 1)
        self.assertNotEqual(before, trainer.policy.checkpoint()["params"])
        for row in records:
            self.assertEqual(row["own_score"], row["status"]["final_scores"][row["learner_side"]])

    def test_only_own_observations_and_raw_terminal_targets(self):
        observed = []
        class ScriptedEpisode:
            def __init__(self, *args, **kwargs):
                self.n = 0
            def reset(self, *, seed):
                self.seed = seed
                return self.status()
            def status(self):
                done = self.n == 4
                return {"current_actor": None if done else SIDES[self.n % 2],
                        "terminated": done, "truncated": False,
                        "final_scores": {"BLUE": 7, "RED": -3} if done else None,
                        "rewards": {"BLUE": 7, "RED": -3} if done else {s: 0 for s in SIDES}}
            def observe(self, side):
                observed.append((self.seed, side))
                return {"side": side, "visible": []}
            def legal_actions(self, side):
                return [{"token": 0}, {"token": 1}]
            def step(self, action, **kwargs):
                self.n += 1
                return self.status()
        with patch("env.neural_train.TwoPlayerEpisode", ScriptedEpisode):
            trainer = self.trainer(batch_episodes=2)
            with patch.object(trainer.policy, "update_batch", wraps=trainer.policy.update_batch) as update:
                trainer.train(2)
                # The list is cleared after update; capture immutable expectations via wrapper below.
                self.assertEqual(update.call_count, 1)
        self.assertEqual(observed, [(0, "BLUE"), (0, "BLUE"), (1, "RED"), (1, "RED")])
        with patch("env.neural_train.TwoPlayerEpisode", ScriptedEpisode):
            trainer = self.trainer(batch_episodes=2)
            batches = []
            original = trainer.policy.update_batch
            def capture(batch):
                batches.append([(len(history), score) for history, score in batch])
                return original(batch)
            trainer.policy.update_batch = capture
            trainer.train(2)
        self.assertEqual(batches, [[(2, 7), (2, -3)]])

    def test_real_intermediate_rewards_are_zero(self):
        episode = TwoPlayerEpisode(self.snapshot, max_seconds=40, max_steps=100)
        status = episode.reset(seed=7)
        saw_intermediate = False
        while not status["terminated"] and not status["truncated"]:
            self.assertEqual(status["rewards"], {s: 0 for s in SIDES})
            saw_intermediate = True
            status = episode.step(episode.legal_actions()[0])
        self.assertTrue(saw_intermediate)
        self.assertEqual(status["rewards"], status["final_scores"])

    def test_truncation_never_updates_or_enters_pending(self):
        trainer = NeuralTrainer(self.snapshot, episode_config={"max_seconds": 999, "max_steps": 2},
                                policy_config={"buckets": 32, "hidden_dim": 4}, batch_episodes=1)
        before = copy.deepcopy(trainer.policy.checkpoint())
        records = trainer.train(2)
        self.assertTrue(all(r["status"]["truncated"] for r in records))
        self.assertEqual(trainer.updates, 0)
        self.assertEqual(trainer.pending, [])
        after = trainer.policy.checkpoint()
        for key in ("params", "m", "v", "steps"):
            self.assertEqual(before[key], after[key])

    def test_resume_matches_uninterrupted_even_mid_batch(self):
        whole = self.trainer(seed=71, batch_episodes=2)
        whole.train(6)
        partial = self.trainer(seed=71, batch_episodes=2)
        partial.train(3)
        path = self.root / "checkpoint.json"
        partial.save(path)
        resumed = NeuralTrainer.load(path, self.snapshot)
        resumed.train(3)
        self.assertEqual(resumed.checkpoint(), whole.checkpoint())
        with self.assertRaises(FileExistsError):
            resumed.save(path)

    def test_frozen_initial_and_trained_paired_evaluation_no_mutation(self):
        trainer = self.trainer(seed=14, batch_episodes=2, heldout_seeds=[90, 91])
        trainer.train(2)
        before = canonical(trainer.checkpoint())
        first, second = trainer.evaluate(), trainer.evaluate()
        for output in (first, second):
            for label in ("initial", "trained"):
                for row in output[label]["games"]:
                    row.pop("elapsed_seconds")
        self.assertEqual(first, second)
        self.assertEqual(canonical(trainer.checkpoint()), before)
        self.assertEqual([(r["seed"], r["learner_side"]) for r in first["initial"]["games"]],
                         [(90, "BLUE"), (90, "RED"), (91, "BLUE"), (91, "RED")])
        with self.assertRaises(ValueError):
            trainer.evaluate([1])
        with self.assertRaises(ValueError):
            trainer.evaluate([90, 90])

    def test_heldout_reservation_blocks_future_training(self):
        trainer = self.trainer(heldout_seeds=[2])
        before = trainer.checkpoint()
        with self.assertRaises(ValueError):
            trainer.train(3)
        self.assertEqual(before, trainer.checkpoint())

    def test_malformed_pending_features_rejected_at_load(self):
        trainer = self.trainer(batch_episodes=2)
        trainer.train(1)
        data = trainer.checkpoint()
        data["pending"][0]["decisions"][0]["observation"][0][0] = 32
        path = self.root / "invalid.json"
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            NeuralTrainer.load(path, self.snapshot)

    def test_snapshot_changes_rejected(self):
        trainer = self.trainer()
        path = self.root / "checkpoint.json"
        trainer.save(path)
        units = self.snapshot / "units.json"
        units.write_text(units.read_text() + "\n")
        with self.assertRaises(ValueError):
            trainer.train(1)
        with self.assertRaises(ValueError):
            NeuralTrainer.load(path, self.snapshot)

    def test_explicit_snapshot_cli_and_resume(self):
        checkpoint, report = self.root / "first.json", self.root / "report.json"
        common = ["--snapshot", str(self.snapshot), "--episodes", "2", "--buckets", "32", "--hidden-dim", "4",
                  "--max-seconds", "10", "--max-steps", "20", "--batch-episodes", "2"]
        self.assertEqual(main(common + ["--checkpoint", str(checkpoint), "--report", str(report)]), 0)
        self.assertEqual(json.loads(report.read_text())["updates"], 1)
        second, report2 = self.root / "second.json", self.root / "report2.json"
        self.assertEqual(main(common + ["--resume", str(checkpoint), "--checkpoint", str(second), "--report", str(report2)]), 0)
        self.assertEqual(json.loads(second.read_text())["episodes_attempted"], 4)


if __name__ == "__main__":
    unittest.main()
