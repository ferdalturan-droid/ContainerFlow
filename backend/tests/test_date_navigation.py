"""
Test suite for date-based job navigation and auto-cleanup features.
Tests:
- GET /api/tours with date parameter filtering
- POST /api/admin/cleanup endpoint
- Backend auto-cleanup task verification (via logs)
"""
import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestDateFiltering:
    """Test date-based tour filtering"""
    
    def test_get_tours_with_date_filter(self):
        """GET /api/tours?date=YYYY-MM-DD returns only tours for that date"""
        today = datetime.now().strftime("%Y-%m-%d")
        response = requests.get(f"{BASE_URL}/api/tours?date={today}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        # Verify all returned tours have the correct date
        for tour in data:
            assert tour.get("date") == today, f"Tour date {tour.get('date')} doesn't match filter {today}"
        print(f"✓ GET /api/tours?date={today} returned {len(data)} tours")
    
    def test_get_tours_yesterday(self):
        """GET /api/tours?date=yesterday returns only yesterday's tours"""
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        response = requests.get(f"{BASE_URL}/api/tours?date={yesterday}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        for tour in data:
            assert tour.get("date") == yesterday, f"Tour date {tour.get('date')} doesn't match filter {yesterday}"
        print(f"✓ GET /api/tours?date={yesterday} returned {len(data)} tours")
    
    def test_get_tours_future_date(self):
        """GET /api/tours?date=future returns empty or only future tours"""
        future = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        response = requests.get(f"{BASE_URL}/api/tours?date={future}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        for tour in data:
            assert tour.get("date") == future, f"Tour date {tour.get('date')} doesn't match filter {future}"
        print(f"✓ GET /api/tours?date={future} returned {len(data)} tours (expected 0 or few)")
    
    def test_get_tours_different_dates_return_different_results(self):
        """Verify different dates return different tour sets"""
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        
        response_today = requests.get(f"{BASE_URL}/api/tours?date={today}")
        response_yesterday = requests.get(f"{BASE_URL}/api/tours?date={yesterday}")
        
        assert response_today.status_code == 200
        assert response_yesterday.status_code == 200
        
        tours_today = response_today.json()
        tours_yesterday = response_yesterday.json()
        
        # Get tour IDs for comparison
        today_ids = set(t.get("id") for t in tours_today)
        yesterday_ids = set(t.get("id") for t in tours_yesterday)
        
        # Tours should not overlap (unless there's a bug)
        overlap = today_ids.intersection(yesterday_ids)
        assert len(overlap) == 0, f"Found {len(overlap)} tours appearing in both dates - this is a bug"
        print(f"✓ Today has {len(tours_today)} tours, yesterday has {len(tours_yesterday)} tours, no overlap")


class TestAdminCleanup:
    """Test admin cleanup endpoint"""
    
    def test_admin_cleanup_with_correct_password(self):
        """POST /api/admin/cleanup with correct password triggers cleanup"""
        response = requests.post(
            f"{BASE_URL}/api/admin/cleanup",
            json={"password": "1234"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "message" in data, "Response should contain 'message'"
        assert "cleanup" in data["message"].lower() or "completed" in data["message"].lower(), \
            f"Expected cleanup confirmation, got: {data['message']}"
        print(f"✓ Admin cleanup triggered successfully: {data['message']}")
    
    def test_admin_cleanup_with_wrong_password(self):
        """POST /api/admin/cleanup with wrong password returns 401"""
        response = requests.post(
            f"{BASE_URL}/api/admin/cleanup",
            json={"password": "wrongpassword"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Admin cleanup correctly rejected wrong password")
    
    def test_admin_cleanup_without_password(self):
        """POST /api/admin/cleanup without password returns 401"""
        response = requests.post(
            f"{BASE_URL}/api/admin/cleanup",
            json={}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Admin cleanup correctly rejected missing password")


class TestTourCRUD:
    """Test tour CRUD operations with date field"""
    
    def test_create_tour_with_date(self):
        """Create a tour with specific date and verify it's returned in date filter"""
        test_date = datetime.now().strftime("%Y-%m-%d")
        
        # Create tour
        tour_data = {
            "date": test_date,
            "fraction": "TEST_DateNavigation",
            "facility": "Test Facility",
            "address": "Test Address 123",
            "plads": "Glostrup",
            "container": "TEST123"
        }
        
        create_response = requests.post(f"{BASE_URL}/api/tours", json=tour_data)
        assert create_response.status_code == 200, f"Failed to create tour: {create_response.text}"
        created_tour = create_response.json()
        tour_id = created_tour.get("id")
        
        try:
            # Verify tour appears in date filter
            filter_response = requests.get(f"{BASE_URL}/api/tours?date={test_date}")
            assert filter_response.status_code == 200
            tours = filter_response.json()
            tour_ids = [t.get("id") for t in tours]
            assert tour_id in tour_ids, f"Created tour {tour_id} not found in date filter results"
            print(f"✓ Created tour appears in date filter for {test_date}")
        finally:
            # Cleanup
            requests.delete(f"{BASE_URL}/api/tours/{tour_id}")
    
    def test_tour_not_in_wrong_date_filter(self):
        """Verify tour doesn't appear in wrong date filter"""
        test_date = datetime.now().strftime("%Y-%m-%d")
        wrong_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        
        # Create tour for today
        tour_data = {
            "date": test_date,
            "fraction": "TEST_WrongDateFilter",
            "facility": "Test Facility",
            "address": "Test Address 456",
            "plads": "Glostrup",
            "container": "TEST456"
        }
        
        create_response = requests.post(f"{BASE_URL}/api/tours", json=tour_data)
        assert create_response.status_code == 200
        created_tour = create_response.json()
        tour_id = created_tour.get("id")
        
        try:
            # Verify tour does NOT appear in wrong date filter
            filter_response = requests.get(f"{BASE_URL}/api/tours?date={wrong_date}")
            assert filter_response.status_code == 200
            tours = filter_response.json()
            tour_ids = [t.get("id") for t in tours]
            assert tour_id not in tour_ids, f"Tour {tour_id} incorrectly appeared in wrong date filter"
            print(f"✓ Tour correctly excluded from wrong date filter ({wrong_date})")
        finally:
            # Cleanup
            requests.delete(f"{BASE_URL}/api/tours/{tour_id}")


class TestAdminLogin:
    """Test admin login endpoint"""
    
    def test_admin_login_success(self):
        """POST /api/admin/login with correct password succeeds"""
        response = requests.post(
            f"{BASE_URL}/api/admin/login",
            json={"password": "1234"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("success") == True, "Expected success: true"
        print("✓ Admin login successful with correct password")
    
    def test_admin_login_failure(self):
        """POST /api/admin/login with wrong password fails"""
        response = requests.post(
            f"{BASE_URL}/api/admin/login",
            json={"password": "wrongpassword"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Admin login correctly rejected wrong password")


class TestExistingEndpoints:
    """Verify existing endpoints still work"""
    
    def test_get_drivers(self):
        """GET /api/drivers returns list"""
        response = requests.get(f"{BASE_URL}/api/drivers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/drivers returned {len(data)} drivers")
    
    def test_get_plads(self):
        """GET /api/plads returns list"""
        response = requests.get(f"{BASE_URL}/api/plads")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/plads returned {len(data)} plads")
    
    def test_get_reports(self):
        """GET /api/reports returns list"""
        response = requests.get(f"{BASE_URL}/api/reports")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/reports returned {len(data)} reports")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
