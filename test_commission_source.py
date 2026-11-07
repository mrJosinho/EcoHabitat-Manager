import unittest

import pandas as pd

from commission_source import normalize_commission_columns


class CommissionSourceTests(unittest.TestCase):
    def normalize(self, rows):
        return normalize_commission_columns(
            pd.DataFrame(rows),
            "TOTAL VENTE",
            "Vente HT hors acompte",
            "Total ventes avant remise",
            "Remise PP",
            ["Commercial", "Commercial 2", "Commercial 3"],
        )

    def test_normal_sale_keeps_the_existing_values(self):
        result = self.normalize([{
            "Commercial": "Vendeur 1",
            "Commercial 2": "",
            "Commercial 3": "",
            "Vente HT hors acompte": 10000.0,
            "TOTAL VENTE": 10000.0,
            "Remise PP": 1500.0,
            "Total ventes avant remise": 11500.0,
        }])

        self.assertAlmostEqual(result.iloc[0]["TOTAL VENTE"], 10000.0)
        self.assertAlmostEqual(result.iloc[0]["Total ventes avant remise"], 11500.0)

    def test_customer_deposit_is_neutralized_for_all_sellers(self):
        result = self.normalize([{
            "Commercial": "SCOLAN Marc",
            "Commercial 2": "LEMONNIER Florian",
            "Commercial 3": "",
            "Vente HT hors acompte": 22243.84,
            "TOTAL VENTE": 7785.345,
            "Remise PP": 4221.72,
            "Total ventes avant remise": 19792.41,
        }])

        self.assertAlmostEqual(result.iloc[0]["TOTAL VENTE"], 11121.92)
        self.assertAlmostEqual(result.iloc[0]["Total ventes avant remise"], 26465.56)

    def test_invalid_complete_sale_keeps_exported_fallback_values(self):
        result = self.normalize([{
            "Commercial": "Vendeur 1",
            "Commercial 2": "",
            "Commercial 3": "",
            "Vente HT hors acompte": "",
            "TOTAL VENTE": 7500.0,
            "Remise PP": 1200.0,
            "Total ventes avant remise": 8700.0,
        }])

        self.assertAlmostEqual(result.iloc[0]["TOTAL VENTE"], 7500.0)
        self.assertAlmostEqual(result.iloc[0]["Total ventes avant remise"], 8700.0)

    def test_total_row_without_a_seller_is_not_rewritten(self):
        result = self.normalize([{
            "Commercial": "",
            "Commercial 2": "",
            "Commercial 3": "",
            "Vente HT hors acompte": 100000.0,
            "TOTAL VENTE": 60000.0,
            "Remise PP": 10000.0,
            "Total ventes avant remise": 70000.0,
        }])

        self.assertAlmostEqual(result.iloc[0]["TOTAL VENTE"], 60000.0)
        self.assertAlmostEqual(result.iloc[0]["Total ventes avant remise"], 70000.0)


if __name__ == "__main__":
    unittest.main()
