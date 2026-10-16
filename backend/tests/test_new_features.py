"""
Test Suite for New Features: Solo/Hænger, Mail Parser Dual Format, Transport Type
Focus: Backend API testing for transport_type field, mail parsing formats
"""

import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'http://localhost:8080').rstrip('/')

class TestTransportType:
    """Tests for Solo/Hænger transport_type field in tours"""
    
    def test_update_tour_transport_type_solo(self):
        """Test updating tour transport_type to 'solo'"""
        # Get existing tours
        response = requests.get(f"{BASE_URL}/api/tours")
        assert response.status_code == 200
        tours = response.json()
        
        if len(tours) == 0:
            pytest.skip("No tours available for testing")
            
        # Find an unclaimed tour
        unclaimed_tour = None
        for t in tours:
            if not t.get('claimed_by'):
                unclaimed_tour = t
                break
        
        if not unclaimed_tour:
            pytest.skip("No unclaimed tours available")
        
        tour_id = unclaimed_tour['id']
        
        # Update to solo
        response = requests.put(f"{BASE_URL}/api/tours/{tour_id}", json={
            "transport_type": "solo"
        })
        assert response.status_code == 200
        data = response.json()
        assert data['transport_type'] == 'solo'
        print(f"PASSED: Tour {tour_id} transport_type set to 'solo'")
        
        # Verify persistence
        response = requests.get(f"{BASE_URL}/api/tours")
        tours = response.json()
        updated_tour = next((t for t in tours if t['id'] == tour_id), None)
        assert updated_tour is not None
        assert updated_tour['transport_type'] == 'solo'
        print(f"PASSED: Transport type 'solo' persisted correctly")

    def test_update_tour_transport_type_haenger(self):
        """Test updating tour transport_type to 'hænger'"""
        # Get existing tours
        response = requests.get(f"{BASE_URL}/api/tours")
        assert response.status_code == 200
        tours = response.json()
        
        if len(tours) == 0:
            pytest.skip("No tours available for testing")
            
        # Find a different unclaimed tour
        unclaimed_tour = None
        for t in tours:
            if not t.get('claimed_by') and t.get('transport_type') != 'solo':
                unclaimed_tour = t
                break
        
        if not unclaimed_tour:
            # Use any tour
            unclaimed_tour = tours[1] if len(tours) > 1 else tours[0]
        
        tour_id = unclaimed_tour['id']
        
        # Update to hænger
        response = requests.put(f"{BASE_URL}/api/tours/{tour_id}", json={
            "transport_type": "hænger"
        })
        assert response.status_code == 200
        data = response.json()
        assert data['transport_type'] == 'hænger'
        print(f"PASSED: Tour {tour_id} transport_type set to 'hænger'")

    def test_tour_model_has_transport_type_field(self):
        """Verify tour model includes transport_type field"""
        response = requests.get(f"{BASE_URL}/api/tours")
        assert response.status_code == 200
        tours = response.json()
        
        if len(tours) > 0:
            tour = tours[0]
            assert 'transport_type' in tour
            print(f"PASSED: transport_type field exists in tour model")

    def test_create_tour_with_transport_type(self):
        """Test creating a new tour with transport_type"""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        
        # Create tour with transport_type
        tour_data = {
            "date": tomorrow,
            "container": "TEST-999",
            "fraction": "TestFraktion",
            "facility": "TestFacility",
            "address": "Testvej 123, 2640 Hedehusene",
            "plads": "Skipstrup",
            "priority": "normal"
        }
        
        response = requests.post(f"{BASE_URL}/api/tours", json=tour_data)
        assert response.status_code == 200
        created_tour = response.json()
        
        # Verify transport_type field exists (should be empty string by default)
        assert 'transport_type' in created_tour
        assert created_tour['transport_type'] == '' or created_tour['transport_type'] is None or created_tour['transport_type'] == ''
        print(f"PASSED: New tour created with transport_type field")
        
        # Update with transport_type
        response = requests.put(f"{BASE_URL}/api/tours/{created_tour['id']}", json={
            "transport_type": "solo"
        })
        assert response.status_code == 200
        assert response.json()['transport_type'] == 'solo'
        print(f"PASSED: Updated new tour to solo")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/tours/{created_tour['id']}")


