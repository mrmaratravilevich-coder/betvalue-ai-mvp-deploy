import unittest

from app.services.models.poisson_model import predict_match, score_matrix


class PoissonModelTests(unittest.TestCase):
    def test_match_outcomes_are_normalized(self) -> None:
        prediction = predict_match(1.6, 1.1)

        self.assertAlmostEqual(
            prediction.home_win + prediction.draw + prediction.away_win,
            1.0,
            places=7,
        )
        self.assertGreater(prediction.home_win, prediction.away_win)

    def test_score_matrix_is_non_negative(self) -> None:
        matrix = score_matrix(1.4, 0.9)

        self.assertTrue(all(value >= 0 for row in matrix for value in row))
        self.assertGreater(sum(sum(row) for row in matrix), 0.999)


if __name__ == "__main__":
    unittest.main()
