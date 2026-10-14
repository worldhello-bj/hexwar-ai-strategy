import ast
import inspect
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from env.neural_policy import Decision, NeuralPolicy


class NeuralPolicyTests(unittest.TestCase):
    def model(self, **kwargs):
        return NeuralPolicy(buckets=64, hidden_dim=3, **kwargs)

    def test_canonical_dict_order_and_array_order(self):
        p = self.model()
        np.testing.assert_array_equal(p.encode({"a": 1, "b": [2, 3]}), p.encode({"b": [2, 3], "a": 1}))
        self.assertFalse(np.array_equal(p.encode([2, 3]), p.encode([3, 2])))
        self.assertFalse(np.array_equal(p.encode(True), p.encode(1)))
        self.assertFalse(np.array_equal(p.encode("1"), p.encode(1)))
        self.assertFalse(np.array_equal(p.encode({"0": 1}), p.encode([1])))
        for invalid in [float("nan"), float("inf"), {1: "x"}, object()]:
            with self.assertRaises(ValueError):
                p.encode(invalid)

    def test_probabilities_order_and_legal_identity(self):
        p = self.model()
        actions = [{"x": 1}, {"x": 2}, {"x": -3}]
        probabilities = p.probabilities({"state": 5}, actions)
        self.assertTrue(np.isfinite(probabilities).all())
        self.assertTrue((probabilities > 0).all())
        self.assertAlmostEqual(sum(probabilities), 1)
        np.testing.assert_allclose(probabilities[[2, 0, 1]], p.probabilities({"state": 5}, [actions[i] for i in [2, 0, 1]]), atol=1e-14)
        for _ in range(20):
            action, decision = p.sample({}, actions)
            self.assertIs(action, actions[decision.selected])
        with self.assertRaises(ValueError):
            p.select({}, [])
        self.assertIs(p.select({}, [actions[0]]), actions[0])

    def test_observation_action_product_changes_preferences(self):
        p = self.model()
        actions = [{"x": 1}, {"x": 2}]
        first = p.probabilities({"state": 1}, actions)
        second = p.probabilities({"state": -1}, actions)
        self.assertGreater(np.max(abs(first - second)), 1e-10)
        p.params["policy"][6:] = 0
        np.testing.assert_allclose(p.probabilities({"state": 1}, actions), p.probabilities({"state": -1}, actions), atol=1e-14)

    def test_every_parameter_gradient_by_finite_difference(self):
        p = NeuralPolicy(buckets=8, hidden_dim=2)
        examples = [(p._decision({"a": 2}, [{"b": 1}, {"b": -2}], 1), 3.5),
                    (p._decision([None, False], ["a", "b", "c"], 0), -1.2)]
        advantages = [score - p._forward(d)[4] for d, score in examples]
        _, gradients = p._loss_gradients(examples, advantages)
        eps = 1e-5
        for name, parameter in p.params.items():
            for index in np.ndindex(parameter.shape):
                old = parameter[index]
                parameter[index] = old + eps
                plus = p._loss_gradients(examples, advantages)[0]
                parameter[index] = old - eps
                minus = p._loss_gradients(examples, advantages)[0]
                parameter[index] = old
                self.assertAlmostEqual(gradients[name][index], (plus - minus) / (2 * eps), places=7, msg=str((name, index)))

    def test_variable_length_actor_is_episode_mean(self):
        p = self.model()
        short = p._decision({"s": 1}, [1, 2], 0)
        long = p._decision({"s": 2}, [1, 2], 1)
        examples = [(short, 3.0), (long, 7.0), (long, 7.0), (long, 7.0)]
        advantages = [score - p._forward(d)[4] for d, score in examples]
        _, episode_gradients = p._loss_gradients(examples, advantages, actor_normalizer=2)
        _, decision_gradients = p._loss_gradients(examples, advantages)
        np.testing.assert_allclose(episode_gradients["policy"], 2 * decision_gradients["policy"])
        np.testing.assert_allclose(episode_gradients["value"], decision_gradients["value"])
        eps = 1e-5
        for name, parameter in p.params.items():
            index = (0,) * parameter.ndim
            old = parameter[index]
            parameter[index] = old + eps
            plus = p._loss_gradients(examples, advantages, actor_normalizer=2)[0]
            parameter[index] = old - eps
            minus = p._loss_gradients(examples, advantages, actor_normalizer=2)[0]
            parameter[index] = old
            self.assertAlmostEqual(episode_gradients[name][index], (plus - minus) / (2 * eps), places=7)
        # Capture the actual update's normalization, including an empty episode.
        from unittest.mock import patch
        with patch.object(p, "_loss_gradients", wraps=p._loss_gradients) as compute:
            p.update_batch([([short], 3.0), ([long, long, long], 7.0), ([], 0.0)])
            self.assertEqual(compute.call_args.kwargs["actor_normalizer"], 3)

    def test_checkpoint_resume_exact_including_optimizer_rng(self):
        p = self.model(seed=10)
        actions = [{"a": 1}, {"a": 2}]
        _, record = p.sample({"s": 7}, actions)
        p.update_batch([([record], 170.0)])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            p.save(path)
            q = NeuralPolicy.load(path)
            with self.assertRaises(FileExistsError):
                p.save(path)
        saved_record = Decision.from_dict(json.loads(json.dumps(record.to_dict())))
        p.update_batch([([record], -7)])
        q.update_batch([([saved_record], -7)])
        for _ in range(20):
            self.assertEqual(p.sample({}, actions)[1].selected, q.sample({}, actions)[1].selected)
        self.assertEqual(p.checkpoint(), q.checkpoint())

    def test_raw_return_empty_batch_and_baseline(self):
        p = self.model()
        d = p._decision({}, [1, 2])
        predicted = p._forward(d)[4]
        loss, gradients = p._loss_gradients([(d, 123.0)])
        self.assertAlmostEqual(gradients["value_bias"][0], predicted - 123.0)
        self.assertGreater(loss, 1000)
        before = p.checkpoint()
        self.assertEqual(p.update_batch([])["decisions"], 0)
        self.assertEqual(before, p.checkpoint())
        with self.assertRaises(ValueError):
            p.update_batch([([d], float("nan"))])
        self.assertEqual(before, p.checkpoint())
        report = p.update_batch([([d], 123.0)])
        self.assertEqual(report["decisions"], 1)
        self.assertEqual(p.steps, 1)

    def test_no_private_environment_import_or_access(self):
        import env.neural_policy as module
        source = inspect.getsource(module)
        tree = ast.parse(source)
        imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        imports += [alias.name for n in ast.walk(tree) if isinstance(n, ast.Import) for alias in n.names]
        self.assertEqual(set(imports), {"dataclasses", "hashlib", "json", "math", "pathlib", "numpy"})
        self.assertNotIn("getattr(env", source)


if __name__ == "__main__":
    unittest.main()
