"""
Test Suite for Multi-Driver Tour Claiming Feature
- Tour claiming: When Driver A presses 'På vej' (on_way), the tour gets claimed_by set to Driver A's name
- Tour locking: When tour is claimed by Driver A, Driver B gets 409 error when trying to claim or modify it
- Tour unclaiming: Driver A can unclaim (toggle off 'På vej') and then the tour becomes available again
- Tour completion: Completed tours show claimed_by driver name, locked for other drivers
- Backend validation: PUT /api/tours/{id} returns 409 when claimed_by doesn't match
- Unclaimed tours: All drivers can still interact with unclaimed tours
"""

import pytest
import requests
import uuid

BASE_URL = "https://role-analysis-flow.preview.emergentagent.com"


class TestTourClaimingWorkflow:
    """Test multi-driver tour claiming functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Create test data for each test"""
        self.driver_a = "TEST_DriverA_" + str(uuid.uuid4())[:8]
        self.driver_b = "TEST_DriverB_" + str(uuid.uuid4())[:8]
        self.test_tours = []
        self.test_report_id = None
        yield
        # Cleanup
        for tour_id in self.test_tours:
            try:
                requests.delete(f"{BASE_URL}/api/tours/{tour_id}")
            except:
                pass
        if self.test_report_id:
            try:
                requests.delete(f"{BASE_URL}/api/reports/{self.test_report_id}")
            except:
                pass
    
    def create_test_tour(self, plads="Skipstrup", fraction="Test Fraction"):
        """Helper to create a test tour"""
        response = requests.post(f"{BASE_URL}/api/tours", json={
            "date": "2026-01-20",
            "fraction": fraction,
            "facility": "Test Facility",
            "address": "Test Address 123",
            "plads": plads,
            "container": f"TEST-{uuid.uuid4().hex[:6]}"
        })
        if response.status_code == 200:
            tour = response.json()
            self.test_tours.append(tour["id"])
            return tour
        return None
    
    # =========== TOUR CLAIMING TESTS ===========
    
    def test_driver_can_claim_tour_with_on_way(self):
        """Tour claiming: When Driver A presses 'På vej', tour gets claimed_by set"""
        tour = self.create_test_tour()
        assert tour is not None, "Failed to create test tour"
        
        # Driver A claims the tour by setting on_way=true
        response = requests.put(f"{BASE_URL}/api/tours/{tour['id']}", json={
            "on_way": True,
            "claimed_by": self.driver_a,
            "claimed_by_id": "test_driver_a_id"
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        updated_tour = response.json()
        assert updated_tour["claimed_by"] == self.driver_a, f"Expected claimed_by={self.driver_a}, got {updated_tour.get('claimed_by')}"
        assert updated_tour["on_way"] == True, "Expected on_way=True"
        print(f"✓ Driver A successfully claimed tour, claimed_by={updated_tour['claimed_by']}")
    
    def test_other_driver_blocked_from_claiming_claimed_tour(self):
        """Tour locking: Driver B gets 409 when trying to claim tour already claimed by Driver A"""
        tour = self.create_test_tour()
        assert tour is not None
        
        # Driver A claims the tour
        response_a = requests.put(f"{BASE_URL}/api/tours/{tour['id']}", json={
            "on_way": True,
            "claimed_by": self.driver_a
        })
        assert response_a.status_code == 200, f"Driver A claim failed: {response_a.text}"
        
        # Driver B tries to claim the same tour - should get 409
        response_b = requests.put(f"{BASE_URL}/api/tours/{tour['id']}", json={
            "on_way": True,
            "claimed_by": self.driver_b
        })
        
        assert response_b.status_code == 409, f"Expected 409 for Driver B, got {response_b.status_code}: {response_b.text}"
        error_detail = response_b.json().get("detail", "")
        assert self.driver_a in error_detail, f"Error should mention Driver A's name: {error_detail}"
        print(f"✓ Driver B correctly blocked with 409: {error_detail}")
    
    def test_other_driver_blocked_from_modifying_claimed_tour(self):
        """Tour locking: Driver B gets 409 when trying to modify on_way/completed/weight of claimed tour"""
        tour = self.create_test_tour()
        assert tour is not None
        
        # Driver A claims the tour
        response_a = requests.put(f"{BASE_URL}/api/tours/{tour['id']}", json={
            "on_way": True,
            "claimed_by": self.driver_a
        })
        assert response_a.status_code == 200
        
        # Driver B tries to modify on_way - should get 409
        response_b_onway = requests.put(f"{BASE_URL}/api/tours/{tour['id']}", json={
            "on_way": False
        })
        assert response_b_onway.status_code == 409, f"Expected 409 for on_way modification, got {response_b_onway.status_code}"
        
        # Driver B tries to set completed - should get 409
        response_b_complete = requests.put(f"{BASE_URL}/api/tours/{tour['id']}", json={
            "completed": True
        })
        assert response_b_complete.status_code == 409, f"Expected 409 for completed modification, got {response_b_complete.status_code}"
        
        # Driver B tries to set weight - should get 409
        response_b_weight = requests.put(f"{BASE_URL}/api/tours/{tour['id']}", json={
            "weight": 5000.0
        })
        assert response_b_weight.status_code == 409, f"Expected 409 for weight modification, got {response_b_weight.status_code}"
        
        print("✓ Driver B correctly blocked from modifying on_way, completed, and weight")
    
    def test_driver_can_unclaim_own_tour(self):
        """Tour unclaiming: Driver A can unclaim tour by setting claimed_by to empty string"""
        tour = self.create_test_tour()
        assert tour is not None
        
        # Driver A claims the tour
        response_claim = requests.put(f"{BASE_URL}/api/tours/{tour['id']}", json={
            "on_way": True,
            "claimed_by": self.driver_a
        })
        assert response_claim.status_code == 200
        
        # Driver A unclaims the tour
        response_unclaim = requests.put(f"{BASE_URL}/api/tours/{tour['id']}", json={
            "on_way": False,
            "claimed_by": ""
        })
        assert response_unclaim.status_code == 200, f"Expected 200, got {response_unclaim.status_code}: {response_unclaim.text}"
        
        updated_tour = response_unclaim.json()
        assert updated_tour["claimed_by"] == "", f"Expected empty claimed_by, got: {updated_tour.get('claimed_by')}"
        assert updated_tour["on_way"] == False, "Expected on_way=False"
        print("✓ Driver A successfully unclaimed tour")
    
    def test_unclaimed_tour_becomes_available_for_other_driver(self):
        """Tour unclaiming: After Driver A unclaims, Driver B can claim"""
        tour = self.create_test_tour()
        assert tour is not None
        
        # Driver A claims
        response_a = requests.put(f"{BASE_URL}/api/tours/{tour['id']}", json={
            "on_way": True,
            "claimed_by": self.driver_a
        })
        assert response_a.status_code == 200
        
        # Driver A unclaims
        response_unclaim = requests.put(f"{BASE_URL}/api/tours/{tour['id']}", json={
            "on_way": False,
            "claimed_by": ""
        })
        assert response_unclaim.status_code == 200
        
        # Now Driver B can claim
        response_b = requests.put(f"{BASE_URL}/api/tours/{tour['id']}", json={
            "on_way": True,
            "claimed_by": self.driver_b
        })
        
        assert response_b.status_code == 200, f"Expected 200 for Driver B after unclaim, got {response_b.status_code}: {response_b.text}"
        updated_tour = response_b.json()
        assert updated_tour["claimed_by"] == self.driver_b
        print("✓ Driver B successfully claimed tour after Driver A unclaimed")
    
    def test_tour_completion_with_claim(self):
        """Tour completion: Completed tours show claimed_by driver name"""
        tour = self.create_test_tour()
        assert tour is not None
        
        # Driver A completes the tour with weight
        response = requests.put(f"{BASE_URL}/api/tours/{tour['id']}", json={
            "completed": True,
            "on_way": False,
            "weight": 3500.0,
            "time": "14:30",
            "claimed_by": self.driver_a
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        completed_tour = response.json()
        assert completed_tour["completed"] == True
        assert completed_tour["claimed_by"] == self.driver_a
        assert completed_tour["weight"] == 3500.0
        print(f"✓ Tour completed by {completed_tour['claimed_by']} with weight {completed_tour['weight']}kg")
    
    def test_completed_tour_locked_for_other_drivers(self):
        """Tour completion: Completed tours are locked for other drivers"""
        tour = self.create_test_tour()
        assert tour is not None
        
        # Driver A completes the tour
        response_a = requests.put(f"{BASE_URL}/api/tours/{tour['id']}", json={
            "completed": True,
            "weight": 2500.0,
            "claimed_by": self.driver_a
        })
        assert response_a.status_code == 200
        
        # Driver B tries to modify the completed tour - should get 409
        response_b = requests.put(f"{BASE_URL}/api/tours/{tour['id']}", json={
            "weight": 3000.0
        })
        
        assert response_b.status_code == 409, f"Expected 409 when Driver B tries to modify completed tour, got {response_b.status_code}"
        print("✓ Completed tour correctly locked for other drivers")
    
    def test_unclaimed_tour_accessible_by_all_drivers(self):
        """Unclaimed tours: All drivers can interact with unclaimed tours"""
        tour = self.create_test_tour()
        assert tour is not None
        
        # Verify tour is unclaimed
        assert tour.get("claimed_by", "") == "", "Tour should start unclaimed"
        
        # Driver A can set priority (non-restricted field)
        response_a = requests.put(f"{BASE_URL}/api/tours/{tour['id']}", json={
            "priority": "high"
        })
        assert response_a.status_code == 200, f"Expected 200, got {response_a.status_code}"
        
        # Driver B can also update
        response_b = requests.put(f"{BASE_URL}/api/tours/{tour['id']}", json={
            "priority": "urgent"
        })
        assert response_b.status_code == 200, f"Expected 200, got {response_b.status_code}"
        
        # Driver A can then claim
        response_claim = requests.put(f"{BASE_URL}/api/tours/{tour['id']}", json={
            "on_way": True,
            "claimed_by": self.driver_a
        })
        assert response_claim.status_code == 200
        print("✓ Unclaimed tours accessible by all drivers")
    
    def test_same_driver_can_modify_own_claimed_tour(self):
        """Same driver can modify their own claimed tour"""
        tour = self.create_test_tour()
        assert tour is not None
        
        # Driver A claims
        response_claim = requests.put(f"{BASE_URL}/api/tours/{tour['id']}", json={
            "on_way": True,
            "claimed_by": self.driver_a
        })
        assert response_claim.status_code == 200
        
        # Driver A can update their own tour (adding weight and completing)
        response_update = requests.put(f"{BASE_URL}/api/tours/{tour['id']}", json={
            "completed": True,
            "weight": 4000.0,
            "time": "15:00",
            "claimed_by": self.driver_a  # Same driver
        })
        
        assert response_update.status_code == 200, f"Expected 200, got {response_update.status_code}: {response_update.text}"
        updated_tour = response_update.json()
        assert updated_tour["completed"] == True
        assert updated_tour["weight"] == 4000.0
        print("✓ Same driver can modify their own claimed tour")


class TestAPIEndpoints:
    """Basic API endpoint tests"""
    
    def test_health_check(self):
        """API root endpoint works"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        print("✓ API health check passed")
    
    def test_get_tours(self):
        """GET /api/tours works"""
        response = requests.get(f"{BASE_URL}/api/tours")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print("✓ GET /api/tours works")
    
    def test_get_plads(self):
        """GET /api/plads works"""
        response = requests.get(f"{BASE_URL}/api/plads")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print("✓ GET /api/plads works")
    
    def test_get_drivers(self):
        """GET /api/drivers works"""
        response = requests.get(f"{BASE_URL}/api/drivers")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print("✓ GET /api/drivers works")
    
    def test_admin_login_correct_credentials(self):
        """Admin login with correct credentials"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={
            "username": "admin",
            "password": "1234"
        })
        # Note: According to server.py line 906, the password is "1234" not "ilkaps"
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ Admin login works with username=admin, password=1234")
    
    def test_admin_login_wrong_credentials(self):
        """Admin login with wrong credentials returns 401"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={
            "username": "admin",
            "password": "wrongpassword"
        })
        assert response.status_code == 401
        print("✓ Admin login correctly rejects wrong password")


class TestSeedDataVerification:
    """Verify the test seed data mentioned in agent_to_agent_context_note"""
    
    def test_skipstrup_plads_exists(self):
        """Verify Skipstrup plads exists"""
        response = requests.get(f"{BASE_URL}/api/plads")
        assert response.status_code == 200
        plads_names = [p["name"] for p in response.json()]
        assert "Skipstrup" in plads_names, f"Skipstrup not in plads list: {plads_names}"
        print("✓ Skipstrup plads exists")
    
    def test_tours_in_skipstrup(self):
        """Check if there are tours in Skipstrup"""
        response = requests.get(f"{BASE_URL}/api/tours?plads=Skipstrup")
        assert response.status_code == 200
        tours = response.json()
        print(f"✓ Found {len(tours)} tours in Skipstrup")
        
        # Check claimed tours
        claimed_tours = [t for t in tours if t.get("claimed_by")]
        unclaimed_tours = [t for t in tours if not t.get("claimed_by")]
        completed_tours = [t for t in tours if t.get("completed")]
        on_way_tours = [t for t in tours if t.get("on_way") and not t.get("completed")]
        
        print(f"  - Claimed tours: {len(claimed_tours)}")
        print(f"  - Unclaimed tours: {len(unclaimed_tours)}")
        print(f"  - Completed tours: {len(completed_tours)}")
        print(f"  - On way tours: {len(on_way_tours)}")
        
        for tour in claimed_tours:
            print(f"    • {tour.get('fraction', 'N/A')} claimed by {tour.get('claimed_by')} (completed: {tour.get('completed')}, on_way: {tour.get('on_way')})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
