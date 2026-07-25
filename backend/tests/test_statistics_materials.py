"""
Test suite for Phase 2 features:
- Admin Statistics endpoint (/api/admin/statistics)
- Materials endpoint (/api/materials) - 27 Danish materials
- Admin login functionality
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestMaterialsEndpoint:
    """Test /api/materials endpoint - should return exactly 27 Danish materials"""
    
    def test_materials_returns_200(self):
        """GET /api/materials should return 200"""
        response = requests.get(f"{BASE_URL}/api/materials")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASSED: GET /api/materials returns 200")
    
    def test_materials_returns_exactly_27(self):
        """GET /api/materials should return exactly 27 materials"""
        response = requests.get(f"{BASE_URL}/api/materials")
        assert response.status_code == 200
        data = response.json()
        
        assert "materials" in data, "Response should have 'materials' key"
        materials = data["materials"]
        assert isinstance(materials, list), "Materials should be a list"
        assert len(materials) == 27, f"Expected 27 materials, got {len(materials)}"
        print(f"PASSED: GET /api/materials returns exactly 27 materials")
    
    def test_materials_contains_expected_items(self):
        """Verify some expected Danish materials are present"""
        response = requests.get(f"{BASE_URL}/api/materials")
        data = response.json()
        materials = data["materials"]
        
        # Check for some expected materials
        expected_samples = [
            "Trykimprægneret træ",
            "Beton til RGS",
            "Haveaffald",
            "Elektronikaffald (WEEE)",
            "Vinduer / Glasaffald"
        ]
        
        for expected in expected_samples:
            assert expected in materials, f"Expected material '{expected}' not found"
        print(f"PASSED: Materials contains expected Danish items")


class TestAdminLogin:
    """Test admin login with password 1234"""
    
    def test_admin_login_success(self):
        """POST /api/admin/login with password 1234 should succeed"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={"password": "1234"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("success") == True, "Login should return success: true"
        print("PASSED: Admin login with password 1234 works")
    
    def test_admin_login_wrong_password(self):
        """POST /api/admin/login with wrong password should fail"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={"password": "wrong"})
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASSED: Admin login with wrong password returns 401")


class TestAdminStatistics:
    """Test /api/admin/statistics endpoint"""
    
    def test_statistics_returns_200(self):
        """GET /api/admin/statistics should return 200"""
        response = requests.get(f"{BASE_URL}/api/admin/statistics")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASSED: GET /api/admin/statistics returns 200")
    
    def test_statistics_has_required_fields(self):
        """Statistics response should have all required fields"""
        response = requests.get(f"{BASE_URL}/api/admin/statistics")
        assert response.status_code == 200
        data = response.json()
        
        # Check top-level required fields
        required_fields = ["jobs_per_day", "driver_performance", "material_usage", "plads_stats", "summary"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        print(f"PASSED: Statistics has all required fields: {required_fields}")
    
    def test_statistics_summary_structure(self):
        """Summary should have total_tours, completed_tours, total_weight, total_drivers, active_drivers"""
        response = requests.get(f"{BASE_URL}/api/admin/statistics")
        data = response.json()
        summary = data.get("summary", {})
        
        summary_fields = ["total_tours", "completed_tours", "total_weight", "total_drivers", "active_drivers"]
        for field in summary_fields:
            assert field in summary, f"Summary missing field: {field}"
        
        # Verify types
        assert isinstance(summary["total_tours"], int), "total_tours should be int"
        assert isinstance(summary["completed_tours"], int), "completed_tours should be int"
        assert isinstance(summary["total_weight"], (int, float)), "total_weight should be numeric"
        assert isinstance(summary["total_drivers"], int), "total_drivers should be int"
        assert isinstance(summary["active_drivers"], int), "active_drivers should be int"
        print(f"PASSED: Summary has correct structure: {summary}")
    
    def test_statistics_jobs_per_day_structure(self):
        """jobs_per_day should be a list with date, total, completed, weight"""
        response = requests.get(f"{BASE_URL}/api/admin/statistics")
        data = response.json()
        jobs_per_day = data.get("jobs_per_day", [])
        
        assert isinstance(jobs_per_day, list), "jobs_per_day should be a list"
        assert len(jobs_per_day) == 30, f"Expected 30 days, got {len(jobs_per_day)}"
        
        if jobs_per_day:
            first_day = jobs_per_day[0]
            assert "date" in first_day, "Each day should have 'date'"
            assert "total" in first_day, "Each day should have 'total'"
            assert "completed" in first_day, "Each day should have 'completed'"
            assert "weight" in first_day, "Each day should have 'weight'"
        print(f"PASSED: jobs_per_day has correct structure (30 days)")
    
    def test_statistics_driver_performance_structure(self):
        """driver_performance should be a list with driver stats"""
        response = requests.get(f"{BASE_URL}/api/admin/statistics")
        data = response.json()
        driver_perf = data.get("driver_performance", [])
        
        assert isinstance(driver_perf, list), "driver_performance should be a list"
        
        if driver_perf:
            first_driver = driver_perf[0]
            expected_fields = ["name", "plate", "total_tours", "completed_tours", "total_weight", "work_days", "total_hours", "avg_tours_per_day"]
            for field in expected_fields:
                assert field in first_driver, f"Driver performance missing field: {field}"
        print(f"PASSED: driver_performance has correct structure ({len(driver_perf)} drivers)")
    
    def test_statistics_material_usage_structure(self):
        """material_usage should be a list with name, count, weight"""
        response = requests.get(f"{BASE_URL}/api/admin/statistics")
        data = response.json()
        material_usage = data.get("material_usage", [])
        
        assert isinstance(material_usage, list), "material_usage should be a list"
        
        if material_usage:
            first_material = material_usage[0]
            assert "name" in first_material, "Material should have 'name'"
            assert "count" in first_material, "Material should have 'count'"
            assert "weight" in first_material, "Material should have 'weight'"
        print(f"PASSED: material_usage has correct structure ({len(material_usage)} materials)")
    
    def test_statistics_plads_stats_structure(self):
        """plads_stats should be a list with name, total, completed, weight"""
        response = requests.get(f"{BASE_URL}/api/admin/statistics")
        data = response.json()
        plads_stats = data.get("plads_stats", [])
        
        assert isinstance(plads_stats, list), "plads_stats should be a list"
        
        if plads_stats:
            first_plads = plads_stats[0]
            assert "name" in first_plads, "Plads should have 'name'"
            assert "total" in first_plads, "Plads should have 'total'"
            assert "completed" in first_plads, "Plads should have 'completed'"
            assert "weight" in first_plads, "Plads should have 'weight'"
        print(f"PASSED: plads_stats has correct structure ({len(plads_stats)} plads)")
    
    def test_statistics_period_parameter(self):
        """Statistics should accept months parameter (1, 3, 6, 12)"""
        for months in [1, 3, 6, 12]:
            response = requests.get(f"{BASE_URL}/api/admin/statistics?months={months}")
            assert response.status_code == 200, f"Failed for months={months}"
            data = response.json()
            assert data.get("period_months") == months, f"Expected period_months={months}"
        print("PASSED: Statistics accepts months parameter (1, 3, 6, 12)")


class TestExistingEndpoints:
    """Verify existing endpoints still work"""
    
    def test_drivers_endpoint(self):
        """GET /api/drivers should return 200"""
        response = requests.get(f"{BASE_URL}/api/drivers")
        assert response.status_code == 200
        print("PASSED: GET /api/drivers returns 200")
    
    def test_plads_endpoint(self):
        """GET /api/plads should return 200"""
        response = requests.get(f"{BASE_URL}/api/plads")
        assert response.status_code == 200
        print("PASSED: GET /api/plads returns 200")
    
    def test_tours_endpoint(self):
        """GET /api/tours should return 200"""
        response = requests.get(f"{BASE_URL}/api/tours")
        assert response.status_code == 200
        print("PASSED: GET /api/tours returns 200")
    
    def test_reports_endpoint(self):
        """GET /api/reports should return 200"""
        response = requests.get(f"{BASE_URL}/api/reports")
        assert response.status_code == 200
        print("PASSED: GET /api/reports returns 200")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
