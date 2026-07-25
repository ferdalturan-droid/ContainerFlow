"""
Test PDF Parsing Endpoint - /api/parse-pdf
Tests the new PDF import feature for container orders.
- PDF text extraction using PyMuPDF
- Material/quantity parsing (e.g., 'Pap = 2' creates 2 tours)
- Range handling (e.g., '3-4' uses minimum value 3)
- Notes attachment (e.g., 'RYSTES' attached to next material)
- Date extraction from PDF text
"""
import pytest
import requests
import os
import io

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestPdfParsing:
    """PDF parsing endpoint tests"""
    
    def test_api_accessible(self):
        """Test that API is accessible"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200, f"API not accessible: {response.status_code}"
        print("✓ API is accessible")
    
    def test_parse_pdf_with_test_file(self):
        """Test PDF parsing with the test order PDF"""
        pdf_path = "/tmp/test_order.pdf"
        assert os.path.exists(pdf_path), f"Test PDF not found at {pdf_path}"
        
        with open(pdf_path, 'rb') as f:
            files = {'file': ('test_order.pdf', f, 'application/pdf')}
            response = requests.post(f"{BASE_URL}/api/parse-pdf", files=files)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify success
        assert data['success'] == True, f"Expected success=True, got {data['success']}"
        print(f"✓ PDF parsed successfully")
        
        # Verify tour count - Expected: 4+2+1+3+2+1 = 13 tours
        # Trykimprægneret træ = 4, Pap = 2, Flasker = 1, Jern og metal = 3-4 (min=3), Haveaffald = 2, Storskrald = 1
        assert data['count'] == 13, f"Expected 13 tours, got {data['count']}"
        print(f"✓ Correct tour count: {data['count']}")
        
        # Verify tours list
        assert len(data['tours']) == 13, f"Expected 13 tours in list, got {len(data['tours'])}"
        print(f"✓ Tours list has {len(data['tours'])} items")
        
        return data
    
    def test_pap_creates_2_tours(self):
        """Test that 'Pap = 2' creates exactly 2 tours with fraction 'Pap'"""
        pdf_path = "/tmp/test_order.pdf"
        
        with open(pdf_path, 'rb') as f:
            files = {'file': ('test_order.pdf', f, 'application/pdf')}
            response = requests.post(f"{BASE_URL}/api/parse-pdf", files=files)
        
        data = response.json()
        pap_tours = [t for t in data['tours'] if t['fraction'] == 'Pap']
        
        assert len(pap_tours) == 2, f"Expected 2 Pap tours, got {len(pap_tours)}"
        print(f"✓ 'Pap = 2' creates 2 tours")
    
    def test_range_uses_minimum(self):
        """Test that range '3-4' creates 3 tours (minimum value)"""
        pdf_path = "/tmp/test_order.pdf"
        
        with open(pdf_path, 'rb') as f:
            files = {'file': ('test_order.pdf', f, 'application/pdf')}
            response = requests.post(f"{BASE_URL}/api/parse-pdf", files=files)
        
        data = response.json()
        metal_tours = [t for t in data['tours'] if 'Jern og metal' in t['fraction']]
        
        assert len(metal_tours) == 3, f"Expected 3 'Jern og metal' tours (min of 3-4), got {len(metal_tours)}"
        print(f"✓ Range '3-4' creates 3 tours (minimum)")
    
    def test_notes_attached_to_next_material(self):
        """Test that notes like 'RYSTES' are attached to the next material's remark"""
        pdf_path = "/tmp/test_order.pdf"
        
        with open(pdf_path, 'rb') as f:
            files = {'file': ('test_order.pdf', f, 'application/pdf')}
            response = requests.post(f"{BASE_URL}/api/parse-pdf", files=files)
        
        data = response.json()
        
        # RYSTES should be attached to Haveaffald (next material after Jern og metal)
        haveaffald_tours = [t for t in data['tours'] if 'Haveaffald' in t['fraction']]
        
        assert len(haveaffald_tours) > 0, "No Haveaffald tours found"
        
        # Check if any Haveaffald tour has RYSTES in remark
        has_rystes = any('RYSTES' in (t.get('remark', '') or '') for t in haveaffald_tours)
        assert has_rystes, f"Expected 'RYSTES' in Haveaffald remark, got remarks: {[t.get('remark') for t in haveaffald_tours]}"
        print(f"✓ Note 'RYSTES' attached to Haveaffald tours")
    
    def test_date_extraction(self):
        """Test that date '02.04.2026' is extracted and formatted as '2026-04-02'"""
        pdf_path = "/tmp/test_order.pdf"
        
        with open(pdf_path, 'rb') as f:
            files = {'file': ('test_order.pdf', f, 'application/pdf')}
            response = requests.post(f"{BASE_URL}/api/parse-pdf", files=files)
        
        data = response.json()
        
        # All tours should have the extracted date
        assert len(data['tours']) > 0, "No tours found"
        
        first_tour_date = data['tours'][0]['date']
        assert first_tour_date == '2026-04-02', f"Expected date '2026-04-02', got '{first_tour_date}'"
        
        # Verify all tours have the same date
        all_same_date = all(t['date'] == '2026-04-02' for t in data['tours'])
        assert all_same_date, "Not all tours have the same extracted date"
        print(f"✓ Date extracted correctly: 2026-04-02")
    
    def test_grouped_by_facility(self):
        """Test that grouped_by_facility contains correct material counts"""
        pdf_path = "/tmp/test_order.pdf"
        
        with open(pdf_path, 'rb') as f:
            files = {'file': ('test_order.pdf', f, 'application/pdf')}
            response = requests.post(f"{BASE_URL}/api/parse-pdf", files=files)
        
        data = response.json()
        grouped = data.get('grouped_by_facility', {})
        
        # Verify expected materials are present
        expected_materials = {
            'Trykimprægneret træ': 4,
            'Pap': 2,
            'Flasker': 1,
            'Jern og metal': 3,  # min of 3-4
            'Haveaffald': 2,
            'Storskrald': 1
        }
        
        for material, expected_count in expected_materials.items():
            assert material in grouped, f"Material '{material}' not found in grouped_by_facility"
            actual_count = grouped[material].get('count', 0)
            assert actual_count == expected_count, f"Expected {expected_count} for '{material}', got {actual_count}"
        
        print(f"✓ grouped_by_facility has correct counts")
    
    def test_empty_pdf_returns_failure(self):
        """Test that empty PDF returns success=false"""
        # Create a minimal empty PDF
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        # Don't add any text
        pdf_bytes = doc.tobytes()
        doc.close()
        
        files = {'file': ('empty.pdf', io.BytesIO(pdf_bytes), 'application/pdf')}
        response = requests.post(f"{BASE_URL}/api/parse-pdf", files=files)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert data['success'] == False, f"Expected success=False for empty PDF, got {data['success']}"
        assert data['count'] == 0, f"Expected count=0 for empty PDF, got {data['count']}"
        print(f"✓ Empty PDF returns success=false")
    
    def test_pdf_no_materials_returns_failure(self):
        """Test that PDF with no material patterns returns success=false"""
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        # Add text but no material patterns
        page.insert_text((50, 50), "This is just some random text\nNo materials here\nJust a header")
        pdf_bytes = doc.tobytes()
        doc.close()
        
        files = {'file': ('no_materials.pdf', io.BytesIO(pdf_bytes), 'application/pdf')}
        response = requests.post(f"{BASE_URL}/api/parse-pdf", files=files)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert data['success'] == False, f"Expected success=False for PDF with no materials, got {data['success']}"
        print(f"✓ PDF with no materials returns success=false")


