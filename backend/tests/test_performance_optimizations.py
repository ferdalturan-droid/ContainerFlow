"""
Test Performance Optimizations for KORKMAN2 Driving Report App
Tests: N+1 fixes, batch queries, projections, limits, bulk operations, indexes
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAdminLogin:
    """Admin login endpoint tests"""
    
    def test_admin_login_success(self):
        """POST /api/admin/login with password 1234 returns success"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={"password": "1234"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("success") == True, f"Expected success=True, got {data}"
        print("PASSED: Admin login with password 1234")
    
    def test_admin_login_invalid_password(self):
        """POST /api/admin/login with wrong password returns 401"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={"password": "wrong"})
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASSED: Admin login rejects invalid password")


class TestAdminStatsBatchQuery:
    """Test admin/stats uses batch queries (N+1 fix)"""
    
    def test_admin_stats_returns_driver_list(self):
        """GET /api/admin/stats returns driver list with stats"""
        start_time = time.time()
        response = requests.get(f"{BASE_URL}/api/admin/stats")
        elapsed = time.time() - start_time
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        
        # Should have driver stats
        if len(data) > 0:
            driver = data[0]
            assert "driver_id" in driver, "Missing driver_id"
            assert "driver_name" in driver, "Missing driver_name"
            assert "total_tours" in driver, "Missing total_tours"
            assert "completed_tours" in driver, "Missing completed_tours"
            assert "today_tours" in driver, "Missing today_tours"
            print(f"PASSED: Admin stats returned {len(data)} drivers in {elapsed:.2f}s")
        else:
            print(f"PASSED: Admin stats returned empty list (no drivers) in {elapsed:.2f}s")
    
    def test_admin_stats_performance(self):
        """Admin stats should be fast (batch query optimization)"""
        # Run multiple times to check consistency
        times = []
        for _ in range(3):
            start = time.time()
            response = requests.get(f"{BASE_URL}/api/admin/stats")
            times.append(time.time() - start)
            assert response.status_code == 200
        
        avg_time = sum(times) / len(times)
        # Should complete in under 2 seconds with batch queries
        assert avg_time < 2.0, f"Admin stats too slow: {avg_time:.2f}s average"
        print(f"PASSED: Admin stats performance OK - avg {avg_time:.2f}s")


class TestToursProjection:
    """Test tours endpoint excludes heavy receipt_image data from list queries"""
    
    def test_tours_list_receipt_image_is_empty(self):
        """GET /api/tours?date=... returns tours with empty receipt_image (projection excludes actual data)"""
        response = requests.get(f"{BASE_URL}/api/tours", params={"date": "2026-03-20"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # The projection excludes receipt_image from DB query, but Pydantic adds default empty string
        # This is correct behavior - heavy base64 data is not transferred
        for tour in data:
            receipt_img = tour.get("receipt_image", "")
            # Should be empty string (default) not actual base64 data
            assert receipt_img == "" or len(receipt_img) < 100, f"receipt_image should be empty or minimal, got {len(receipt_img)} chars"
        
        print(f"PASSED: Tours list has empty receipt_image ({len(data)} tours checked)")
    
    def test_tours_limit_parameter(self):
        """GET /api/tours?date=...&limit=1 respects limit parameter"""
        response = requests.get(f"{BASE_URL}/api/tours", params={"date": "2026-03-20", "limit": 1})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert len(data) <= 1, f"Expected at most 1 tour, got {len(data)}"
        print(f"PASSED: Tours limit=1 respected ({len(data)} tours returned)")
    
    def test_tours_limit_larger(self):
        """GET /api/tours with limit=5 returns at most 5 tours"""
        response = requests.get(f"{BASE_URL}/api/tours", params={"limit": 5})
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 5, f"Expected at most 5 tours, got {len(data)}"
        print(f"PASSED: Tours limit=5 respected ({len(data)} tours returned)")


class TestDailyOverview:
    """Test admin/daily-overview with date filter and projections"""
    
    def test_daily_overview_today(self):
        """GET /api/admin/daily-overview returns today's data with plads_stats"""
        response = requests.get(f"{BASE_URL}/api/admin/daily-overview")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Check structure
        assert "date" in data, "Missing date field"
        assert "totals" in data, "Missing totals field"
        assert "plads_stats" in data, "Missing plads_stats field"
        assert "active_drivers" in data, "Missing active_drivers field"
        
        # Check totals structure
        totals = data["totals"]
        assert "total_tours" in totals, "Missing total_tours in totals"
        assert "completed" in totals, "Missing completed in totals"
        assert "progress_percent" in totals, "Missing progress_percent in totals"
        
        print(f"PASSED: Daily overview for today ({data['date']}) - {totals['total_tours']} tours")
    
    def test_daily_overview_specific_date(self):
        """GET /api/admin/daily-overview?date=2026-03-23 returns specific date data"""
        response = requests.get(f"{BASE_URL}/api/admin/daily-overview", params={"date": "2026-03-23"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert data["date"] == "2026-03-23", f"Expected date 2026-03-23, got {data['date']}"
        assert "plads_stats" in data, "Missing plads_stats"
        print(f"PASSED: Daily overview for 2026-03-23 - {data['totals']['total_tours']} tours")
    
    def test_daily_overview_plads_stats_structure(self):
        """Daily overview plads_stats has correct structure"""
        response = requests.get(f"{BASE_URL}/api/admin/daily-overview")
        assert response.status_code == 200
        data = response.json()
        
        plads_stats = data.get("plads_stats", {})
        for plads_name, stats in plads_stats.items():
            assert "total" in stats, f"Missing total in {plads_name}"
            assert "completed" in stats, f"Missing completed in {plads_name}"
            assert "on_way" in stats, f"Missing on_way in {plads_name}"
            assert "waiting" in stats, f"Missing waiting in {plads_name}"
            assert "progress_percent" in stats, f"Missing progress_percent in {plads_name}"
        
        print(f"PASSED: Daily overview plads_stats structure OK ({len(plads_stats)} plads)")


class TestReportHistoryBatchQuery:
    """Test reports/history uses batch queries (N+1 fix)"""
    
    def test_report_history_returns_data(self):
        """GET /api/reports/history?days=10 returns batch-fetched history"""
        start_time = time.time()
        response = requests.get(f"{BASE_URL}/api/reports/history", params={"days": 10})
        elapsed = time.time() - start_time
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        
        # Check structure if data exists
        if len(data) > 0:
            day = data[0]
            assert "date" in day, "Missing date"
            assert "total_tours" in day, "Missing total_tours"
            assert "completed_tours" in day, "Missing completed_tours"
            assert "driver_count" in day, "Missing driver_count"
        
        print(f"PASSED: Report history returned {len(data)} days in {elapsed:.2f}s")
    
    def test_report_history_performance(self):
        """Report history should be fast (batch query optimization)"""
        start = time.time()
        response = requests.get(f"{BASE_URL}/api/reports/history", params={"days": 30})
        elapsed = time.time() - start
        
        assert response.status_code == 200
        # Should complete in under 2 seconds with batch queries
        assert elapsed < 2.0, f"Report history too slow: {elapsed:.2f}s"
        print(f"PASSED: Report history performance OK - {elapsed:.2f}s for 30 days")


class TestReceiptsProjection:
    """Test receipts endpoint excludes image_data from list queries"""
    
    def test_receipts_list_excludes_image_data(self):
        """GET /api/receipts?limit=5 returns receipts WITHOUT image_data field"""
        response = requests.get(f"{BASE_URL}/api/receipts", params={"limit": 5})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Check that image_data is NOT in the response (projection)
        for receipt in data:
            assert "image_data" not in receipt, f"image_data should be excluded from list query"
        
        print(f"PASSED: Receipts list excludes image_data ({len(data)} receipts checked)")
    
    def test_receipts_limit_parameter(self):
        """GET /api/receipts?limit=5 respects limit parameter"""
        response = requests.get(f"{BASE_URL}/api/receipts", params={"limit": 5})
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 5, f"Expected at most 5 receipts, got {len(data)}"
        print(f"PASSED: Receipts limit=5 respected ({len(data)} receipts returned)")


class TestDriverArchive:
    """Test driver-archive endpoints"""
    
    def test_driver_archive_list(self):
        """GET /api/driver-archive returns driver list in {drivers: [...]} format"""
        response = requests.get(f"{BASE_URL}/api/driver-archive")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, dict), f"Expected dict, got {type(data)}"
        assert "drivers" in data, "Missing 'drivers' key"
        assert isinstance(data["drivers"], list), "drivers should be a list"
        print(f"PASSED: Driver archive returned {len(data['drivers'])} drivers")
    
    def test_driver_archive_specific_driver(self):
        """GET /api/driver-archive/Ferdal returns {driver_name, days} with tour data"""
        response = requests.get(f"{BASE_URL}/api/driver-archive/Ferdal")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, dict), f"Expected dict, got {type(data)}"
        assert "driver_name" in data, "Missing driver_name"
        assert "days" in data, "Missing days"
        assert isinstance(data["days"], list), "days should be a list"
        
        # Check structure if data exists
        days = data["days"]
        if len(days) > 0:
            day = days[0]
            assert "date" in day, "Missing date"
            assert "tours" in day, "Missing tours"
            # Tours should have empty receipt_image (projection excludes actual data)
            for tour in day.get("tours", []):
                receipt_img = tour.get("receipt_image", "")
                assert receipt_img == "" or len(receipt_img) < 100, "receipt_image should be empty"
        
        print(f"PASSED: Driver archive for Ferdal returned {len(days)} days")


