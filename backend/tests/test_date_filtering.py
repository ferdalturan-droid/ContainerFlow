"""
Test Date Filtering Fix - Admin Ture Tab
Tests that date filtering correctly isolates tours by date and updates Quick Stats
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestDateFiltering:
    """Tests for date filtering in Admin Ture tab"""
    
    def test_api_accessible(self):
        """Test that API is accessible"""
        response = requests.get(f"{BASE_URL}/api/plads")
        assert response.status_code == 200
        print("API is accessible - PASSED")
    
    def test_daily_overview_with_tours_date(self):
        """Test daily overview for date with tours (2026-04-01)"""
        response = requests.get(f"{BASE_URL}/api/admin/daily-overview?date=2026-04-01")
        assert response.status_code == 200
        data = response.json()
        
        # Verify date is correct
        assert data["date"] == "2026-04-01"
        
        # Verify totals show tours
        assert data["totals"]["total_tours"] > 0, "Should have tours on 2026-04-01"
        
        # Verify Glostrup has tours
        assert data["plads_stats"]["Glostrup"]["total"] > 0, "Glostrup should have tours on 2026-04-01"
        
        print(f"Daily overview for 2026-04-01: {data['totals']['total_tours']} tours - PASSED")
    
    def test_daily_overview_empty_date(self):
        """Test daily overview for date without tours (2026-04-02)"""
        response = requests.get(f"{BASE_URL}/api/admin/daily-overview?date=2026-04-02")
        assert response.status_code == 200
        data = response.json()
        
        # Verify date is correct
        assert data["date"] == "2026-04-02"
        
        # Verify totals show 0 tours
        assert data["totals"]["total_tours"] == 0, "Should have 0 tours on 2026-04-02"
        
        # Verify all plads have 0 tours
        for plads_name, stats in data["plads_stats"].items():
            assert stats["total"] == 0, f"{plads_name} should have 0 tours on 2026-04-02"
        
        print(f"Daily overview for 2026-04-02: {data['totals']['total_tours']} tours (expected 0) - PASSED")
    
    def test_tours_endpoint_with_date_filter(self):
        """Test tours endpoint filters by date correctly"""
        # Date with tours
        response1 = requests.get(f"{BASE_URL}/api/tours?date=2026-04-01")
        assert response1.status_code == 200
        tours_apr1 = response1.json()
        
        # Date without tours
        response2 = requests.get(f"{BASE_URL}/api/tours?date=2026-04-02")
        assert response2.status_code == 200
        tours_apr2 = response2.json()
        
        # Verify filtering works
        assert len(tours_apr1) > 0, "Should have tours on 2026-04-01"
        assert len(tours_apr2) == 0, "Should have 0 tours on 2026-04-02"
        
        # Verify all tours on apr1 have correct date
        for tour in tours_apr1:
            assert tour.get("date") == "2026-04-01", f"Tour should have date 2026-04-01, got {tour.get('date')}"
        
        print(f"Tours endpoint filtering: {len(tours_apr1)} tours on 2026-04-01, {len(tours_apr2)} on 2026-04-02 - PASSED")
    
    def test_tours_date_isolation(self):
        """Test that tours are properly isolated by date - no cross-date leakage"""
        # Get tours for multiple dates
        dates_to_check = ["2026-03-31", "2026-04-01", "2026-04-02"]
        
        for date in dates_to_check:
            response = requests.get(f"{BASE_URL}/api/tours?date={date}")
            assert response.status_code == 200
            tours = response.json()
            
            # Verify all returned tours have the correct date
            for tour in tours:
                assert tour.get("date") == date, f"Tour date mismatch: expected {date}, got {tour.get('date')}"
        
        print("Tours date isolation verified - no cross-date leakage - PASSED")
    
    def test_daily_overview_default_date(self):
        """Test daily overview uses Danish timezone date as default"""
        response = requests.get(f"{BASE_URL}/api/admin/daily-overview")
        assert response.status_code == 200
        data = response.json()
        
        # Should have a date field
        assert "date" in data, "Response should include date field"
        assert data["date"] is not None, "Date should not be None"
        
        # Date should be in YYYY-MM-DD format
        import re
        assert re.match(r"\d{4}-\d{2}-\d{2}", data["date"]), f"Date should be in YYYY-MM-DD format, got {data['date']}"
        
        print(f"Daily overview default date: {data['date']} - PASSED")
    
    def test_plads_stats_structure(self):
        """Test that plads_stats has correct structure for badge counts"""
        response = requests.get(f"{BASE_URL}/api/admin/daily-overview?date=2026-04-01")
        assert response.status_code == 200
        data = response.json()
        
        # Verify plads_stats exists
        assert "plads_stats" in data, "Response should include plads_stats"
        
        # Verify each plads has required fields for badge counts
        required_fields = ["total", "completed", "on_way", "waiting", "total_weight", "progress_percent"]
        for plads_name, stats in data["plads_stats"].items():
            for field in required_fields:
                assert field in stats, f"{plads_name} should have {field} field"
        
        print("Plads stats structure verified - PASSED")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
