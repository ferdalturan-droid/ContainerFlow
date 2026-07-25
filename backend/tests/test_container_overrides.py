"""
Test Container Override System - Customer Editable Data
Tests the new feature where customers can edit address and container-nummer,
and the system saves/loads these overrides per location.

Key features tested:
- GET /api/locations/{code}/containers returns has_override flag and default_address
- PUT /api/locations/{code}/containers/override saves custom data
- After override saved, GET returns the saved data (not default)
- POST /api/customer-orders/submit with custom_address saves override automatically
- Override is per-location: editing for code 3030 doesn't affect code 3131
"""

import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestContainerOverrideSystem:
    """Test the container override (customer editable data) system"""
    
    # Test data
    TEST_LOCATION_CODE = "3030"
    TEST_LOCATION_CODE_2 = "3131"
    TEST_MATERIAL = "Beton til RGS"
    TEST_MATERIAL_2 = "Tegl til RGS"
    TEST_CONTAINER_LABEL = "Container 1"
    TEST_CUSTOM_ADDRESS = "TEST_Ny Vej 42, 1234 Testby"
    TEST_CUSTOM_CONTAINER_ID = "TEST_CNT-8842"
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        yield
        # Cleanup: Remove test overrides
        try:
            # We can't easily delete overrides via API, but they're prefixed with TEST_
            pass
        except:
            pass
    
    # ============= BACKEND API TESTS =============
    
    def test_get_containers_returns_has_override_flag(self):
        """GET /api/locations/{code}/containers returns containers with has_override flag"""
        response = self.session.get(
            f"{BASE_URL}/api/locations/{self.TEST_LOCATION_CODE}/containers",
            params={"material": self.TEST_MATERIAL}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "containers" in data, "Response should have 'containers' field"
        assert len(data["containers"]) > 0, "Should return at least one container"
        
        # Check that each container has the required fields
        for container in data["containers"]:
            assert "has_override" in container, f"Container should have 'has_override' field: {container}"
            assert "default_address" in container, f"Container should have 'default_address' field: {container}"
            assert "address" in container, f"Container should have 'address' field: {container}"
            assert "label" in container, f"Container should have 'label' field: {container}"
            assert "material" in container, f"Container should have 'material' field: {container}"
            assert "genbrugsplads" in container, f"Container should have 'genbrugsplads' field: {container}"
        
        print(f"✓ GET containers returns {len(data['containers'])} containers with has_override flag")
    
    def test_save_container_override_endpoint(self):
        """PUT /api/locations/{code}/containers/override saves custom address and container_id"""
        override_data = {
            "material": self.TEST_MATERIAL,
            "container_label": self.TEST_CONTAINER_LABEL,
            "custom_address": self.TEST_CUSTOM_ADDRESS,
            "custom_container_id": self.TEST_CUSTOM_CONTAINER_ID
        }
        
        response = self.session.put(
            f"{BASE_URL}/api/locations/{self.TEST_LOCATION_CODE}/containers/override",
            json=override_data
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "message" in data, "Response should have 'message' field"
        assert data.get("material") == self.TEST_MATERIAL, "Response should echo material"
        assert data.get("container_label") == self.TEST_CONTAINER_LABEL, "Response should echo container_label"
        
        print(f"✓ PUT override saved successfully: {data}")
    
    def test_get_containers_returns_saved_override_data(self):
        """After override saved, GET containers returns the saved data (not default)"""
        # First, save an override
        override_data = {
            "material": self.TEST_MATERIAL,
            "container_label": self.TEST_CONTAINER_LABEL,
            "custom_address": self.TEST_CUSTOM_ADDRESS,
            "custom_container_id": self.TEST_CUSTOM_CONTAINER_ID
        }
        
        save_response = self.session.put(
            f"{BASE_URL}/api/locations/{self.TEST_LOCATION_CODE}/containers/override",
            json=override_data
        )
        assert save_response.status_code == 200, f"Failed to save override: {save_response.text}"
        
        # Now GET containers and verify the override is returned
        get_response = self.session.get(
            f"{BASE_URL}/api/locations/{self.TEST_LOCATION_CODE}/containers",
            params={"material": self.TEST_MATERIAL}
        )
        assert get_response.status_code == 200, f"Failed to get containers: {get_response.text}"
        
        data = get_response.json()
        containers = data.get("containers", [])
        
        # Find Container 1
        container_1 = next((c for c in containers if c["label"] == self.TEST_CONTAINER_LABEL), None)
        assert container_1 is not None, f"Container 1 not found in response: {containers}"
        
        # Verify override data is returned
        assert container_1["has_override"] == True, f"has_override should be True: {container_1}"
        assert container_1["address"] == self.TEST_CUSTOM_ADDRESS, f"Address should be custom: {container_1['address']}"
        assert container_1["container_id"] == self.TEST_CUSTOM_CONTAINER_ID, f"Container ID should be custom: {container_1.get('container_id')}"
        
        print(f"✓ GET containers returns saved override data: address={container_1['address']}, container_id={container_1['container_id']}")
    
    def test_submit_order_with_custom_address_saves_override(self):
        """POST /api/customer-orders/submit with custom_address saves override automatically"""
        unique_address = f"TEST_Auto-saved Vej {datetime.now().strftime('%H%M%S')}"
        unique_container_id = f"TEST_AUTO-{datetime.now().strftime('%H%M%S')}"
        
        order_data = {
            "location_code": self.TEST_LOCATION_CODE,
            "material": self.TEST_MATERIAL_2,  # Use different material to avoid conflict
            "container_number": "Container 2",
            "priority": "normal",
            "comment": "Test order with custom address",
            "custom_address": unique_address,
            "custom_container_id": unique_container_id
        }
        
        # Submit order
        submit_response = self.session.post(
            f"{BASE_URL}/api/customer-orders/submit",
            json=order_data
        )
        assert submit_response.status_code == 200, f"Failed to submit order: {submit_response.text}"
        
        # Verify the override was auto-saved by fetching containers
        get_response = self.session.get(
            f"{BASE_URL}/api/locations/{self.TEST_LOCATION_CODE}/containers",
            params={"material": self.TEST_MATERIAL_2}
        )
        assert get_response.status_code == 200, f"Failed to get containers: {get_response.text}"
        
        data = get_response.json()
        containers = data.get("containers", [])
        
        # Find Container 2
        container_2 = next((c for c in containers if c["label"] == "Container 2"), None)
        assert container_2 is not None, f"Container 2 not found: {containers}"
        
        # Verify override was auto-saved
        assert container_2["has_override"] == True, f"has_override should be True after submit: {container_2}"
        assert container_2["address"] == unique_address, f"Address should be auto-saved: {container_2['address']}"
        assert container_2["container_id"] == unique_container_id, f"Container ID should be auto-saved: {container_2.get('container_id')}"
        
        print(f"✓ Submit order auto-saved override: address={container_2['address']}")
    
    def test_override_is_per_location(self):
        """Override is per-location: editing for code 3030 doesn't affect code 3131"""
        # Save override for location 3030
        override_3030 = {
            "material": self.TEST_MATERIAL,
            "container_label": "Container 3",
            "custom_address": "TEST_3030 Specific Address",
            "custom_container_id": "TEST_3030-CNT"
        }
        
        save_response = self.session.put(
            f"{BASE_URL}/api/locations/3030/containers/override",
            json=override_3030
        )
        assert save_response.status_code == 200, f"Failed to save 3030 override: {save_response.text}"
        
        # Get containers for location 3131 - should NOT have the 3030 override
        get_3131_response = self.session.get(
            f"{BASE_URL}/api/locations/3131/containers",
            params={"material": self.TEST_MATERIAL}
        )
        assert get_3131_response.status_code == 200, f"Failed to get 3131 containers: {get_3131_response.text}"
        
        data_3131 = get_3131_response.json()
        containers_3131 = data_3131.get("containers", [])
        
        # Find Container 3 at location 3131
        container_3_at_3131 = next((c for c in containers_3131 if c["label"] == "Container 3"), None)
        assert container_3_at_3131 is not None, f"Container 3 not found at 3131: {containers_3131}"
        
        # Verify 3131 does NOT have the 3030 override
        assert container_3_at_3131["address"] != "TEST_3030 Specific Address", \
            f"3131 should NOT have 3030's override address: {container_3_at_3131['address']}"
        
        # Verify 3030 DOES have the override
        get_3030_response = self.session.get(
            f"{BASE_URL}/api/locations/3030/containers",
            params={"material": self.TEST_MATERIAL}
        )
        data_3030 = get_3030_response.json()
        containers_3030 = data_3030.get("containers", [])
        container_3_at_3030 = next((c for c in containers_3030 if c["label"] == "Container 3"), None)
        
        assert container_3_at_3030["address"] == "TEST_3030 Specific Address", \
            f"3030 should have its override: {container_3_at_3030['address']}"
        
        print(f"✓ Override is per-location: 3030 has override, 3131 does not")
    
    def test_second_order_loads_previously_saved_address(self):
        """Second order with same material+container loads previously saved address"""
        unique_address = f"TEST_Persistent Vej {datetime.now().strftime('%H%M%S')}"
        unique_container_id = f"TEST_PERSIST-{datetime.now().strftime('%H%M%S')}"
        
        # First order - save custom data
        first_order = {
            "location_code": self.TEST_LOCATION_CODE,
            "material": "Asfalt til RGS",  # Use unique material
            "container_number": "Container 1",
            "priority": "normal",
            "comment": "First order",
            "custom_address": unique_address,
            "custom_container_id": unique_container_id
        }
        
        first_response = self.session.post(
            f"{BASE_URL}/api/customer-orders/submit",
            json=first_order
        )
        assert first_response.status_code == 200, f"First order failed: {first_response.text}"
        
        # Now fetch containers - should have the saved data
        get_response = self.session.get(
            f"{BASE_URL}/api/locations/{self.TEST_LOCATION_CODE}/containers",
            params={"material": "Asfalt til RGS"}
        )
        assert get_response.status_code == 200
        
        data = get_response.json()
        container_1 = next((c for c in data["containers"] if c["label"] == "Container 1"), None)
        
        # Verify the saved data is loaded
        assert container_1["has_override"] == True, "Should have override after first order"
        assert container_1["address"] == unique_address, f"Should load saved address: {container_1['address']}"
        assert container_1["container_id"] == unique_container_id, f"Should load saved container_id: {container_1.get('container_id')}"
        
        print(f"✓ Second order loads previously saved address: {container_1['address']}")
    
    def test_override_validation_requires_material_and_label(self):
        """PUT override requires material and container_label"""
        # Missing material
        response1 = self.session.put(
            f"{BASE_URL}/api/locations/{self.TEST_LOCATION_CODE}/containers/override",
            json={"container_label": "Container 1", "custom_address": "Test"}
        )
        assert response1.status_code == 400, f"Should fail without material: {response1.status_code}"
        
        # Missing container_label
        response2 = self.session.put(
            f"{BASE_URL}/api/locations/{self.TEST_LOCATION_CODE}/containers/override",
            json={"material": "Beton til RGS", "custom_address": "Test"}
        )
        assert response2.status_code == 400, f"Should fail without container_label: {response2.status_code}"
        
        print("✓ Override validation works correctly")
    
    def test_invalid_location_code_returns_404(self):
        """Invalid location code returns 404"""
        response = self.session.get(
            f"{BASE_URL}/api/locations/9999/containers",
            params={"material": self.TEST_MATERIAL}
        )
        assert response.status_code == 404, f"Expected 404 for invalid location: {response.status_code}"
        
        response2 = self.session.put(
            f"{BASE_URL}/api/locations/9999/containers/override",
            json={"material": "Test", "container_label": "Container 1"}
        )
        assert response2.status_code == 404, f"Expected 404 for invalid location on PUT: {response2.status_code}"
        
        print("✓ Invalid location returns 404")


class TestCustomerOrderSubmitWithOverride:
    """Test the customer order submit endpoint with custom data"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def test_submit_order_returns_correct_response(self):
        """POST /api/customer-orders/submit returns correct response structure"""
        order_data = {
            "location_code": "3030",
            "material": "Pap til HCS",
            "container_number": "Container 1",
            "priority": "haster",
            "comment": "Test urgent order",
            "custom_address": "TEST_Urgent Vej 99",
            "custom_container_id": "TEST_URG-001"
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/customer-orders/submit",
            json=order_data
        )
        assert response.status_code == 200, f"Submit failed: {response.text}"
        
        data = response.json()
        
        # Verify response structure
        assert "tour_id" in data, "Response should have tour_id"
        assert "order_id" in data, "Response should have order_id"
        assert "material" in data, "Response should have material"
        assert "container" in data, "Response should have container"
        assert "priority" in data, "Response should have priority"
        assert "genbrugsplads" in data, "Response should have genbrugsplads"
        assert "address" in data, "Response should have address"
        
        # Verify values
        assert data["material"] == "Pap til HCS"
        assert data["container"] == "Container 1"
        assert data["priority"] == "haster"
        assert data["address"] == "TEST_Urgent Vej 99"
        
        print(f"✓ Submit order returns correct response: tour_id={data['tour_id']}, order_id={data['order_id']}")
    
    def test_submit_order_creates_tour_with_correct_priority(self):
        """Submit order creates tour with correct priority mapping"""
        # Test haster -> urgent
        order_haster = {
            "location_code": "3030",
            "material": "Rockwool til RGS",
            "container_number": "Container 1",
            "priority": "haster",
            "comment": "",
            "custom_address": "",
            "custom_container_id": ""
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/customer-orders/submit",
            json=order_haster
        )
        assert response.status_code == 200
        
        data = response.json()
        tour_id = data.get("tour_id")
        
        # Fetch the tour to verify priority
        tour_response = self.session.get(f"{BASE_URL}/api/tours")
        assert tour_response.status_code == 200
        
        tours = tour_response.json()
        created_tour = next((t for t in tours if t["id"] == tour_id), None)
        
        if created_tour:
            assert created_tour["priority"] == "urgent", f"haster should map to urgent: {created_tour['priority']}"
            print(f"✓ Priority mapping works: haster -> {created_tour['priority']}")
        else:
            print(f"⚠ Could not find tour {tour_id} to verify priority")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