class TestBulkOperations:
    """Test bulk insert and bulk_write operations"""
    
    def test_tours_bulk_create(self):
        """POST /api/tours/bulk creates multiple tours at once (insert_many)"""
        test_tours = [
            {
                "date": "2026-03-25",
                "fraction": "TEST_BULK_1",
                "facility": "Test Facility",
                "address": "Test Address 1",
                "plads": "Glostrup"
            },
            {
                "date": "2026-03-25",
                "fraction": "TEST_BULK_2",
                "facility": "Test Facility",
                "address": "Test Address 2",
                "plads": "Glostrup"
            }
        ]
        
        response = requests.post(f"{BASE_URL}/api/tours/bulk", json=test_tours)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        assert len(data) == 2, f"Expected 2 tours created, got {len(data)}"
        
        # Verify tours have IDs
        for tour in data:
            assert "id" in tour, "Created tour missing id"
        
        # Cleanup - delete test tours
        for tour in data:
            requests.delete(f"{BASE_URL}/api/tours/{tour['id']}")
        
        print("PASSED: Bulk tour create with insert_many")
    
    def test_tours_reorder_bulk_write(self):
        """PUT /api/tours/reorder with {tours: [{id, sort_order}]} works (bulk_write)"""
        # First create some test tours
        test_tours = [
            {"date": "2026-03-26", "fraction": "TEST_REORDER_1", "facility": "Test", "address": "Addr1", "plads": "Glostrup"},
            {"date": "2026-03-26", "fraction": "TEST_REORDER_2", "facility": "Test", "address": "Addr2", "plads": "Glostrup"}
        ]
        create_response = requests.post(f"{BASE_URL}/api/tours/bulk", json=test_tours)
        assert create_response.status_code == 200
        created_tours = create_response.json()
        
        # Now reorder them using the new format {tours: [...]}
        reorder_data = {
            "tours": [
                {"id": created_tours[0]["id"], "sort_order": 10},
                {"id": created_tours[1]["id"], "sort_order": 5}
            ]
        }
        
        response = requests.put(f"{BASE_URL}/api/tours/reorder", json=reorder_data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "message" in data, "Missing message in response"
        
        # Cleanup
        for tour in created_tours:
            requests.delete(f"{BASE_URL}/api/tours/{tour['id']}")
        
        print("PASSED: Tour reorder with bulk_write")
    
    def test_tours_reorder_empty_list(self):
        """PUT /api/tours/reorder with empty tours list returns appropriate message"""
        response = requests.put(f"{BASE_URL}/api/tours/reorder", json={"tours": []})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "message" in data
        print("PASSED: Tour reorder handles empty list")


class TestAPIHealth:
    """Basic API health checks"""
    
    def test_api_root(self):
        """GET /api/ returns API info"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        print("PASSED: API root endpoint")
    
    def test_drivers_endpoint(self):
        """GET /api/drivers returns list"""
        response = requests.get(f"{BASE_URL}/api/drivers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASSED: Drivers endpoint ({len(data)} drivers)")
    
    def test_plads_endpoint(self):
        """GET /api/plads returns list"""
        response = requests.get(f"{BASE_URL}/api/plads")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASSED: Plads endpoint ({len(data)} plads)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
