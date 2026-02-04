import os
from pydicom import dcmread
from pydicom.data import get_testdata_file
from pathlib import Path

def setup_test_environment():
    # 1. Get the official pydicom test file
    sample_path = get_testdata_file("CT_small.dcm")
    
    # Create raw input directory
    input_dir = Path("./raw_input")
    input_dir.mkdir(exist_ok=True)
    
    # Test Case 1: Normal MRN + Accession lookup
    print("\n=== Test Case 1: Normal MRN and Accession ===")
    ds = dcmread(sample_path)
    ds.PatientName = "Doe^John"
    ds.PatientID = "12345"
    ds.AccessionNumber = "ACC001"
    ds.StudyDate = "20250101"  # Jan 1, 2025 (9 days before surgery)
    test_file_path = input_dir / "patient_01_scan_1.dcm"
    ds.save_as(str(test_file_path))
    print(f"✅ Created: {test_file_path}")
    print(f"   PatientID: {ds.PatientID}")
    print(f"   AccessionNumber: {ds.AccessionNumber}")
    print(f"   StudyDate: {ds.StudyDate}")
    print(f"   Expected output AccessionNumber: RSV0001_1")
    
    # Test Case 2: Accession-only lookup (MRN is underscores)
    print("\n=== Test Case 2: Accession number fallback (MRN has underscores) ===")
    ds = dcmread(sample_path)
    ds.PatientName = "Smith^Jane"
    ds.PatientID = "_____"  # Should be ignored, will use accession
    ds.AccessionNumber = "ACC002"
    ds.StudyDate = "20250220"  # Feb 20, 2025 (5 days after surgery)
    test_file_path = input_dir / "patient_02_scan_1.dcm"
    ds.save_as(str(test_file_path))
    print(f"✅ Created: {test_file_path}")
    print(f"   PatientID: {ds.PatientID} (will be ignored)")
    print(f"   AccessionNumber: {ds.AccessionNumber}")
    print(f"   StudyDate: {ds.StudyDate}")
    print(f"   Expected output AccessionNumber: RSV0002_1")
    
    # Test Case 3: Multiple scans for same patient (to test scan numbering)
    print("\n=== Test Case 3: Multiple scans for same patient ===")
    for scan_num in [1, 2]:
        ds = dcmread(sample_path)
        ds.PatientName = "Johnson^Bob"
        ds.PatientID = "12345"
        ds.AccessionNumber = "ACC001"
        ds.StudyDate = f"2025010{scan_num}"  # Jan 1 and Jan 2, 2025
        test_file_path = input_dir / f"patient_01_scan_{scan_num}.dcm"
        ds.save_as(str(test_file_path))
        print(f"✅ Created: {test_file_path}")
        print(f"   StudyDate: {ds.StudyDate}")
        print(f"   Expected output AccessionNumber: RSV0001_{scan_num}")
    
    print("\n" + "="*60)
    print("Test environment setup complete!")
    print("Run the following command to test the de-identification:")
    print("\npython deid_tool.py --csv test_mapping.csv --input ./raw_input --output ./deid_output")
    print("\nExpected results:")
    print("  - 4 DICOM files should be processed")
    print("  - notes.txt should be created in output folders")
    print("  - AccessionNumbers should follow pattern: Short_Prefix+Patient_Number_ScanNumber")
    print("="*60 + "\n")

if __name__ == "__main__":
    setup_test_environment()