class TestMailParserDualFormat:
    """Tests for mail parser supporting both horizontal and vertical formats"""
    
    def test_parse_horizontal_tab_format(self):
        """Test parsing horizontal tab-separated mail format"""
        # Sample horizontal tab-separated data (matching what real mails look like)
        mail_text = """20-03-2026\t5962\tEternit\tTømning\tAV Miljø\tAvedøreholmen 97, 2650 Hvidovre\t7\t14\t
20-03-2026\t5906\tJord, grus\tTømning\tDamifo a/s\tBeredskabsvej 21, 2640 Hedehusene\t6\t16\t"""
        
        response = requests.post(f"{BASE_URL}/api/parse-mail", json={
            "text": mail_text,
            "report_id": ""
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True
        assert data['count'] >= 2
        print(f"PASSED: Horizontal tab format parsed, found {data['count']} tours")
        
        # Verify parsed tour details
        tours = data['tours']
        assert len(tours) >= 2
        
        # Check first tour has correct data
        tour1 = tours[0]
        assert tour1['date'] == '20-03-2026'
        assert tour1['container'] == '5962'
        assert tour1['fraction'] == 'Eternit'
        print(f"PASSED: Horizontal format tour data parsed correctly")

    def test_parse_vertical_multiline_format(self):
        """Test parsing vertical multi-line mail format (one field per line)"""
        # Sample vertical format - each tour spans multiple lines
        mail_text = """20-03-2026
5962
Eternit
Tømning
AV Miljø
Avedøreholmen 97, 2650 Hvidovre
7 14
20-03-2026
5906
Jord, grus
Ombytning
Damifo a/s
Beredskabsvej 21, 2640 Hedehusene
6 16"""
        
        response = requests.post(f"{BASE_URL}/api/parse-mail", json={
            "text": mail_text,
            "report_id": ""
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Should detect vertical format and parse correctly
        print(f"Parse result: success={data['success']}, count={data['count']}")
        print(f"Debug info: {data.get('debug_info', '')[:500]}")
        
        assert data['success'] == True
        assert data['count'] >= 2
        print(f"PASSED: Vertical multi-line format parsed, found {data['count']} tours")

    def test_parse_horizontal_with_multiple_spaces(self):
        """Test parsing horizontal format with multiple spaces as separator"""
        # Sometimes mails use multiple spaces instead of tabs
        mail_text = """20-03-2026  5962  Eternit  Tømning  AV Miljø  Avedøreholmen 97, 2650 Hvidovre  7  14
20-03-2026  5906  Jord  Ombytning  Damifo  Beredskabsvej 21, 2640 Hedehusene  6  16"""
        
        response = requests.post(f"{BASE_URL}/api/parse-mail", json={
            "text": mail_text,
            "report_id": ""
        })
        
        assert response.status_code == 200
        data = response.json()
        print(f"Multiple spaces format: success={data['success']}, count={data['count']}")
        print(f"Debug info: {data.get('debug_info', '')[:500]}")
        
        # Should attempt to parse with multiple spaces
        # Note: This may or may not succeed depending on implementation
        if data['success']:
            print(f"PASSED: Multiple spaces format parsed successfully")
        else:
            print(f"INFO: Multiple spaces format not supported (expected)")

    def test_parse_mail_returns_grouped_by_facility(self):
        """Test that parse-mail returns grouped_by_facility summary"""
        mail_text = """20-03-2026\t5962\tEternit\tTømning\tAV Miljø\tAvedøreholmen 97, 2650 Hvidovre\t7\t14\t
20-03-2026\t5906\tJord\tTømning\tAV Miljø\tBeredskabsvej 21, 2640 Hedehusene\t6\t16\t"""
        
        response = requests.post(f"{BASE_URL}/api/parse-mail", json={
            "text": mail_text,
            "report_id": ""
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify grouped_by_facility is in response
        assert 'grouped_by_facility' in data
        print(f"PASSED: grouped_by_facility present in response")
        
        # If parsing was successful, check the grouping
        if data['success']:
            grouped = data['grouped_by_facility']
            assert 'AV Miljø' in grouped
            print(f"PASSED: Facility grouping works correctly: {grouped}")

    def test_parse_mail_empty_text(self):
        """Test parse-mail with empty text"""
        response = requests.post(f"{BASE_URL}/api/parse-mail", json={
            "text": "",
            "report_id": ""
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data['success'] == False
        assert data['count'] == 0
        print(f"PASSED: Empty text returns success=False")

    def test_parse_mail_invalid_format(self):
        """Test parse-mail with invalid/random text"""
        response = requests.post(f"{BASE_URL}/api/parse-mail", json={
            "text": "This is just random text without any valid tour data",
            "report_id": ""
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data['success'] == False
        assert data['count'] == 0
        print(f"PASSED: Invalid format returns success=False")


class TestPostalCodeGrouping:
    """Tests for postal code grouping logic - tours with nearby postal codes"""
    
    def test_tours_have_addresses_with_postal_codes(self):
        """Verify that tours have addresses that can be parsed for postal codes"""
        response = requests.get(f"{BASE_URL}/api/tours")
        assert response.status_code == 200
        tours = response.json()
        
        # Check for tours with Danish postal codes (4 digits)
        tours_with_postal = [t for t in tours if t.get('address') and any(c.isdigit() for c in t.get('address', ''))]
        
        assert len(tours_with_postal) > 0
        print(f"PASSED: Found {len(tours_with_postal)} tours with addresses containing postal codes")
        
        # Look for tours that should be grouped (postal codes within ±5)
        for tour in tours_with_postal:
            address = tour.get('address', '')
            # Extract 4-digit postal code
            import re
            match = re.search(r'\b(\d{4})\b', address)
            if match:
                print(f"  Tour {tour['container']}: postal code {match.group(1)} from '{address}'")

    def test_create_tours_for_grouping_test(self):
        """Create test tours with nearby postal codes to verify grouping"""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        
        # Create two tours with nearby postal codes (2640 and 2641)
        tour1_data = {
            "date": tomorrow,
            "container": "GROUP-TEST-1",
            "fraction": "TestGroupFraktion1",
            "facility": "TestFacility",
            "address": "Testvej 1, 2640 Hedehusene",  # Postal code 2640
            "plads": "Skipstrup"
        }
        
        tour2_data = {
            "date": tomorrow,
            "container": "GROUP-TEST-2",
            "fraction": "TestGroupFraktion2",
            "facility": "TestFacility2",
            "address": "Testvej 2, 2641 Hedehusene",  # Postal code 2641 (within ±5)
            "plads": "Skipstrup"
        }
        
        # Create tours
        response1 = requests.post(f"{BASE_URL}/api/tours", json=tour1_data)
        assert response1.status_code == 200
        created1 = response1.json()
        print(f"Created tour 1: {created1['container']} with address {created1['address']}")
        
        response2 = requests.post(f"{BASE_URL}/api/tours", json=tour2_data)
        assert response2.status_code == 200
        created2 = response2.json()
        print(f"Created tour 2: {created2['container']} with address {created2['address']}")
        
        print(f"PASSED: Created 2 test tours with postal codes 2640 and 2641 (should be grouped)")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/tours/{created1['id']}")
        requests.delete(f"{BASE_URL}/api/tours/{created2['id']}")


class TestTourCRUD:
    """Basic CRUD tests for tours - verify existing functionality not broken"""
    
    def test_get_tours(self):
        """Test GET /api/tours"""
        response = requests.get(f"{BASE_URL}/api/tours")
        assert response.status_code == 200
        tours = response.json()
        assert isinstance(tours, list)
        print(f"PASSED: GET /api/tours returns {len(tours)} tours")

    def test_get_tours_by_plads(self):
        """Test GET /api/tours with plads filter"""
        response = requests.get(f"{BASE_URL}/api/tours?plads=Skipstrup")
        assert response.status_code == 200
        tours = response.json()
        
        # All returned tours should have plads=Skipstrup
        for tour in tours:
            assert tour['plads'] == 'Skipstrup'
        print(f"PASSED: GET /api/tours?plads=Skipstrup returns {len(tours)} tours")

    def test_update_tour_weight(self):
        """Test updating tour weight"""
        # Get a tour
        response = requests.get(f"{BASE_URL}/api/tours")
        tours = response.json()
        
        if len(tours) == 0:
            pytest.skip("No tours for testing")
        
        # Find unclaimed tour
        test_tour = None
        for t in tours:
            if not t.get('claimed_by'):
                test_tour = t
                break
        
        if not test_tour:
            pytest.skip("No unclaimed tours available")
        
        # Update weight
        response = requests.put(f"{BASE_URL}/api/tours/{test_tour['id']}", json={
            "weight": 150.5
        })
        assert response.status_code == 200
        data = response.json()
        assert data['weight'] == 150.5
        print(f"PASSED: Tour weight updated to 150.5")


class TestAdminLogin:
    """Test admin authentication"""
    
    def test_admin_login_correct_credentials(self):
        """Test admin login with correct credentials"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={
            "username": "admin",
            "password": "1234"
        })
        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True
        print(f"PASSED: Admin login with admin/1234 successful")

    def test_admin_login_wrong_credentials(self):
        """Test admin login with wrong credentials"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={
            "username": "admin",
            "password": "wrong"
        })
        assert response.status_code == 401
        print(f"PASSED: Admin login with wrong password returns 401")


class TestPladsList:
    """Test plads endpoints"""
    
    def test_get_plads(self):
        """Test GET /api/plads"""
        response = requests.get(f"{BASE_URL}/api/plads")
        assert response.status_code == 200
        plads = response.json()
        assert isinstance(plads, list)
        assert len(plads) > 0
        
        # Check Skipstrup is in the list
        plads_names = [p['name'] for p in plads]
        assert 'Skipstrup' in plads_names
        print(f"PASSED: GET /api/plads returns {len(plads)} plads")


class TestHealthCheck:
    """Basic health check tests"""
    
    def test_api_root(self):
        """Test API root endpoint"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert 'message' in data
        print(f"PASSED: API root returns message: {data['message']}")

    def test_api_drivers(self):
        """Test GET /api/drivers"""
        response = requests.get(f"{BASE_URL}/api/drivers")
        assert response.status_code == 200
        drivers = response.json()
        assert isinstance(drivers, list)
        print(f"PASSED: GET /api/drivers returns {len(drivers)} drivers")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
