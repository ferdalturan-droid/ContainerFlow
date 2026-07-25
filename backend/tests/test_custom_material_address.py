"""
Test suite for:
1. Address field = destination address (empty by default for first-time use)
2. Custom material support (any material name accepted)
3. Override persistence for reuse
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAddressFieldBehavior:
    """Test that address field is empty by default (destination address, not genbrugsplads address)"""
    
    def test_containers_endpoint_returns_has_override_flag(self):
        """GET /api/locations/{code}/containers should return has_override flag"""
        response = requests.get(f"{BASE_URL}/api/locations/3030/containers?material=Beton til RGS")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "containers" in data, "Response should have 'containers' key"
        for container in data["containers"]:
            assert "has_override" in container, f"Container should have 'has_override' field: {container}"
            assert "default_address" in container, f"Container should have 'default_address' field: {container}"
        print(f"PASSED: Containers endpoint returns has_override and default_address fields")
    
    def test_new_material_container_has_no_override(self):
        """For a material+container combo that has never been used, has_override should be False"""
        # Use a unique material name to ensure no prior override exists
        unique_material = f"TEST_UniqueNewMaterial_{uuid.uuid4().hex[:8]}"
        response = requests.get(f"{BASE_URL}/api/locations/3131/containers?material={unique_material}")
        assert response.status_code == 200
        data = response.json()
        for container in data["containers"]:
            assert container["has_override"] == False, f"New material should have has_override=False: {container}"
        print(f"PASSED: New material '{unique_material}' has has_override=False for all containers")
    
    def test_address_empty_when_no_override(self):
        """When has_override=False, frontend should show empty address (per handleContainerSelect logic)"""
        # This is a frontend behavior test - we verify backend returns the right data
        unique_material = f"TEST_EmptyAddr_{uuid.uuid4().hex[:8]}"
        response = requests.get(f"{BASE_URL}/api/locations/3131/containers?material={unique_material}")
        assert response.status_code == 200
        data = response.json()
        # Backend returns default_address but frontend should use empty string when has_override=False
        for container in data["containers"]:
            assert container["has_override"] == False
            # Backend still provides default_address for reference
            assert "default_address" in container
        print(f"PASSED: Backend returns has_override=False for new material, frontend will show empty address")


class TestCustomMaterialSupport:
    """Test that backend accepts any material name (custom materials)"""
    
    def test_containers_endpoint_accepts_any_material(self):
        """GET /api/locations/{code}/containers should accept any material name"""
        custom_material = "Min egen specielle affald type"
        response = requests.get(f"{BASE_URL}/api/locations/3030/containers?material={custom_material}")
        assert response.status_code == 200, f"Expected 200 for custom material, got {response.status_code}"
        data = response.json()
        assert data["material"] == custom_material, f"Response should echo the custom material name"
        assert len(data["containers"]) > 0, "Should return containers for custom material"
        print(f"PASSED: Backend accepts custom material '{custom_material}'")
    
    def test_submit_order_with_custom_material(self):
        """POST /api/customer-orders/submit should accept custom material names"""
        custom_material = f"TEST_CustomMat_{uuid.uuid4().hex[:8]}"
        order_data = {
            "location_code": "3030",
            "material": custom_material,
            "container_number": "Container 1",
            "priority": "normal",
            "comment": "Test custom material order",
            "custom_address": "Test Custom Address 123",
            "custom_container_id": "CUSTOM-001"
        }
        response = requests.post(f"{BASE_URL}/api/customer-orders/submit", json=order_data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["material"] == custom_material, f"Response should have custom material"
        assert "tour_id" in data, "Response should have tour_id"
        assert "order_id" in data, "Response should have order_id"
        print(f"PASSED: Order submitted with custom material '{custom_material}'")
    
    def test_custom_material_not_in_predefined_list(self):
        """Verify custom material is not rejected even if not in DEFAULT_MATERIALS"""
        # Get the materials list
        response = requests.get(f"{BASE_URL}/api/materials")
        assert response.status_code == 200
        materials = response.json().get("materials", [])
        
        # Create a material name that's definitely not in the list
        custom_material = "Helt ny type affald som ikke findes i listen"
        assert custom_material not in materials, "Test material should not be in predefined list"
        
        # Try to get containers for this custom material
        response = requests.get(f"{BASE_URL}/api/locations/3030/containers?material={custom_material}")
        assert response.status_code == 200, f"Custom material should be accepted: {response.status_code}"
        print(f"PASSED: Custom material not in predefined list is accepted")


class TestOverridePersistence:
    """Test that overrides are saved and loaded correctly"""
    
    def test_save_override_via_order_submission(self):
        """Submitting order with custom_address should save override for reuse"""
        test_material = f"TEST_Override_{uuid.uuid4().hex[:8]}"
        test_address = f"TEST_Address_{uuid.uuid4().hex[:8]}"
        test_container_id = f"TEST_ID_{uuid.uuid4().hex[:8]}"
        
        # Submit order with custom data
        order_data = {
            "location_code": "3030",
            "material": test_material,
            "container_number": "Container 1",
            "priority": "normal",
            "comment": "",
            "custom_address": test_address,
            "custom_container_id": test_container_id
        }
        response = requests.post(f"{BASE_URL}/api/customer-orders/submit", json=order_data)
        assert response.status_code == 200, f"Order submission failed: {response.text}"
        print(f"Order submitted with custom address: {test_address}")
        
        # Now fetch containers again - should have override
        response = requests.get(f"{BASE_URL}/api/locations/3030/containers?material={test_material}")
        assert response.status_code == 200
        data = response.json()
        
        container_1 = next((c for c in data["containers"] if c["label"] == "Container 1"), None)
        assert container_1 is not None, "Container 1 should exist"
        assert container_1["has_override"] == True, f"Container 1 should have override: {container_1}"
        assert container_1["address"] == test_address, f"Address should be saved: {container_1}"
        assert container_1["container_id"] == test_container_id, f"Container ID should be saved: {container_1}"
        print(f"PASSED: Override persisted - address={test_address}, container_id={test_container_id}")
    
    def test_override_isolation_between_locations(self):
        """Override at location 3030 should not affect location 3131"""
        test_material = f"TEST_Isolation_{uuid.uuid4().hex[:8]}"
        test_address = "3030 Specific Address"
        
        # Save override at 3030
        order_data = {
            "location_code": "3030",
            "material": test_material,
            "container_number": "Container 1",
            "priority": "normal",
            "comment": "",
            "custom_address": test_address,
            "custom_container_id": ""
        }
        response = requests.post(f"{BASE_URL}/api/customer-orders/submit", json=order_data)
        assert response.status_code == 200
        
        # Check 3131 - should NOT have override
        response = requests.get(f"{BASE_URL}/api/locations/3131/containers?material={test_material}")
        assert response.status_code == 200
        data = response.json()
        
        container_1 = next((c for c in data["containers"] if c["label"] == "Container 1"), None)
        assert container_1 is not None
        assert container_1["has_override"] == False, f"3131 should not have 3030's override: {container_1}"
        print(f"PASSED: Override isolation - 3030 override does not affect 3131")


class TestFullOrderFlow:
    """Test complete order flow with custom material and address"""
    
    def test_full_flow_custom_material_and_address(self):
        """Complete flow: custom material → container → custom address → priority → submit"""
        custom_material = f"TEST_FullFlow_{uuid.uuid4().hex[:8]}"
        custom_address = "Testvej 42, 8000 Aarhus"
        
        # Step 1: Get containers for custom material
        response = requests.get(f"{BASE_URL}/api/locations/3030/containers?material={custom_material}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["containers"]) >= 1
        container = data["containers"][0]
        assert container["has_override"] == False, "First time should have no override"
        print(f"Step 1 PASSED: Got containers for custom material")
        
        # Step 2: Submit order with custom address
        order_data = {
            "location_code": "3030",
            "material": custom_material,
            "container_number": container["label"],
            "priority": "haster",
            "comment": "Full flow test",
            "custom_address": custom_address,
            "custom_container_id": "FLOW-001"
        }
        response = requests.post(f"{BASE_URL}/api/customer-orders/submit", json=order_data)
        assert response.status_code == 200
        result = response.json()
        assert result["material"] == custom_material
        assert result["address"] == custom_address
        assert result["priority"] == "haster"
        print(f"Step 2 PASSED: Order submitted successfully")
        
        # Step 3: Verify override was saved
        response = requests.get(f"{BASE_URL}/api/locations/3030/containers?material={custom_material}")
        assert response.status_code == 200
        data = response.json()
        container = next((c for c in data["containers"] if c["label"] == order_data["container_number"]), None)
        assert container["has_override"] == True
        assert container["address"] == custom_address
        print(f"Step 3 PASSED: Override saved for reuse")
        
        print(f"FULL FLOW TEST PASSED")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
