"""
Test Argo text-based tour import system
- POST /api/parse-argo: Parse tab-separated text into tour objects
- POST /api/import-argo: Import parsed tours into database
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestArgoParseEndpoint:
    """Tests for POST /api/parse-argo endpoint"""
    
    def test_parse_argo_basic_tab_separated(self):
        """Test parsing basic tab-separated Argo text"""
        # Sample data with header and 2 data rows
        argo_text = """#\tType/Størrelse\tFra\tTil\tFraktion\tStatus\tTid
CTN-001\t20 fod\tKøge Genbrugsplads\tGlostrup\tJern\tAfhent\t08:00
CTN-002\t30 fod\tBrøndby Genbrugsplads\tAlbertslund\tTræ\tAfhent\t09:00"""
        
        response = requests.post(f"{BASE_URL}/api/parse-argo", json={
            "text": argo_text,
            "date": "2026-01-15"
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "tours" in data, "Response should contain 'tours' field"
        assert "count" in data, "Response should contain 'count' field"
        
        # Verify count matches tours length
        assert data["count"] == len(data["tours"]), "Count should match tours length"
        assert data["count"] == 2, f"Expected 2 tours, got {data['count']}"
        
        # Verify first tour data
        tour1 = data["tours"][0]
        assert tour1["container"] == "CTN-001", f"Expected CTN-001, got {tour1['container']}"
        assert tour1["container_type"] == "20 fod", f"Expected '20 fod', got {tour1['container_type']}"
        assert tour1["fra"] == "Køge Genbrugsplads", f"Expected 'Køge Genbrugsplads', got {tour1['fra']}"
        assert tour1["til"] == "Glostrup", f"Expected 'Glostrup', got {tour1['til']}"
        assert tour1["fraktion"] == "Jern", f"Expected 'Jern', got {tour1['fraktion']}"
        assert tour1["plads"] == "Køge", f"Expected 'Køge' (extracted from fra), got {tour1['plads']}"
        assert tour1["tid"] == "08:00", f"Expected '08:00', got {tour1['tid']}"
        
        # Verify second tour data
        tour2 = data["tours"][1]
        assert tour2["container"] == "CTN-002"
        assert tour2["plads"] == "Brøndby"
        assert tour2["fraktion"] == "Træ"
        print("✓ Basic tab-separated parsing works correctly")
    
    def test_parse_argo_empty_text(self):
        """Test parsing empty text returns empty tours"""
        response = requests.post(f"{BASE_URL}/api/parse-argo", json={
            "text": "",
            "date": "2026-01-15"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0, "Empty text should return 0 tours"
        assert data["tours"] == [], "Empty text should return empty tours list"
        print("✓ Empty text handling works correctly")
    
    def test_parse_argo_header_only(self):
        """Test parsing text with only header returns empty tours"""
        argo_text = "#\tType/Størrelse\tFra\tTil\tFraktion\tStatus\tTid"
        
        response = requests.post(f"{BASE_URL}/api/parse-argo", json={
            "text": argo_text,
            "date": "2026-01-15"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0, "Header-only text should return 0 tours"
        print("✓ Header-only text handling works correctly")
    
    def test_parse_argo_missing_fields(self):
        """Test parsing text with missing optional fields"""
        # Text with minimal fields (no tid)
        argo_text = """CTN-003\t40 fod\tGlostrup Genbrugsplads\tKøge\tMetal"""
        
        response = requests.post(f"{BASE_URL}/api/parse-argo", json={
            "text": argo_text,
            "date": "2026-01-15"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1, f"Expected 1 tour, got {data['count']}"
        
        tour = data["tours"][0]
        assert tour["container"] == "CTN-003"
        assert tour["tid"] == "", "Missing tid should be empty string"
        print("✓ Missing fields handling works correctly")


class TestArgoImportEndpoint:
    """Tests for POST /api/import-argo endpoint"""
    
    def test_import_argo_success(self):
        """Test importing parsed tours into database"""
        tours_data = [
            {
                "container": "TEST-ARGO-001",
                "container_type": "20 fod",
                "fra": "Test Genbrugsplads",
                "til": "Test Facility",
                "fraktion": "TestMaterial",
                "plads": "Test",
                "tid": "10:00"
            },
            {
                "container": "TEST-ARGO-002",
                "container_type": "30 fod",
                "fra": "Test2 Genbrugsplads",
                "til": "Test2 Facility",
                "fraktion": "TestMaterial2",
                "plads": "Test2",
                "tid": "11:00"
            }
        ]
        
        response = requests.post(f"{BASE_URL}/api/import-argo", json={
            "tours": tours_data,
            "date": "2026-01-15"
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "message" in data, "Response should contain 'message' field"
        assert "count" in data, "Response should contain 'count' field"
        assert "tour_ids" in data, "Response should contain 'tour_ids' field"
        
        # Verify count
        assert data["count"] == 2, f"Expected 2 tours imported, got {data['count']}"
        assert len(data["tour_ids"]) == 2, "Should return 2 tour IDs"
        
        # Verify message contains count
        assert "2" in data["message"], "Message should mention count"
        print(f"✓ Import successful: {data['message']}")
        
        # Verify tours were actually created by fetching them via date endpoint
        get_response = requests.get(f"{BASE_URL}/api/tours?date=2026-01-15")
        assert get_response.status_code == 200, "Should be able to fetch tours by date"
        all_tours = get_response.json()
        
        # Find our test tours
        created_tour_ids = set(data["tour_ids"])
        found_tours = [t for t in all_tours if t["id"] in created_tour_ids]
        assert len(found_tours) == 2, f"Expected 2 test tours, found {len(found_tours)}"
        
        for tour in found_tours:
            assert "Argo" in tour.get("remark", ""), "Tour remark should contain 'Argo'"
            print(f"  ✓ Tour {tour['id']} verified in database with remark: {tour['remark']}")
        
        # Cleanup: Delete test tours
        for tour_id in data["tour_ids"]:
            requests.delete(f"{BASE_URL}/api/tours/{tour_id}")
        print("✓ Test tours cleaned up")
    
    def test_import_argo_missing_date(self):
        """Test import fails without date"""
        response = requests.post(f"{BASE_URL}/api/import-argo", json={
            "tours": [{"container": "TEST", "fra": "Test"}]
        })
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Missing date validation works")
    
    def test_import_argo_missing_tours(self):
        """Test import fails without tours"""
        response = requests.post(f"{BASE_URL}/api/import-argo", json={
            "date": "2026-01-15"
        })
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Missing tours validation works")
    
    def test_import_argo_empty_tours(self):
        """Test import fails with empty tours array"""
        response = requests.post(f"{BASE_URL}/api/import-argo", json={
            "tours": [],
            "date": "2026-01-15"
        })
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Empty tours validation works")


class TestArgoEndToEndFlow:
    """End-to-end test: Parse then Import"""
    
    def test_parse_then_import_flow(self):
        """Test complete flow: parse text -> import tours"""
        # Step 1: Parse Argo text
        argo_text = """#\tType/Størrelse\tFra\tTil\tFraktion\tStatus\tTid
