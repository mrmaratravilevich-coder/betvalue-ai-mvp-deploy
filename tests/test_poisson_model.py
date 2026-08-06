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
        self.assertAlmostEqual(sum(sum(row) for row in matrix), 1.0, places=7)

    def test_derived_markets_are_normalized_after_tail_truncation(self) -> None:
        prediction = predict_match(3.2, 2.8, max_goals=4)

        self.assertAlmostEqual(prediction.btts_yes + prediction.btts_no, 1.0, places=7)
        self.assertAlmostEqual(prediction.over_line + prediction.under_line, 1.0, places=7)

    def test_zero_dixon_coles_rho_preserves_poisson(self) -> None:
        self.assertEqual(
            score_matrix(1.4, 0.9),
            score_matrix(1.4, 0.9, dixon_coles_rho=0.0),
        )

    def test_negative_rho_increases_zero_zero_and_one_one(self) -> None:
        poisson = score_matrix(1.4, 0.9)
        corrected = score_matrix(1.4, 0.9, dixon_coles_rho=-0.1)

        self.assertGreater(corrected[0][0], poisson[0][0])
        self.assertGreater(corrected[1][1], poisson[1][1])
        self.assertLess(corrected[0][1], poisson[0][1])
        self.assertLess(corrected[1][0], poisson[1][0])

    def test_invalid_dixon_coles_rho_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "negative score probability"):
            score_matrix(4.0, 4.0, dixon_coles_rho=-0.5)


if __name__ == "__main__":
    unittest.main()
