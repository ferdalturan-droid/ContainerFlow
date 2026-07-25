"""
Test Date Normalization Fix - Iteration 23
Tests the fix for tours mixing between different dates due to DD-MM-YYYY vs YYYY-MM-DD format inconsistency.
"""
import pytest
import requests
import os
import re

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestDateNormalization:
    """Test date normalization in tour creation and querying"""
    
    def test_get_tours_april_1_returns_correct_count(self):
        """GET /api/tours?date=2026-04-01 should return only April 1 tours (14 tours)"""
        response = requests.get(f"{BASE_URL}/api/tours?date=2026-04-01")
        assert response.status_code == 200
        tours = response.json()
        print(f"Tours for 2026-04-01: {len(tours)}")
        assert len(tours) == 14, f"Expected 14 tours for April 1, got {len(tours)}"
        # Verify all tours have correct date
        for tour in tours:
            assert tour.get('date') == '2026-04-01', f"Tour {tour.get('id')} has wrong date: {tour.get('date')}"
    
    def test_get_tours_april_2_returns_empty(self):
        """GET /api/tours?date=2026-04-02 should return 0 tours (empty day)"""
        response = requests.get(f"{BASE_URL}/api/tours?date=2026-04-02")
        assert response.status_code == 200
        tours = response.json()
        print(f"Tours for 2026-04-02: {len(tours)}")
        assert len(tours) == 0, f"Expected 0 tours for April 2, got {len(tours)}"
    
    def test_get_tours_march_18_returns_correct_count(self):
        """GET /api/tours?date=2026-03-18 should return March 18 tours (23 tours)"""
        response = requests.get(f"{BASE_URL}/api/tours?date=2026-03-18")
        assert response.status_code == 200
        tours = response.json()
        print(f"Tours for 2026-03-18: {len(tours)}")
        assert len(tours) == 23, f"Expected 23 tours for March 18, got {len(tours)}"
        # Verify all tours have correct date
        for tour in tours:
            assert tour.get('date') == '2026-03-18', f"Tour {tour.get('id')} has wrong date: {tour.get('date')}"
    
    def test_no_dd_mm_yyyy_dates_in_database(self):
        """No DD-MM-YYYY format dates should exist in database anymore"""
        response = requests.get(f"{BASE_URL}/api/tours?limit=500")
        assert response.status_code == 200
        tours = response.json()
        
        dd_mm_yyyy_pattern = re.compile(r'^\d{1,2}-\d{1,2}-\d{4}$')
        bad_dates = [t for t in tours if dd_mm_yyyy_pattern.match(t.get('date', ''))]
        
        print(f"Total tours: {len(tours)}")
        print(f"Tours with DD-MM-YYYY format: {len(bad_dates)}")
        
        assert len(bad_dates) == 0, f"Found {len(bad_dates)} tours with DD-MM-YYYY format"
    
    def test_create_tour_with_dd_mm_yyyy_normalizes(self):
        """POST /api/tours with DD-MM-YYYY date should auto-normalize to YYYY-MM-DD"""
        response = requests.post(f"{BASE_URL}/api/tours", json={
            "date": "15-04-2026",
            "fraction": "TEST_NORMALIZE_SINGLE",
            "facility": "Test Facility",
            "address": "Test Address"
        })
        assert response.status_code == 200
        tour = response.json()
        
        print(f"Created tour with date: {tour.get('date')}")
        assert tour.get('date') == '2026-04-15', f"Expected 2026-04-15, got {tour.get('date')}"
        
        # Cleanup
        tour_id = tour.get('id')
        requests.delete(f"{BASE_URL}/api/tours/{tour_id}")
    
    def test_create_tour_with_slash_format_normalizes(self):
        """POST /api/tours with DD/MM/YYYY date should auto-normalize to YYYY-MM-DD"""
        response = requests.post(f"{BASE_URL}/api/tours", json={
            "date": "16/04/2026",
            "fraction": "TEST_NORMALIZE_SLASH",
            "facility": "Test Facility",
            "address": "Test Address"
        })
        assert response.status_code == 200
        tour = response.json()
        
        print(f"Created tour with date: {tour.get('date')}")
        assert tour.get('date') == '2026-04-16', f"Expected 2026-04-16, got {tour.get('date')}"
        
        # Cleanup
        tour_id = tour.get('id')
        requests.delete(f"{BASE_URL}/api/tours/{tour_id}")
    
    def test_create_tour_with_dot_format_normalizes(self):
        """POST /api/tours with DD.MM.YYYY date should auto-normalize to YYYY-MM-DD"""
        response = requests.post(f"{BASE_URL}/api/tours", json={
            "date": "17.04.2026",
            "fraction": "TEST_NORMALIZE_DOT",
            "facility": "Test Facility",
            "address": "Test Address"
        })
        assert response.status_code == 200
        tour = response.json()
        
        print(f"Created tour with date: {tour.get('date')}")
        assert tour.get('date') == '2026-04-17', f"Expected 2026-04-17, got {tour.get('date')}"
        
        # Cleanup
        tour_id = tour.get('id')
        requests.delete(f"{BASE_URL}/api/tours/{tour_id}")
    
    def test_bulk_create_tours_normalizes_dates(self):
        """POST /api/tours/bulk should normalize all date formats"""
        response = requests.post(f"{BASE_URL}/api/tours/bulk", json=[
            {"date": "20-04-2026", "fraction": "TEST_BULK_DD_MM", "facility": "Test 1", "address": "Addr 1"},
            {"date": "21/04/2026", "fraction": "TEST_BULK_SLASH", "facility": "Test 2", "address": "Addr 2"},
            {"date": "22.04.2026", "fraction": "TEST_BULK_DOT", "facility": "Test 3", "address": "Addr 3"},
            {"date": "2026-04-23", "fraction": "TEST_BULK_ISO", "facility": "Test 4", "address": "Addr 4"}
        ])
        assert response.status_code == 200
        tours = response.json()
        
        assert len(tours) == 4, f"Expected 4 tours, got {len(tours)}"
        
        expected_dates = ['2026-04-20', '2026-04-21', '2026-04-22', '2026-04-23']
        for i, tour in enumerate(tours):
            print(f"Tour {i+1}: date={tour.get('date')}, fraction={tour.get('fraction')}")
            assert tour.get('date') == expected_dates[i], f"Expected {expected_dates[i]}, got {tour.get('date')}"
        
        # Cleanup
        for tour in tours:
            requests.delete(f"{BASE_URL}/api/tours/{tour.get('id')}")
    
    def test_query_with_dd_mm_yyyy_normalizes(self):
        """GET /api/tours?date=01-04-2026 should normalize query and return correct tours"""
        # Query with DD-MM-YYYY format
        response = requests.get(f"{BASE_URL}/api/tours?date=01-04-2026")
        assert response.status_code == 200
        tours = response.json()
        
        print(f"Tours for query '01-04-2026': {len(tours)}")
        # Should return same as 2026-04-01 query (14 tours)
        assert len(tours) == 14, f"Expected 14 tours, got {len(tours)}"


