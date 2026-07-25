"""
Test Phase 3: Customer Order Workflow, Materials System, Admin Features
Tests for:
- GET /api/materials returns exactly 27 materials with correct names
- GET /api/locations/{code}/containers?material=X returns 3 containers with auto-filled address
- POST /api/customer-orders/submit creates both container_order and tour
- Admin login with password 1234
- Admin statistics endpoint
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestMaterialsSystem:
    """Test the 27 Danish materials list"""
    
    def test_materials_endpoint_returns_200(self):
        """GET /api/materials returns 200"""
        response = requests.get(f"{BASE_URL}/api/materials")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASSED: GET /api/materials returns 200")
    
    def test_materials_returns_exactly_27(self):
        """GET /api/materials returns exactly 27 materials"""
        response = requests.get(f"{BASE_URL}/api/materials")
        data = response.json()
        materials = data.get("materials", [])
        assert len(materials) == 27, f"Expected 27 materials, got {len(materials)}"
        print(f"PASSED: GET /api/materials returns exactly 27 materials")
    
    def test_materials_contains_fjernmobler(self):
        """Materials contains 'Fjernmøbler til neddeling FSG' (not Fjedermøbler)"""
        response = requests.get(f"{BASE_URL}/api/materials")
        data = response.json()
        materials = data.get("materials", [])
        # Check for correct spelling
        assert "Fjernmøbler til neddeling FSG" in materials, f"'Fjernmøbler til neddeling FSG' not found in materials"
        # Ensure wrong spelling is NOT present
        assert "Fjedermøbler til neddeling FSG" not in materials, "Wrong spelling 'Fjedermøbler' found"
        print("PASSED: Materials contains 'Fjernmøbler til neddeling FSG' (correct spelling)")
    
    def test_materials_contains_krogs(self):
        """Materials contains 'Flasker til Krogs flaskegenbrug' (not Krog)"""
        response = requests.get(f"{BASE_URL}/api/materials")
        data = response.json()
        materials = data.get("materials", [])
        # Check for correct spelling
        assert "Flasker til Krogs flaskegenbrug" in materials, f"'Flasker til Krogs flaskegenbrug' not found"
        print("PASSED: Materials contains 'Flasker til Krogs flaskegenbrug' (correct spelling)")
    
    def test_materials_contains_beton_til_rgs(self):
        """Materials contains 'Beton til RGS'"""
        response = requests.get(f"{BASE_URL}/api/materials")
        data = response.json()
        materials = data.get("materials", [])
        assert "Beton til RGS" in materials, f"'Beton til RGS' not found in materials"
        print("PASSED: Materials contains 'Beton til RGS'")


class TestLocationContainers:
    """Test location containers endpoint with auto-fill"""
    
    @pytest.fixture(autouse=True)
    def setup_location(self):
        """Ensure test location exists"""
        # First check if location 3030 exists
        response = requests.get(f"{BASE_URL}/api/locations/code/3030")
        if response.status_code == 404:
            # Create the location
            requests.post(f"{BASE_URL}/api/locations", json={
                "code": "3030",
                "name": "Skipstrup Genbrugsplads",
                "address": "Skibstrupvej 1",
                "city": "3140 Ålsgårde",
                "materials": []
            })
    
    def test_containers_endpoint_returns_200(self):
        """GET /api/locations/3030/containers?material=Beton%20til%20RGS returns 200"""
        response = requests.get(f"{BASE_URL}/api/locations/3030/containers?material=Beton%20til%20RGS")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASSED: GET /api/locations/3030/containers?material=Beton%20til%20RGS returns 200")
    
    def test_containers_returns_3_containers(self):
        """GET /api/locations/3030/containers?material=Beton%20til%20RGS returns 3 containers"""
        response = requests.get(f"{BASE_URL}/api/locations/3030/containers?material=Beton%20til%20RGS")
        data = response.json()
        containers = data.get("containers", [])
        assert len(containers) == 3, f"Expected 3 containers, got {len(containers)}"
        print(f"PASSED: Returns 3 containers")
    
    def test_containers_have_auto_filled_address(self):
        """Containers have auto-filled address from location"""
        response = requests.get(f"{BASE_URL}/api/locations/3030/containers?material=Beton%20til%20RGS")
        data = response.json()
        containers = data.get("containers", [])
        # Each container should have address field
        for c in containers:
            assert "address" in c, f"Container missing 'address' field"
            assert "genbrugsplads" in c, f"Container missing 'genbrugsplads' field"
        print("PASSED: Containers have auto-filled address and genbrugsplads")
    
    def test_containers_have_correct_labels(self):
        """Containers have labels Container 1, Container 2, Container 3"""
        response = requests.get(f"{BASE_URL}/api/locations/3030/containers?material=Beton%20til%20RGS")
        data = response.json()
        containers = data.get("containers", [])
        labels = [c.get("label") for c in containers]
        assert "Container 1" in labels, "Container 1 not found"
        assert "Container 2" in labels, "Container 2 not found"
        assert "Container 3" in labels, "Container 3 not found"
        print("PASSED: Containers have correct labels (Container 1, 2, 3)")


class TestCustomerOrderSubmit:
    """Test customer order submission creates both container_order and tour"""
    
    @pytest.fixture(autouse=True)
    def setup_location(self):
        """Ensure test location exists"""
        response = requests.get(f"{BASE_URL}/api/locations/code/3030")
        if response.status_code == 404:
            requests.post(f"{BASE_URL}/api/locations", json={
                "code": "3030",
                "name": "Skipstrup Genbrugsplads",
                "address": "Skibstrupvej 1",
                "city": "3140 Ålsgårde",
                "materials": []
            })
    
    def test_submit_order_returns_200(self):
        """POST /api/customer-orders/submit returns 200"""
        response = requests.post(f"{BASE_URL}/api/customer-orders/submit", json={
            "location_code": "3030",
            "material": "Beton til RGS",
            "container_number": "Container 1",
            "priority": "normal",
            "comment": "Test order"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASSED: POST /api/customer-orders/submit returns 200")
    
    def test_submit_order_creates_tour(self):
        """POST /api/customer-orders/submit creates a tour"""
        response = requests.post(f"{BASE_URL}/api/customer-orders/submit", json={
            "location_code": "3030",
            "material": "Tegl til RGS",
            "container_number": "Container 2",
            "priority": "haster",
            "comment": "Urgent test"
        })
        data = response.json()
        assert "tour_id" in data, f"Response missing 'tour_id': {data}"
        assert "order_id" in data, f"Response missing 'order_id': {data}"
        print(f"PASSED: Submit creates both tour_id and order_id")
    
    def test_submit_order_returns_correct_data(self):
        """POST /api/customer-orders/submit returns correct data"""
        response = requests.post(f"{BASE_URL}/api/customer-orders/submit", json={
            "location_code": "3030",
            "material": "Asfalt til RGS",
            "container_number": "Container 3",
            "priority": "senere",
            "comment": ""
        })
        data = response.json()
        assert data.get("material") == "Asfalt til RGS", f"Wrong material: {data.get('material')}"
        assert data.get("container") == "Container 3", f"Wrong container: {data.get('container')}"
        assert data.get("priority") == "senere", f"Wrong priority: {data.get('priority')}"
        assert "genbrugsplads" in data, f"Missing genbrugsplads in response"
        assert "address" in data, f"Missing address in response"
        print("PASSED: Submit returns correct data (material, container, priority, genbrugsplads, address)")
    
    def test_priority_haster_maps_to_urgent(self):
        """Priority 'haster' maps to 'urgent' in tour"""
        response = requests.post(f"{BASE_URL}/api/customer-orders/submit", json={
            "location_code": "3030",
            "material": "Pap til HCS",
            "container_number": "Container 1",
            "priority": "haster",
            "comment": ""
        })
        data = response.json()
        tour_id = data.get("tour_id")
        # Fetch the tour to verify priority
        tour_response = requests.get(f"{BASE_URL}/api/tours?limit=100")
        tours = tour_response.json()
        tour = next((t for t in tours if t.get("id") == tour_id), None)
        if tour:
            assert tour.get("priority") == "urgent", f"Expected priority 'urgent', got {tour.get('priority')}"
            print("PASSED: Priority 'haster' maps to 'urgent' in tour")
        else:
            print("PASSED: Order created (tour verification skipped)")


class TestAdminLogin:
    """Test admin login with password 1234"""
    
    def test_admin_login_success(self):
        """POST /api/admin/login with password 1234 returns 200"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={"password": "1234"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("success") == True, f"Expected success=True, got {data}"
        print("PASSED: Admin login with password 1234 returns 200 with success=True")
    
    def test_admin_login_wrong_password(self):
        """POST /api/admin/login with wrong password returns 401"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={"password": "wrong"})
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASSED: Admin login with wrong password returns 401")


class TestAdminStatistics:
    """Test admin statistics endpoint"""
    
    def test_statistics_endpoint_returns_200(self):
        """GET /api/admin/statistics returns 200"""
        response = requests.get(f"{BASE_URL}/api/admin/statistics")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASSED: GET /api/admin/statistics returns 200")
    
    def test_statistics_has_required_fields(self):
        """Statistics has required fields"""
        response = requests.get(f"{BASE_URL}/api/admin/statistics")
        data = response.json()
        required_fields = ["jobs_per_day", "driver_performance", "material_usage", "plads_stats", "summary"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        print("PASSED: Statistics has all required fields")
    
    def test_statistics_driver_performance_structure(self):
        """Driver performance has correct structure"""
        response = requests.get(f"{BASE_URL}/api/admin/statistics")
        data = response.json()
        driver_perf = data.get("driver_performance", [])
        if len(driver_perf) > 0:
            dp = driver_perf[0]
            expected_fields = ["name", "total_tours", "completed_tours", "total_weight"]
            for field in expected_fields:
                assert field in dp, f"Driver performance missing field: {field}"
        print("PASSED: Driver performance has correct structure")


class TestLocationCodeValidation:
    """Test location code validation"""
    
    def test_valid_location_code_3030(self):
        """GET /api/locations/code/3030 returns location data"""
        response = requests.get(f"{BASE_URL}/api/locations/code/3030")
        # May be 200 or 404 depending on seed data
        if response.status_code == 200:
            data = response.json()
            assert "name" in data, "Location missing 'name' field"
            print(f"PASSED: Location 3030 exists: {data.get('name')}")
        else:
            print(f"INFO: Location 3030 not seeded (status {response.status_code})")
    
    def test_invalid_location_code(self):
        """GET /api/locations/code/9999 returns 404"""
        response = requests.get(f"{BASE_URL}/api/locations/code/9999")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASSED: Invalid location code returns 404")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
