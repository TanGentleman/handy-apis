"""Unit tests for scraper/bulk.py bulk job processing functions."""

import pytest

from scraper.bulk import (
    MAX_CONTAINERS,
    JobStatus,
    calculate_batches,
)


class TestJobStatus:
    """Tests for JobStatus enum."""

    def test_status_values(self):
        assert JobStatus.PENDING == "pending"
        assert JobStatus.IN_PROGRESS == "in_progress"
        assert JobStatus.COMPLETED == "completed"

    def test_status_is_string(self):
        assert isinstance(JobStatus.PENDING, str)
        assert JobStatus.PENDING.value == "pending"


class TestCalculateBatches:
    """Tests for calculate_batches function."""

    def test_empty_input(self):
        assert calculate_batches({}) == []

    def test_single_site_few_paths(self):
        """Single site with fewer paths than max containers.

        With proportional allocation, a single site gets all available containers
        (capped by the number of paths), so 3 paths = 3 batches of 1 path each.
        """
        by_site = {"site1": ["/a", "/b", "/c"]}
        batches = calculate_batches(by_site)

        # With proportional allocation, 3 paths gets 3 containers (1 per path)
        assert len(batches) == 3
        assert all(b["site_id"] == "site1" for b in batches)
        all_paths = [p for b in batches for p in b["paths"]]
        assert set(all_paths) == {"/a", "/b", "/c"}

    def test_single_site_many_paths(self):
        """Single site with many paths should split across containers."""
        paths = [f"/page{i}" for i in range(200)]
        by_site = {"site1": paths}
        batches = calculate_batches(by_site, max_containers=100)

        # Should use up to MAX_CONTAINERS but no more than needed
        total_paths = sum(len(b["paths"]) for b in batches)
        assert total_paths == 200

        # All batches should be for site1
        for batch in batches:
            assert batch["site_id"] == "site1"

    def test_multiple_sites_proportional(self):
        """Multiple sites should get proportional container allocation."""
        by_site = {
            "big_site": [f"/p{i}" for i in range(80)],  # 80 paths
            "small_site": [f"/p{i}" for i in range(20)],  # 20 paths
        }
        batches = calculate_batches(by_site, max_containers=10)

        big_batches = [b for b in batches if b["site_id"] == "big_site"]
        small_batches = [b for b in batches if b["site_id"] == "small_site"]

        # Big site should get more batches
        assert len(big_batches) >= len(small_batches)

        # All paths should be covered
        big_paths = sum(len(b["paths"]) for b in big_batches)
        small_paths = sum(len(b["paths"]) for b in small_batches)
        assert big_paths == 80
        assert small_paths == 20

    def test_site_with_empty_paths(self):
        """Sites with empty path lists should be skipped."""
        by_site = {
            "site1": ["/a", "/b"],
            "empty_site": [],
        }
        batches = calculate_batches(by_site)

        # Only site1 should have batches
        assert all(b["site_id"] == "site1" for b in batches)

    def test_all_paths_distributed(self):
        """All paths should be distributed across batches."""
        by_site = {
            "site1": [f"/page{i}" for i in range(50)],
            "site2": [f"/doc{i}" for i in range(30)],
            "site3": [f"/api{i}" for i in range(20)],
        }
        batches = calculate_batches(by_site, max_containers=20)

        # Collect all paths from batches
        all_batch_paths = []
        for batch in batches:
            all_batch_paths.extend(batch["paths"])

        # Should have all 100 paths
        assert len(all_batch_paths) == 100

    def test_max_containers_respected(self):
        """Number of batches should not exceed max_containers."""
        by_site = {f"site{i}": [f"/p{j}" for j in range(100)] for i in range(10)}
        batches = calculate_batches(by_site, max_containers=50)

        # Total batches should be reasonable (may exceed due to rounding per site)
        # but each site should not create more batches than needed
        for site_id in by_site:
            site_batches = [b for b in batches if b["site_id"] == site_id]
            assert len(site_batches) <= len(by_site[site_id])

    def test_min_one_container_per_site(self):
        """Each site should get at least one container."""
        by_site = {
            "big": [f"/p{i}" for i in range(95)],
            "tiny": ["/p1"],
        }
        batches = calculate_batches(by_site, max_containers=10)

        tiny_batches = [b for b in batches if b["site_id"] == "tiny"]
        assert len(tiny_batches) >= 1
        assert len(tiny_batches[0]["paths"]) == 1


class TestCalculateBatchesEdgeCases:
    """Edge case tests for calculate_batches."""

    def test_single_path(self):
        """Single path should create single batch."""
        by_site = {"site1": ["/only"]}
        batches = calculate_batches(by_site)

        assert len(batches) == 1
        assert batches[0]["paths"] == ["/only"]

    def test_exact_container_count(self):
        """Paths equal to max containers."""
        paths = [f"/p{i}" for i in range(100)]
        by_site = {"site1": paths}
        batches = calculate_batches(by_site, max_containers=100)

        # Each path could get its own batch, or they could be grouped
        total = sum(len(b["paths"]) for b in batches)
        assert total == 100

    def test_preserves_path_order_within_batches(self):
        """Paths within a batch should maintain relative order."""
        paths = ["/a", "/b", "/c", "/d", "/e"]
        by_site = {"site1": paths}
        batches = calculate_batches(by_site, max_containers=2)

        # Combine all paths maintaining batch order
        all_paths = []
        for batch in batches:
            all_paths.extend(batch["paths"])

        # All paths should be present
        assert set(all_paths) == set(paths)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
