import os
from pydicom import dcmread
from pydicom.data import get_testdata_file
from pathlib import Path

def setup_test_environment():
    # 1. Get the official pydicom test file
    sample_path = get_testdata_file("CT_small.dcm")
    ds = dcmread(sample_path)
    
    # 2. Inject "Raw" PHI so we can test if our script scrubs it
    ds.PatientName = "Doe^John"
    ds.PatientID = "12345"
    ds.StudyDate = "20250101"  # Let's assume the scan happened Jan 1st, 2025
    
    # 3. Create a raw input directory
    input_dir = Path("./raw_input")
    input_dir.mkdir(exist_ok=True)
    
    # 4. Save the "Raw" file
    test_file_path = input_dir / "sample_raw_scan.dcm"
    ds.save_as(str(test_file_path))
    
    print(f"✅ Setup Complete!")
    print(f"Generated Raw Scan: {test_file_path}")
    print(f"Original Name: {ds.PatientName}, Original ID: {ds.PatientID}")

if __name__ == "__main__":
    setup_test_environment()