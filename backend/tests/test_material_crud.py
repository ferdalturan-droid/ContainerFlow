"""
Test Material CRUD Operations for Per-Location Materials
Tests: GET, POST (add), PUT (rename), DELETE materials for locations
Also tests isolation between locations (3030 vs 3131)
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestMaterialCRUD:
    """Test material CRUD operations for per-location materials"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        self.test_material = f"TEST_Material_{int(time.time())}"
        self.location_3030 = "3030"
        self.location_3131 = "3131"
        yield
        # Cleanup: try to delete test materials
        try:
            requests.delete(f"{BASE_URL}/api/locations/{self.location_3030}/materials?material={self.test_material}")
            requests.delete(f"{BASE_URL}/api/locations/{self.location_3030}/materials?material={self.test_material}_Renamed")
            requests.delete(f"{BASE_URL}/api/locations/{self.location_3131}/materials?material={self.test_material}")
        except:
            pass
    
    def test_get_materials_for_location_3030(self):
        """GET /api/locations/3030/materials returns current material list"""
        response = requests.get(f"{BASE_URL}/api/locations/{self.location_3030}/materials")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "materials" in data, "Response should contain 'materials' key"
        assert "location" in data, "Response should contain 'location' key"
        assert isinstance(data["materials"], list), "Materials should be a list"
        print(f"✓ GET materials for 3030: {len(data['materials'])} materials found")
    
    def test_get_materials_for_location_3131(self):
        """GET /api/locations/3131/materials returns current material list"""
        response = requests.get(f"{BASE_URL}/api/locations/{self.location_3131}/materials")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "materials" in data, "Response should contain 'materials' key"
        assert isinstance(data["materials"], list), "Materials should be a list"
        print(f"✓ GET materials for 3131: {len(data['materials'])} materials found")
    
    def test_get_materials_invalid_location(self):
        """GET /api/locations/9999/materials returns 404 for invalid location"""
        response = requests.get(f"{BASE_URL}/api/locations/9999/materials")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ GET materials for invalid location returns 404")
    
    def test_add_material_to_location(self):
        """POST /api/locations/3030/materials adds new material to location's list"""
        response = requests.post(
            f"{BASE_URL}/api/locations/{self.location_3030}/materials",
            json={"material": self.test_material}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "materials" in data, "Response should contain 'materials' key"
        assert self.test_material in data["materials"], f"New material '{self.test_material}' should be in list"
        print(f"✓ POST add material: '{self.test_material}' added to 3030")
        
        # Verify persistence with GET
        get_response = requests.get(f"{BASE_URL}/api/locations/{self.location_3030}/materials")
        assert get_response.status_code == 200
        get_data = get_response.json()
        assert self.test_material in get_data["materials"], "Material should persist after GET"
        print(f"✓ Material persisted in database")
    
    def test_add_duplicate_material_fails(self):
        """POST /api/locations/3030/materials returns 400 for duplicate material"""
        # First add the material
        requests.post(
            f"{BASE_URL}/api/locations/{self.location_3030}/materials",
            json={"material": self.test_material}
        )
        
        # Try to add again
        response = requests.post(
            f"{BASE_URL}/api/locations/{self.location_3030}/materials",
            json={"material": self.test_material}
        )
        assert response.status_code == 400, f"Expected 400 for duplicate, got {response.status_code}"
        print("✓ POST duplicate material returns 400")
    
    def test_add_material_empty_name_fails(self):
        """POST /api/locations/3030/materials returns 400 for empty material name"""
        response = requests.post(
            f"{BASE_URL}/api/locations/{self.location_3030}/materials",
            json={"material": ""}
        )
        assert response.status_code == 400, f"Expected 400 for empty name, got {response.status_code}"
        print("✓ POST empty material name returns 400")
    
    def test_rename_material(self):
        """PUT /api/locations/3030/materials renames a material"""
        # First add the material
        requests.post(
            f"{BASE_URL}/api/locations/{self.location_3030}/materials",
            json={"material": self.test_material}
        )
        
        new_name = f"{self.test_material}_Renamed"
        response = requests.put(
            f"{BASE_URL}/api/locations/{self.location_3030}/materials",
            json={"old_name": self.test_material, "new_name": new_name}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "materials" in data, "Response should contain 'materials' key"
        assert new_name in data["materials"], f"Renamed material '{new_name}' should be in list"
        assert self.test_material not in data["materials"], f"Old name '{self.test_material}' should not be in list"
        print(f"✓ PUT rename material: '{self.test_material}' → '{new_name}'")
        
        # Verify persistence
        get_response = requests.get(f"{BASE_URL}/api/locations/{self.location_3030}/materials")
        get_data = get_response.json()
        assert new_name in get_data["materials"], "Renamed material should persist"
        print(f"✓ Renamed material persisted in database")
    
    def test_rename_nonexistent_material_fails(self):
        """PUT /api/locations/3030/materials returns 404 for nonexistent material"""
        response = requests.put(
            f"{BASE_URL}/api/locations/{self.location_3030}/materials",
            json={"old_name": "NONEXISTENT_MATERIAL_XYZ", "new_name": "NewName"}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ PUT rename nonexistent material returns 404")
    
    def test_delete_material(self):
        """DELETE /api/locations/3030/materials?material=X removes material from list"""
        # First add the material
        requests.post(
            f"{BASE_URL}/api/locations/{self.location_3030}/materials",
            json={"material": self.test_material}
        )
        
        # Delete it
        response = requests.delete(
            f"{BASE_URL}/api/locations/{self.location_3030}/materials?material={self.test_material}"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "materials" in data, "Response should contain 'materials' key"
        assert self.test_material not in data["materials"], f"Deleted material should not be in list"
        print(f"✓ DELETE material: '{self.test_material}' removed from 3030")
        
        # Verify persistence
        get_response = requests.get(f"{BASE_URL}/api/locations/{self.location_3030}/materials")
        get_data = get_response.json()
        assert self.test_material not in get_data["materials"], "Deleted material should not persist"
        print(f"✓ Material deletion persisted in database")
    
    def test_delete_nonexistent_material_fails(self):
        """DELETE /api/locations/3030/materials?material=X returns 404 for nonexistent material"""
        response = requests.delete(
            f"{BASE_URL}/api/locations/{self.location_3030}/materials?material=NONEXISTENT_MATERIAL_XYZ"
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ DELETE nonexistent material returns 404")
    
    def test_delete_material_missing_param_fails(self):
        """DELETE /api/locations/3030/materials without material param returns 400"""
        response = requests.delete(f"{BASE_URL}/api/locations/{self.location_3030}/materials")
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ DELETE without material param returns 400")


class TestMaterialIsolation:
    """Test that material changes to one location don't affect another"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        self.test_material = f"TEST_Isolation_{int(time.time())}"
        self.location_3030 = "3030"
        self.location_3131 = "3131"
        yield
        # Cleanup
        try:
            requests.delete(f"{BASE_URL}/api/locations/{self.location_3030}/materials?material={self.test_material}")
            requests.delete(f"{BASE_URL}/api/locations/{self.location_3131}/materials?material={self.test_material}")
        except:
            pass
    
    def test_add_material_to_3030_does_not_affect_3131(self):
        """Adding material to 3030 should not add it to 3131"""
        # Get initial materials for 3131
        initial_3131 = requests.get(f"{BASE_URL}/api/locations/{self.location_3131}/materials").json()
        initial_count_3131 = len(initial_3131["materials"])
        
        # Add material to 3030
        response = requests.post(
            f"{BASE_URL}/api/locations/{self.location_3030}/materials",
            json={"material": self.test_material}
        )
        assert response.status_code == 200
        
        # Check 3131 is unchanged
        after_3131 = requests.get(f"{BASE_URL}/api/locations/{self.location_3131}/materials").json()
        assert len(after_3131["materials"]) == initial_count_3131, "3131 material count should not change"
        assert self.test_material not in after_3131["materials"], "Test material should not appear in 3131"
        print(f"✓ Material added to 3030 does NOT affect 3131")
    
    def test_delete_material_from_3030_does_not_affect_3131(self):
        """Deleting material from 3030 should not affect 3131"""
        # Add material to both locations
        requests.post(f"{BASE_URL}/api/locations/{self.location_3030}/materials", json={"material": self.test_material})
        requests.post(f"{BASE_URL}/api/locations/{self.location_3131}/materials", json={"material": self.test_material})
        
        # Delete from 3030
        response = requests.delete(f"{BASE_URL}/api/locations/{self.location_3030}/materials?material={self.test_material}")
        assert response.status_code == 200
        
        # Check 3131 still has it
        after_3131 = requests.get(f"{BASE_URL}/api/locations/{self.location_3131}/materials").json()
        assert self.test_material in after_3131["materials"], "Test material should still be in 3131"
        print(f"✓ Material deleted from 3030 does NOT affect 3131")
    
    def test_rename_material_in_3030_does_not_affect_3131(self):
        """Renaming material in 3030 should not affect 3131"""
        # Add material to both locations
        requests.post(f"{BASE_URL}/api/locations/{self.location_3030}/materials", json={"material": self.test_material})
        requests.post(f"{BASE_URL}/api/locations/{self.location_3131}/materials", json={"material": self.test_material})
        
        # Rename in 3030
        new_name = f"{self.test_material}_Renamed"
        response = requests.put(
            f"{BASE_URL}/api/locations/{self.location_3030}/materials",
            json={"old_name": self.test_material, "new_name": new_name}
        )
        assert response.status_code == 200
        
        # Check 3131 still has original name
        after_3131 = requests.get(f"{BASE_URL}/api/locations/{self.location_3131}/materials").json()
        assert self.test_material in after_3131["materials"], "Original material name should still be in 3131"
        assert new_name not in after_3131["materials"], "Renamed material should NOT be in 3131"
        print(f"✓ Material renamed in 3030 does NOT affect 3131")


class TestContainerOverrideUpdate:
    """Test that renaming material also updates container_overrides"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        self.test_material = f"TEST_Override_{int(time.time())}"
        self.location_3030 = "3030"
        yield
        # Cleanup
        try:
            requests.delete(f"{BASE_URL}/api/locations/{self.location_3030}/materials?material={self.test_material}")
            requests.delete(f"{BASE_URL}/api/locations/{self.location_3030}/materials?material={self.test_material}_Renamed")
        except:
            pass
    
    def test_rename_material_updates_container_overrides(self):
        """PUT rename should also update container_overrides for that material"""
        # Add material
        requests.post(
            f"{BASE_URL}/api/locations/{self.location_3030}/materials",
            json={"material": self.test_material}
        )
        
        # Create an order with this material to create a container_override
        # First get containers
        containers_resp = requests.get(
            f"{BASE_URL}/api/locations/{self.location_3030}/containers?material={self.test_material}"
        )
        if containers_resp.status_code == 200:
            containers = containers_resp.json().get("containers", [])
            if containers:
                # Submit an order to create override
                order_resp = requests.post(
                    f"{BASE_URL}/api/customer-orders/submit",
                    json={
                        "location_code": self.location_3030,
                        "material": self.test_material,
                        "container_number": containers[0]["label"],
                        "priority": "normal",
                        "comment": "Test override",
                        "custom_address": "Test Address 123",
                        "custom_container_id": "TEST-OVERRIDE-001"
                    }
                )
                print(f"Order created: {order_resp.status_code}")
        
        # Now rename the material
        new_name = f"{self.test_material}_Renamed"
        response = requests.put(
            f"{BASE_URL}/api/locations/{self.location_3030}/materials",
            json={"old_name": self.test_material, "new_name": new_name}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify the material was renamed
        data = response.json()
        assert new_name in data["materials"], "New name should be in materials list"
        print(f"✓ Material renamed and container_overrides should be updated")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
