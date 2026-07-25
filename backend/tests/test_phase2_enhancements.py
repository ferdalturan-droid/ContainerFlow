"""
Test suite for Phase 2 enhancements:
- Tour image endpoint (/api/tours/{tour_id}/image)
- has_receipt_image flag in driver-archive
- Materials endpoint verification (27 materials including 3 new ones)
- Admin statistics with order_stats
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestMaterialsEnhancements:
    """Test /api/materials endpoint - verify 27 materials including 3 new ones"""
    
    def test_materials_returns_200(self):
        """GET /api/materials should return 200"""
        response = requests.get(f"{BASE_URL}/api/materials")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASSED: GET /api/materials returns 200")
    
    def test_materials_count_exactly_27(self):
        """GET /api/materials should return exactly 27 materials"""
        response = requests.get(f"{BASE_URL}/api/materials")
        data = response.json()
        materials = data.get("materials", [])
        assert len(materials) == 27, f"Expected 27 materials, got {len(materials)}"
        print(f"PASSED: Materials count is exactly 27")
    
    def test_materials_contains_new_items(self):
        """Verify 3 new materials are present: Haveaffald, Elektronikaffald (WEEE), Vinduer / Glasaffald"""
        response = requests.get(f"{BASE_URL}/api/materials")
        data = response.json()
        materials = data.get("materials", [])
        
        new_materials = [
            "Haveaffald",
            "Elektronikaffald (WEEE)",
            "Vinduer / Glasaffald"
        ]
        
        for material in new_materials:
            assert material in materials, f"New material '{material}' not found in list"
        print(f"PASSED: All 3 new materials present: {new_materials}")


class TestTourImageEndpoint:
    """Test /api/tours/{tour_id}/image endpoint"""
    
    def test_tour_image_nonexistent_tour(self):
        """GET /api/tours/{tour_id}/image with non-existent tour should return 404"""
        response = requests.get(f"{BASE_URL}/api/tours/nonexistent-tour-id/image")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASSED: Non-existent tour returns 404")
    
    def test_tour_image_endpoint_structure(self):
        """Test tour image endpoint returns correct structure when tour exists"""
        # First get a tour ID from the tours list
        tours_response = requests.get(f"{BASE_URL}/api/tours")
        assert tours_response.status_code == 200
        tours = tours_response.json()
        
        if tours:
            tour_id = tours[0].get("id")
            if tour_id:
                response = requests.get(f"{BASE_URL}/api/tours/{tour_id}/image")
                assert response.status_code == 200, f"Expected 200, got {response.status_code}"
                data = response.json()
                
                # Verify response structure
                assert "image_data" in data, "Response should have 'image_data' key"
                assert "tour_id" in data, "Response should have 'tour_id' key"
                assert "plads" in data, "Response should have 'plads' key"
                assert "fraction" in data, "Response should have 'fraction' key"
                assert data["tour_id"] == tour_id, "tour_id should match requested ID"
                print(f"PASSED: Tour image endpoint returns correct structure for tour {tour_id}")
        else:
            pytest.skip("No tours available to test image endpoint")


class TestAdminStatisticsEnhancements:
    """Test /api/admin/statistics endpoint enhancements"""
    
    def test_statistics_returns_200(self):
        """GET /api/admin/statistics should return 200"""
        response = requests.get(f"{BASE_URL}/api/admin/statistics")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASSED: GET /api/admin/statistics returns 200")
    
    def test_statistics_has_all_required_fields(self):
        """Statistics should have jobs_per_day, driver_performance, material_usage, plads_stats, summary"""
        response = requests.get(f"{BASE_URL}/api/admin/statistics")
        data = response.json()
        
        required_fields = ["jobs_per_day", "driver_performance", "material_usage", "plads_stats", "summary"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        print(f"PASSED: Statistics has all required fields")
    
    def test_statistics_months_parameter_1(self):
        """Statistics should accept months=1 parameter"""
        response = requests.get(f"{BASE_URL}/api/admin/statistics?months=1")
        assert response.status_code == 200
        data = response.json()
        assert data.get("period_months") == 1
        print("PASSED: Statistics accepts months=1")
    
    def test_statistics_months_parameter_3(self):
        """Statistics should accept months=3 parameter"""
        response = requests.get(f"{BASE_URL}/api/admin/statistics?months=3")
        assert response.status_code == 200
        data = response.json()
        assert data.get("period_months") == 3
        print("PASSED: Statistics accepts months=3")
    
    def test_statistics_months_parameter_6(self):
        """Statistics should accept months=6 parameter"""
        response = requests.get(f"{BASE_URL}/api/admin/statistics?months=6")
        assert response.status_code == 200
        data = response.json()
        assert data.get("period_months") == 6
        print("PASSED: Statistics accepts months=6")
    
    def test_statistics_months_parameter_12(self):
        """Statistics should accept months=12 parameter"""
        response = requests.get(f"{BASE_URL}/api/admin/statistics?months=12")
        assert response.status_code == 200
        data = response.json()
        assert data.get("period_months") == 12
        print("PASSED: Statistics accepts months=12")


class TestDriverArchiveHasReceiptImage:
    """Test has_receipt_image flag in driver-archive endpoint"""
    
    def test_driver_archive_endpoint_exists(self):
        """GET /api/driver-archive should return 200"""
        # First get a driver name
        drivers_response = requests.get(f"{BASE_URL}/api/drivers")
        assert drivers_response.status_code == 200
        drivers = drivers_response.json()
        
        if drivers:
            driver_name = drivers[0].get("name")
            if driver_name:
                response = requests.get(f"{BASE_URL}/api/driver-archive/{driver_name}")
                assert response.status_code == 200, f"Expected 200, got {response.status_code}"
                print(f"PASSED: Driver archive endpoint works for driver: {driver_name}")
        else:
            pytest.skip("No drivers available to test archive endpoint")
    
    def test_driver_archive_tours_have_has_receipt_image_flag(self):
        """Tours in driver archive should have has_receipt_image flag"""
        # First get a driver name
        drivers_response = requests.get(f"{BASE_URL}/api/drivers")
        drivers = drivers_response.json()
        
        if drivers:
            driver_name = drivers[0].get("name")
            if driver_name:
                response = requests.get(f"{BASE_URL}/api/driver-archive/{driver_name}")
                data = response.json()
                
                # Response structure: {driver_name: str, days: [{date, sessions, reports, tours, receipts, receipt_ids}]}
                days = data.get("days", [])
                tours_found = False
                for day in days:
                    tours = day.get("tours", [])
                    for tour in tours:
                        tours_found = True
                        assert "has_receipt_image" in tour, f"Tour missing 'has_receipt_image' flag: {tour.get('id')}"
                        assert isinstance(tour["has_receipt_image"], bool), "has_receipt_image should be boolean"
                
                if tours_found:
                    print(f"PASSED: Tours in driver archive have has_receipt_image flag")
                else:
                    print(f"PASSED: Driver archive structure correct (no tours to verify flag)")
        else:
            pytest.skip("No drivers available to test archive endpoint")


class TestAdminLogin:
    """Test admin login functionality"""
    
    def test_admin_login_with_correct_password(self):
        """POST /api/admin/login with password 1234 should succeed"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={"password": "1234"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("success") == True, "Login should return success: true"
        print("PASSED: Admin login with password 1234 works")
    
    def test_admin_login_with_wrong_password(self):
        """POST /api/admin/login with wrong password should fail"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={"password": "wrong"})
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASSED: Admin login with wrong password returns 401")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