class TestDriverLogin:
    """Test driver login functionality"""
    
    def test_driver_login_with_name_and_code(self):
        """Driver login with name + code 3030 should work"""
        response = requests.post(f"{BASE_URL}/api/driver/login", json={
            "name": "Test Driver",
            "code": "3030"
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get('success') == True
        assert data.get('driver_name') == "Test Driver"
    
    def test_driver_login_wrong_code_fails(self):
        """Driver login with wrong code should fail"""
        response = requests.post(f"{BASE_URL}/api/driver/login", json={
            "name": "Test Driver",
            "code": "9999"
        })
        assert response.status_code == 401


class TestAdminLogin:
    """Test admin login functionality"""
    
    def test_admin_login_with_correct_password(self):
        """Admin login with password 3030 should work"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={
            "password": "3030"
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get('success') == True
    
    def test_admin_login_wrong_password_fails(self):
        """Admin login with wrong password should fail"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={
            "password": "wrong"
        })
        assert response.status_code == 401


class TestDateDistribution:
    """Verify date distribution matches expected values"""
    
    def test_date_distribution(self):
        """Verify tour counts per date match expected distribution"""
        expected = {
            '2026-03-18': 23,
            '2026-03-19': 3,
            '2026-03-20': 24,
            '2026-03-22': 14,
            '2026-03-23': 15,
            '2026-03-31': 26,
            '2026-04-01': 14
        }
        
        for date, expected_count in expected.items():
            response = requests.get(f"{BASE_URL}/api/tours?date={date}")
            assert response.status_code == 200
            tours = response.json()
            actual_count = len(tours)
            print(f"Date {date}: expected={expected_count}, actual={actual_count}")
            # Allow some variance due to test data changes
            assert abs(actual_count - expected_count) <= 5, f"Date {date}: expected ~{expected_count}, got {actual_count}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