TEST-E2E-001\t20 fod\tE2E Genbrugsplads\tDestination1\tPap\tAfhent\t14:00"""
        
        parse_response = requests.post(f"{BASE_URL}/api/parse-argo", json={
            "text": argo_text,
            "date": "2026-01-16"
        })
        
        assert parse_response.status_code == 200
        parsed_data = parse_response.json()
        assert parsed_data["count"] == 1
        print("✓ Step 1: Parse successful")
        
        # Step 2: Import parsed tours
        import_response = requests.post(f"{BASE_URL}/api/import-argo", json={
            "tours": parsed_data["tours"],
            "date": "2026-01-16"
        })
        
        assert import_response.status_code == 200
        import_data = import_response.json()
        assert import_data["count"] == 1
        print("✓ Step 2: Import successful")
        
        # Step 3: Verify tour in database via date endpoint
        tour_id = import_data["tour_ids"][0]
        get_response = requests.get(f"{BASE_URL}/api/tours?date=2026-01-16")
        assert get_response.status_code == 200
        
        all_tours = get_response.json()
        tour = next((t for t in all_tours if t["id"] == tour_id), None)
        assert tour is not None, f"Tour {tour_id} should exist"
        assert tour["container"] == "TEST-E2E-001"
        assert tour["date"] == "2026-01-16"
        assert "Argo" in tour.get("remark", ""), "Tour remark should contain 'Argo'"
        assert tour["plads"] == "E2E"
        print("✓ Step 3: Tour verified in database")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/tours/{tour_id}")
        print("✓ E2E flow completed successfully")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