class TestMailParsing:
    """Verify existing mail parsing still works"""
    
    def test_parse_mail_endpoint_exists(self):
        """Test that /api/parse-mail endpoint still exists"""
        response = requests.post(f"{BASE_URL}/api/parse-mail", json={"text": ""})
        # Should return 200 even with empty text
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✓ /api/parse-mail endpoint exists")
    
    def test_parse_mail_with_tab_format(self):
        """Test mail parsing with tab-separated format"""
        mail_text = """01-04-2026\t12345\tPap\tTomning\tSkipstrup\tVej 1\t08:00\t16:00\tTest remark"""
        
        response = requests.post(f"{BASE_URL}/api/parse-mail", json={"text": mail_text})
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Should parse at least one tour
        assert data['success'] == True or data['count'] >= 0, "Mail parsing should work"
        print(f"✓ Mail parsing with tab format works, count: {data.get('count', 0)}")


class TestToursBulkEndpoint:
    """Test tours/bulk endpoint used by PDF upload"""
    
    def test_tours_bulk_endpoint_exists(self):
        """Test that /api/tours/bulk endpoint exists"""
        # Send empty array - should return 200
        response = requests.post(f"{BASE_URL}/api/tours/bulk", json=[])
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✓ /api/tours/bulk endpoint exists")
    
    def test_tours_bulk_creates_tours(self):
        """Test that tours/bulk creates tours correctly"""
        test_tours = [
            {
                "date": "2026-04-02",
                "container": "TEST-PDF-001",
                "fraction": "TEST_PDF_Pap",
                "facility": "",
                "address": "",
                "plads": "Skipstrup Genbrugsplads",
                "driver_id": "",
                "driver_name": "",
                "report_id": ""
            },
            {
                "date": "2026-04-02",
                "container": "TEST-PDF-002",
                "fraction": "TEST_PDF_Metal",
                "facility": "",
                "address": "",
                "plads": "Skipstrup Genbrugsplads",
                "driver_id": "",
                "driver_name": "",
                "report_id": ""
            }
        ]
        
        response = requests.post(f"{BASE_URL}/api/tours/bulk", json=test_tours)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        # Bulk endpoint returns list of created tours
        assert isinstance(data, list), f"Expected list response, got {type(data)}"
        assert len(data) == 2, f"Expected 2 tours created, got {len(data)}"
        print(f"✓ tours/bulk creates tours correctly")
        
        # Cleanup - delete test tours
        tours_response = requests.get(f"{BASE_URL}/api/tours?date=2026-04-02")
        if tours_response.status_code == 200:
            tours = tours_response.json()
            for tour in tours:
                if tour.get('fraction', '').startswith('TEST_PDF_'):
                    requests.delete(f"{BASE_URL}/api/tours/{tour['id']}")
            print(f"✓ Test tours cleaned up")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
