"""
Test Daily Separation System - Each day must be a completely separate workspace
Tests:
1. GET /api/tours?date=YYYY-MM-DD returns only tours for that specific date
2. Different dates return different tour sets (no mixing)
3. Empty dates return empty arrays
4. POST /api/tours without date auto-fills today's date
5. Admin and Driver login work with code 3030
"""

import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestDailySeparation:
    """Test that tours are properly separated by date"""
    
    def test_tours_for_april_1_returns_only_april_1_tours(self):
        """GET /api/tours?date=2026-04-01 returns only tours for April 1"""
        response = requests.get(f"{BASE_URL}/api/tours?date=2026-04-01")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        tours = response.json()
        assert isinstance(tours, list), "Response should be a list"
        
        # All tours should have date 2026-04-01
        for tour in tours:
            assert tour.get("date") == "2026-04-01", f"Tour {tour.get('id')} has wrong date: {tour.get('date')}"
        
        print(f"✓ Found {len(tours)} tours for 2026-04-01, all with correct date")
    
    def test_tours_for_april_2_returns_empty(self):
        """GET /api/tours?date=2026-04-02 returns 0 tours (empty day)"""
        response = requests.get(f"{BASE_URL}/api/tours?date=2026-04-02")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        tours = response.json()
        assert isinstance(tours, list), "Response should be a list"
        assert len(tours) == 0, f"Expected 0 tours for empty day, got {len(tours)}"
        
        print("✓ 2026-04-02 returns empty array (no tours)")
    
    def test_tours_for_march_31_returns_only_march_31_tours(self):
        """GET /api/tours?date=2026-03-31 returns only tours for March 31"""
        response = requests.get(f"{BASE_URL}/api/tours?date=2026-03-31")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        tours = response.json()
        assert isinstance(tours, list), "Response should be a list"
        
        # All tours should have date 2026-03-31
        for tour in tours:
            assert tour.get("date") == "2026-03-31", f"Tour {tour.get('id')} has wrong date: {tour.get('date')}"
        
        print(f"✓ Found {len(tours)} tours for 2026-03-31, all with correct date")
    
    def test_no_tour_leakage_between_dates(self):
        """Tours from one date should not appear in another date's query"""
        # Get tours for both dates
        response_apr1 = requests.get(f"{BASE_URL}/api/tours?date=2026-04-01")
        response_mar31 = requests.get(f"{BASE_URL}/api/tours?date=2026-03-31")
        
        assert response_apr1.status_code == 200
        assert response_mar31.status_code == 200
        
        tours_apr1 = response_apr1.json()
        tours_mar31 = response_mar31.json()
        
        # Get IDs from each set
        ids_apr1 = set(t.get("id") for t in tours_apr1)
        ids_mar31 = set(t.get("id") for t in tours_mar31)
        
        # No overlap should exist
        overlap = ids_apr1.intersection(ids_mar31)
        assert len(overlap) == 0, f"Found {len(overlap)} tours appearing in both dates: {overlap}"
        
        print(f"✓ No tour leakage: {len(ids_apr1)} tours on Apr 1, {len(ids_mar31)} tours on Mar 31, 0 overlap")
    
    def test_create_tour_without_date_uses_today(self):
        """POST /api/tours without date auto-fills today's date"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Create tour without specifying date
        tour_data = {
            "fraction": "TEST_DailySeparation_AutoDate",
            "facility": "Test Facility",
            "address": "Test Address 123"
        }
        
        response = requests.post(f"{BASE_URL}/api/tours", json=tour_data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        created_tour = response.json()
        assert created_tour.get("date") == today, f"Expected date {today}, got {created_tour.get('date')}"
        
        # Cleanup
        tour_id = created_tour.get("id")
        if tour_id:
            requests.delete(f"{BASE_URL}/api/tours/{tour_id}")
        
        print(f"✓ Tour created without date defaults to today: {today}")
    
    def test_create_tour_with_specific_date(self):
        """POST /api/tours with specific date uses that date"""
        specific_date = "2026-05-15"
        
        tour_data = {
            "date": specific_date,
            "fraction": "TEST_DailySeparation_SpecificDate",
            "facility": "Test Facility",
            "address": "Test Address 456"
        }
        
        response = requests.post(f"{BASE_URL}/api/tours", json=tour_data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        created_tour = response.json()
        assert created_tour.get("date") == specific_date, f"Expected date {specific_date}, got {created_tour.get('date')}"
        
        # Verify it appears in that date's query
        response_check = requests.get(f"{BASE_URL}/api/tours?date={specific_date}")
        assert response_check.status_code == 200
        tours = response_check.json()
        tour_ids = [t.get("id") for t in tours]
        assert created_tour.get("id") in tour_ids, "Created tour should appear in date-filtered query"
        
        # Cleanup
        tour_id = created_tour.get("id")
        if tour_id:
            requests.delete(f"{BASE_URL}/api/tours/{tour_id}")
        
        print(f"✓ Tour created with specific date {specific_date} appears in correct date query")


class TestAuthLogin:
    """Test Admin and Driver login with code 3030"""
    
    def test_admin_login_with_correct_password(self):
        """POST /api/admin/login with password 3030 returns success"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={"password": "3030"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True, f"Expected success=True, got {data}"
        
        print("✓ Admin login with password 3030 works")
    
    def test_admin_login_with_wrong_password(self):
        """POST /api/admin/login with wrong password returns 401"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={"password": "wrong"})
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        
        print("✓ Admin login with wrong password returns 401")
    
    def test_driver_login_with_correct_code(self):
        """POST /api/driver/login with name + code 3030 returns success"""
        response = requests.post(f"{BASE_URL}/api/driver/login", json={
            "name": "Test Driver",
            "code": "3030"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True, f"Expected success=True, got {data}"
        assert data.get("driver_name") == "Test Driver", f"Expected driver_name='Test Driver', got {data}"
        
        print("✓ Driver login with name + code 3030 works")
    
    def test_driver_login_with_wrong_code(self):
        """POST /api/driver/login with wrong code returns 401"""
        response = requests.post(f"{BASE_URL}/api/driver/login", json={
            "name": "Test Driver",
            "code": "wrong"
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        
        print("✓ Driver login with wrong code returns 401")
    
    def test_driver_login_without_name(self):
        """POST /api/driver/login without name returns 400"""
        response = requests.post(f"{BASE_URL}/api/driver/login", json={
            "name": "",
            "code": "3030"
        })
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        
        print("✓ Driver login without name returns 400")


class TestTourDateFiltering:
    """Additional tests for tour date filtering edge cases"""
    
    def test_tours_without_date_filter_returns_all(self):
        """GET /api/tours without date filter returns tours (may include multiple dates)"""
        response = requests.get(f"{BASE_URL}/api/tours")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        tours = response.json()
        assert isinstance(tours, list), "Response should be a list"
        
        # Should return some tours
        print(f"✓ GET /api/tours without date filter returns {len(tours)} tours")
    
    def test_tours_with_invalid_date_format(self):
        """GET /api/tours with invalid date format should still work (returns empty or all)"""
        response = requests.get(f"{BASE_URL}/api/tours?date=invalid-date")
        # Should not crash - either returns empty or ignores invalid date
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        tours = response.json()
        assert isinstance(tours, list), "Response should be a list"
        
        print(f"✓ GET /api/tours with invalid date format returns {len(tours)} tours (graceful handling)")
    
    def test_tours_with_future_date_returns_empty(self):
        """GET /api/tours with far future date returns empty"""
        future_date = "2030-12-31"
        response = requests.get(f"{BASE_URL}/api/tours?date={future_date}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        tours = response.json()
        assert isinstance(tours, list), "Response should be a list"
        assert len(tours) == 0, f"Expected 0 tours for future date, got {len(tours)}"
        
        print(f"✓ GET /api/tours with future date {future_date} returns empty")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
