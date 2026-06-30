"""Tests unitarios para costos de transacción BMV (KB-003)."""
import numpy as np
import pytest

from src.ml.shared.evaluators.metrics import Metrics
from src.ml.shared.evaluators.backtester import Backtester


class TestTransactionCosts:
    def test_round_trip_cost_matches_bmv_defaults(self):
        cost = Metrics.round_trip_cost(0.0025, 0.0005)
        assert cost == pytest.approx(0.006, rel=1e-6)

    def test_trade_with_costs_reduces_return(self):
        gross = 0.05
        net = Metrics.net_return(gross, commission_pct=0.0025, slippage_pct=0.0005)
        assert net < gross
        assert net == pytest.approx(gross - Metrics.round_trip_cost(0.0025, 0.0005))

    def test_apply_costs_to_returns_only_on_trades(self):
        gross = np.array([0.02, 0.0, -0.01, 0.03])
        net = Metrics.apply_costs_to_returns(gross, trade_mask=np.array([True, False, True, True]))
        round_trip = Metrics.round_trip_cost()
        assert net[0] == pytest.approx(0.02 - round_trip)
        assert net[1] == 0.0
        assert net[2] == pytest.approx(-0.01 - round_trip)
        assert net[3] == pytest.approx(0.03 - round_trip)

    def test_backtester_simulated_trade_net_below_gross(self):
        backtester = Backtester(
            initial_train_days=10,
            retrain_frequency=5,
            test_days=3,
            commission_pct=0.0025,
            slippage_pct=0.0005,
        )
        y_true = np.array([100.0, 102.0, 104.0, 103.0])
        y_pred = np.array([100.0, 101.5, 105.0, 104.0])

        gross, net = backtester._simulate_directional_returns(y_true, y_pred)
        active = gross != 0
        assert active.any()
        assert (net[active] < gross[active]).all()

    def test_dual_metrics_sharpe_net_below_gross_with_costs(self):
        gross = np.array([0.01, 0.02, -0.005, 0.015, 0.008])
        net = Metrics.apply_costs_to_returns(gross, trade_mask=np.ones(len(gross), dtype=bool))
        dual = Metrics.calculate_dual_metrics(gross, net, periods_per_year=252 / 5)
        assert dual["sharpe_net"] <= dual["sharpe_gross"]
